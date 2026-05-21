"""Admin-only CRUD for partner API keys.

See `docs/business/partner-api-v1-scope.md` (Auth model: Key management UX).

v1 ships admin-only endpoints; org-admin UI is deferred to v1.1 when partner
count > ~2. Every mutation is audit-logged via ``log_audit`` so cross-org
key provisioning has an immutable trail. The secret half of a newly
generated key is returned ONCE in the create response — never on GET.

Auth: platform admin (owner OR operator). Operator can issue keys; owner
can also read details. We use the platform-admin rung throughout since
key management is infrastructure-shaped, not customer-data-shaped.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from app.core.logging import get_logger
from app.core.partner_tokens import (
    ReservedScopeError,
    UnknownScopeError,
    generate_partner_token,
    hash_partner_secret,
    validate_scopes,
)
from app.core.platform_auth import require_platform_admin
from app.core.time import utcnow
from app.db.session import get_session
from app.models.organizations import Organization
from app.models.partner_api_key import PartnerApiKey
from app.schemas.partner_admin import (
    PartnerApiKeyCreateRequest,
    PartnerApiKeyCreateResponse,
    PartnerApiKeyListItem,
    PartnerApiKeyRevokeRequest,
)
from app.services.audit import log_audit

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.users import User

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/partner-keys", tags=["admin"])

SESSION_DEP = Depends(get_session)
ADMIN_DEP = Depends(require_platform_admin)


@router.post(
    "",
    response_model=PartnerApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a new partner API key (secret returned ONCE)",
)
async def create_partner_key(
    body: PartnerApiKeyCreateRequest,
    admin: User = ADMIN_DEP,
    session: AsyncSession = SESSION_DEP,
) -> PartnerApiKeyCreateResponse:
    """Generate a new partner API key for ``body.organization_id``.

    The full token (``vck_<key_id>.<secret>``) is returned ONCE in this
    response. After this point the secret is unrecoverable — callers must
    deliver it to the partner via a secure channel immediately.

    Reserved scopes (``leads:*``, ``intakes:*``, ``records:*``, ``skills:*``,
    etc.) are rejected with 422. They slot into v1.x as their endpoints ship.
    """
    organization = await session.get(Organization, body.organization_id)
    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {body.organization_id} not found",
        )

    try:
        validated_scopes = validate_scopes(body.scopes)
    except ReservedScopeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except UnknownScopeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    full_token, key_id, secret = generate_partner_token()
    key_hash = hash_partner_secret(secret)

    api_key = PartnerApiKey(
        id=uuid4(),
        organization_id=organization.id,
        key_id=key_id,
        key_hash=key_hash,
        scopes=validated_scopes,
        label=body.label,
        created_by=admin.id,
        rate_limit_override=body.rate_limit_override,
        created_at=utcnow(),
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)

    await log_audit(
        org_id=organization.id,
        action="partner_key.create",
        user_id=admin.id,
        resource_type="partner_api_key",
        resource_id=api_key.id,
        details={
            "key_id": key_id,
            "label": body.label,
            "scopes": validated_scopes,
            "rate_limit_override": body.rate_limit_override,
        },
    )

    return PartnerApiKeyCreateResponse(
        id=api_key.id,
        organization_id=api_key.organization_id,
        key_id=api_key.key_id,
        full_token=full_token,
        scopes=list(api_key.scopes),
        label=api_key.label,
        rate_limit_override=api_key.rate_limit_override,
        created_at=api_key.created_at,
    )


@router.get(
    "",
    response_model=list[PartnerApiKeyListItem],
    summary="List partner API keys (optionally filtered by organization)",
)
async def list_partner_keys(
    organization_id: UUID | None = None,
    include_revoked: bool = False,
    admin: User = ADMIN_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[PartnerApiKeyListItem]:
    """List partner API keys with safe (no-secret) metadata.

    Filter by ``organization_id`` to scope to one org's keys; omit to list
    all keys across orgs (platform-admin view). Revoked keys are excluded
    by default — pass ``include_revoked=true`` to include them.

    Discards admin identity in the signature (kept only for the ADMIN_DEP
    side effect of enforcing auth) — keep the parameter to satisfy ruff.
    """
    _ = admin  # auth-enforcement only

    statement = select(PartnerApiKey)
    if organization_id is not None:
        statement = statement.where(
            PartnerApiKey.organization_id == organization_id  # type: ignore[arg-type]
        )
    if not include_revoked:
        statement = statement.where(PartnerApiKey.revoked_at.is_(None))  # type: ignore[union-attr]
    statement = statement.order_by(PartnerApiKey.created_at.desc())  # type: ignore[union-attr]

    rows = (await session.exec(statement)).all()

    return [
        PartnerApiKeyListItem(
            id=row.id,
            organization_id=row.organization_id,
            key_id=row.key_id,
            scopes=list(row.scopes),
            label=row.label,
            rate_limit_override=row.rate_limit_override,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
            revoked_at=row.revoked_at,
            revoked_reason=row.revoked_reason,
        )
        for row in rows
    ]


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a partner API key (sets revoked_at + revoked_reason)",
)
async def revoke_partner_key(
    key_id: UUID,
    body: PartnerApiKeyRevokeRequest,
    admin: User = ADMIN_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    """Revoke a partner API key. Idempotent — re-revoking a revoked key 200s.

    ``revoked_reason`` is required (free-text) so the audit trail captures
    why the key was retired: ``"rotated"``, ``"partner left"``,
    ``"suspected leak"``, etc. The reason flows into ``audit_log.details``.
    """
    api_key = await session.get(PartnerApiKey, key_id)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Partner API key {key_id} not found",
        )

    if api_key.revoked_at is not None:
        # Idempotent re-revoke. Don't update reason or timestamp.
        return None

    api_key.revoked_at = utcnow()
    api_key.revoked_reason = body.revoked_reason
    session.add(api_key)
    await session.commit()

    await log_audit(
        org_id=api_key.organization_id,
        action="partner_key.revoke",
        user_id=admin.id,
        resource_type="partner_api_key",
        resource_id=api_key.id,
        details={
            "key_id": api_key.key_id,
            "revoked_reason": body.revoked_reason,
        },
    )
    return None
