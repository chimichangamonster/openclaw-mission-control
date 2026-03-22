"""Organization settings API — BYOK keys, feature flags, branding."""

from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import require_org_member
from app.core.encryption import encrypt_token, decrypt_token
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.organization_settings import OrganizationSettings
from app.services.audit import log_audit
from app.services.organizations import OrganizationContext

router = APIRouter(prefix="/organization-settings", tags=["organization-settings"])


def _mask_key(key: str | None) -> str | None:
    """Mask an API key for display, showing only last 4 chars."""
    if not key:
        return None
    if len(key) <= 8:
        return "****"
    return f"{'*' * (len(key) - 4)}{key[-4:]}"


@router.get("/feature-flags")
async def get_feature_flags(
    org_ctx: OrganizationContext = Depends(require_org_member),
):
    """Get feature flags for the current organization (lightweight)."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

    if not settings:
        settings = OrganizationSettings(organization_id=org_id)

    return {"feature_flags": settings.feature_flags}


@router.get("")
async def get_settings(
    org_ctx: OrganizationContext = Depends(require_org_member),
):
    """Get organization settings. API keys are masked."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

    if not settings:
        settings = OrganizationSettings(organization_id=org_id)

    # Decrypt and mask keys for display
    or_key = None
    if settings.openrouter_api_key_encrypted:
        try:
            or_key = _mask_key(decrypt_token(settings.openrouter_api_key_encrypted))
        except Exception:
            or_key = "(invalid)"

    mgmt_key = None
    if settings.openrouter_management_key_encrypted:
        try:
            mgmt_key = _mask_key(decrypt_token(settings.openrouter_management_key_encrypted))
        except Exception:
            mgmt_key = "(invalid)"

    return {
        "openrouter_api_key": or_key,
        "has_openrouter_key": settings.openrouter_api_key_encrypted is not None,
        "openrouter_management_key": mgmt_key,
        "has_management_key": settings.openrouter_management_key_encrypted is not None,
        "default_model_tier_max": settings.default_model_tier_max,
        "configured_models": settings.configured_models,
        "feature_flags": settings.feature_flags,
        "agent_defaults": settings.agent_defaults,
        "branding": settings.branding,
    }


class SettingsUpdate(BaseModel):
    default_model_tier_max: int | None = None
    configured_models: list[str] | None = None
    feature_flags: dict[str, bool] | None = None
    agent_defaults: dict | None = None
    branding: dict | None = None


@router.put("")
async def update_settings(
    payload: SettingsUpdate,
    org_ctx: OrganizationContext = Depends(require_org_member),
):
    """Update organization settings (non-key fields)."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

        if not settings:
            settings = OrganizationSettings(id=uuid4(), organization_id=org_id, created_at=utcnow(), updated_at=utcnow())
            session.add(settings)

        changes = {}
        if payload.default_model_tier_max is not None:
            changes["default_model_tier_max"] = {"old": settings.default_model_tier_max, "new": payload.default_model_tier_max}
            settings.default_model_tier_max = payload.default_model_tier_max
        if payload.configured_models is not None:
            settings.configured_models_json = json.dumps(payload.configured_models)
            changes["configured_models"] = True
        if payload.feature_flags is not None:
            settings.feature_flags_json = json.dumps(payload.feature_flags)
            changes["feature_flags"] = True
        if payload.agent_defaults is not None:
            settings.agent_defaults_json = json.dumps(payload.agent_defaults)
            changes["agent_defaults"] = True
        if payload.branding is not None:
            settings.branding_json = json.dumps(payload.branding)
            changes["branding"] = True

        settings.updated_at = utcnow()
        await session.commit()

    await log_audit(
        org_id, "settings.update",
        user_id=org_ctx.member.user_id,
        resource_type="organization_settings",
        details={"changed_fields": list(changes.keys())},
    )

    return {"ok": True}


class KeyPayload(BaseModel):
    key: str


@router.post("/openrouter-key")
async def set_openrouter_key(
    payload: KeyPayload,
    org_ctx: OrganizationContext = Depends(require_org_member),
):
    """Store a BYOK OpenRouter API key (Fernet-encrypted)."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

        if not settings:
            settings = OrganizationSettings(id=uuid4(), organization_id=org_id, created_at=utcnow(), updated_at=utcnow())
            session.add(settings)

        settings.openrouter_api_key_encrypted = encrypt_token(payload.key)
        settings.updated_at = utcnow()
        await session.commit()

    await log_audit(
        org_id, "key.set",
        user_id=org_ctx.member.user_id,
        resource_type="organization_settings",
        details={"key_type": "openrouter_api_key"},
    )

    return {"ok": True}


@router.delete("/openrouter-key")
async def remove_openrouter_key(
    org_ctx: OrganizationContext = Depends(require_org_member),
):
    """Remove BYOK OpenRouter key, reverting to platform default."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

        if settings and settings.openrouter_api_key_encrypted:
            settings.openrouter_api_key_encrypted = None
            settings.updated_at = utcnow()
            await session.commit()

    await log_audit(
        org_id, "key.remove",
        user_id=org_ctx.member.user_id,
        resource_type="organization_settings",
        details={"key_type": "openrouter_api_key"},
    )

    return {"ok": True}


@router.post("/management-key")
async def set_management_key(
    payload: KeyPayload,
    org_ctx: OrganizationContext = Depends(require_org_member),
):
    """Store a BYOK OpenRouter management key (Fernet-encrypted)."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

        if not settings:
            settings = OrganizationSettings(id=uuid4(), organization_id=org_id, created_at=utcnow(), updated_at=utcnow())
            session.add(settings)

        settings.openrouter_management_key_encrypted = encrypt_token(payload.key)
        settings.updated_at = utcnow()
        await session.commit()

    await log_audit(
        org_id, "key.set",
        user_id=org_ctx.member.user_id,
        resource_type="organization_settings",
        details={"key_type": "openrouter_management_key"},
    )

    return {"ok": True}


@router.delete("/management-key")
async def remove_management_key(
    org_ctx: OrganizationContext = Depends(require_org_member),
):
    """Remove BYOK management key, reverting to platform default."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

        if settings and settings.openrouter_management_key_encrypted:
            settings.openrouter_management_key_encrypted = None
            settings.updated_at = utcnow()
            await session.commit()

    await log_audit(
        org_id, "key.remove",
        user_id=org_ctx.member.user_id,
        resource_type="organization_settings",
        details={"key_type": "openrouter_management_key"},
    )

    return {"ok": True}


@router.get("/audit-log")
async def get_audit_log(
    org_ctx: OrganizationContext = Depends(require_org_member),
    limit: int = 50,
):
    """Get recent audit log entries for the organization."""
    from app.models.audit_log import AuditLog

    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(AuditLog)
            .where(AuditLog.organization_id == org_id)
            .order_by(AuditLog.created_at.desc())  # type: ignore[union-attr]
            .limit(limit)
        )
        rows = result.scalars().all()

    return {
        "entries": [
            {
                "id": str(r.id),
                "action": r.action,
                "resource_type": r.resource_type,
                "resource_id": str(r.resource_id) if r.resource_id else None,
                "details": r.details,
                "user_id": str(r.user_id) if r.user_id else None,
                "ip_address": r.ip_address,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }
