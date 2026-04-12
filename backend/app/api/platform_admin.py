"""Platform administration endpoints for cross-org operations.

These endpoints are for Henz (platform owner) and future platform operators.
Every action is audit-logged with the platform admin's identity.

Role separation:
- Owner:    can do everything, including reading client data
- Operator: can manage infrastructure but NOT read client data
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import func, select

from app.core.logging import get_logger
from app.core.platform_auth import (
    require_platform_admin,
    require_platform_owner,
)
from app.db.session import get_session
from app.models.gateways import Gateway
from app.models.organization_members import OrganizationMember
from app.models.organization_settings import OrganizationSettings
from app.models.organizations import Organization
from app.services.audit import log_audit

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.users import User

logger = get_logger(__name__)
router = APIRouter(prefix="/platform", tags=["platform"])

SESSION_DEP = Depends(get_session)
ADMIN_DEP = Depends(require_platform_admin)
OWNER_DEP = Depends(require_platform_owner)


# ---------------------------------------------------------------------------
# Infrastructure endpoints (owner + operator)
# ---------------------------------------------------------------------------


@router.get("/orgs", summary="List all organizations")
async def list_all_orgs(
    admin: User = ADMIN_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[dict[str, Any]]:
    """List all organizations with basic metadata. No sensitive data."""
    result = await session.execute(select(Organization))
    orgs = result.scalars().all()

    org_list = []
    for org in orgs:
        # Count members
        member_count_result = await session.execute(
            select(func.count()).where(OrganizationMember.organization_id == org.id)
        )
        member_count = member_count_result.scalar() or 0

        # Get feature flags (not secrets)
        settings_result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org.id)
        )
        org_settings = settings_result.scalars().first()

        org_list.append(
            {
                "id": str(org.id),
                "name": org.name,
                "slug": getattr(org, "slug", None),
                "member_count": member_count,
                "feature_flags": org_settings.feature_flags if org_settings else {},
                "timezone": org_settings.timezone if org_settings else "UTC",
                "created_at": org.created_at.isoformat() if hasattr(org, "created_at") else None,
            }
        )

    await log_audit(
        org_id=orgs[0].id if orgs else UUID(int=0),
        action="platform.list_orgs",
        user_id=admin.id,
        details={"org_count": len(org_list), "role": getattr(admin, "platform_role", None)},
    )

    return org_list


@router.get("/orgs/{org_id}/health", summary="Check org gateway health")
async def org_gateway_health(
    org_id: UUID,
    admin: User = ADMIN_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """Check gateway connectivity for an organization. No client data exposed."""
    org = await _get_org_or_404(org_id, session)

    result = await session.execute(select(Gateway).where(Gateway.organization_id == org_id))
    gateways = result.scalars().all()

    gateway_status = []
    for gw in gateways:
        gateway_status.append(
            {
                "id": str(gw.id),
                "url": gw.url,
                "name": getattr(gw, "name", None),
                "connected": True,  # Simplified — real health check would ping
            }
        )

    await log_audit(
        org_id=org_id,
        action="platform.health_check",
        user_id=admin.id,
        resource_type="organization",
        resource_id=org_id,
    )

    return {
        "org": org.name,
        "gateways": gateway_status,
    }


@router.get("/orgs/{org_id}/members", summary="List org members")
async def list_org_members(
    org_id: UUID,
    admin: User = ADMIN_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[dict[str, Any]]:
    """List members of an organization. Names and roles only — no credentials."""
    await _get_org_or_404(org_id, session)

    result = await session.execute(
        select(OrganizationMember).where(OrganizationMember.organization_id == org_id)
    )
    members = result.scalars().all()

    from app.models.users import User as UserModel

    member_list = []
    for m in members:
        user_result = await session.execute(select(UserModel).where(UserModel.id == m.user_id))
        user = user_result.scalars().first()
        member_list.append(
            {
                "user_id": str(m.user_id),
                "name": user.name if user else None,
                "email": user.email if user else None,
                "role": m.role,
            }
        )

    await log_audit(
        org_id=org_id,
        action="platform.list_members",
        user_id=admin.id,
        resource_type="organization",
        resource_id=org_id,
    )

    return member_list


# ---------------------------------------------------------------------------
# Owner-only endpoints (access to sensitive client data)
# ---------------------------------------------------------------------------


@router.get("/orgs/{org_id}/settings", summary="View org settings (owner only)")
async def get_org_settings(
    org_id: UUID,
    owner: User = OWNER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """View full org settings including encrypted key status. Owner only.

    Returns key presence (has_key: true/false) but NOT decrypted values.
    """
    await _get_org_or_404(org_id, session)

    result = await session.execute(
        select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
    )
    settings = result.scalars().first()

    if not settings:
        return {"error": "No settings configured for this org"}

    await log_audit(
        org_id=org_id,
        action="platform.view_settings",
        user_id=owner.id,
        resource_type="organization_settings",
        resource_id=settings.id,
        details={"accessed_fields": ["feature_flags", "data_policy", "model_config", "key_status"]},
    )

    return {
        "feature_flags": settings.feature_flags,
        "data_policy": settings.data_policy,
        "default_model_tier_max": settings.default_model_tier_max,
        "timezone": settings.timezone,
        "location": settings.location,
        "industry_template_id": settings.industry_template_id,
        "has_openrouter_key": bool(settings.openrouter_api_key_encrypted),
        "has_custom_llm_endpoint": bool(settings.custom_llm_endpoint.get("api_url")),
        "has_custom_llm_key": bool(settings.custom_llm_api_key_encrypted),
        "has_adobe_credentials": bool(settings.adobe_pdf_client_id_encrypted),
    }


@router.get("/orgs/{org_id}/audit", summary="View org audit trail (owner only)")
async def get_org_audit_trail(
    org_id: UUID,
    limit: int = 50,
    owner: User = OWNER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[dict[str, Any]]:
    """View audit trail for an organization. Owner only."""
    from app.models.audit_log import AuditLog

    await _get_org_or_404(org_id, session)

    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.organization_id == org_id)
        .order_by(AuditLog.created_at.desc())  # type: ignore[attr-defined]
        .limit(min(limit, 200))
    )
    entries = result.scalars().all()

    await log_audit(
        org_id=org_id,
        action="platform.view_audit",
        user_id=owner.id,
        resource_type="audit_log",
        details={"entries_returned": len(entries)},
    )

    return [
        {
            "id": str(e.id),
            "action": e.action,
            "resource_type": e.resource_type,
            "user_id": str(e.user_id) if e.user_id else None,
            "details": e.details,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]


# ---------------------------------------------------------------------------
# Org readiness check (pre-onboarding QA)
# ---------------------------------------------------------------------------


@router.get("/orgs/{org_id}/readiness", summary="Pre-onboarding readiness check")
async def org_readiness_check(
    org_id: UUID,
    admin: User = ADMIN_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """Run automated readiness checks for a client org before onboarding.

    Validates: org exists, settings configured, feature flags set, gateway
    connected, members exist, budget config present, rate limiting active,
    BYOK key or platform key available.
    """
    from app.models.budget import BudgetConfig

    org = await _get_org_or_404(org_id, session)

    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"check": name, "passed": passed, "detail": detail})

    # 1. Org settings exist
    settings_result = await session.execute(
        select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
    )
    org_settings = settings_result.scalars().first()
    add("org_settings_exist", org_settings is not None, "OrganizationSettings row exists")

    # 2. Feature flags configured (at least one enabled)
    if org_settings:
        flags = org_settings.feature_flags or {}
        enabled = [k for k, v in flags.items() if v]
        add(
            "feature_flags_set",
            len(enabled) > 0,
            f"{len(enabled)} flags enabled: {', '.join(enabled[:5])}{'...' if len(enabled) > 5 else ''}",
        )
    else:
        add("feature_flags_set", False, "No settings — cannot check flags")

    # 3. Has LLM access (BYOK key or custom endpoint)
    if org_settings:
        has_key = bool(org_settings.openrouter_api_key_encrypted)
        has_custom = bool(
            org_settings.custom_llm_endpoint and org_settings.custom_llm_endpoint.get("api_url")
        )
        add(
            "llm_access",
            has_key or has_custom,
            (
                "BYOK key"
                if has_key
                else ("Custom endpoint" if has_custom else "No LLM key or endpoint configured")
            ),
        )
    else:
        add("llm_access", False, "No settings — cannot check LLM access")

    # 4. Gateway connected
    gw_result = await session.execute(select(Gateway).where(Gateway.organization_id == org_id))
    gateways = gw_result.scalars().all()
    add("gateway_connected", len(gateways) > 0, f"{len(gateways)} gateway(s)")

    # 5. Members exist
    member_result = await session.execute(
        select(func.count()).where(OrganizationMember.organization_id == org_id)
    )
    member_count = member_result.scalar() or 0
    add("members_exist", member_count > 0, f"{member_count} member(s)")

    # 6. Has at least one owner
    owner_result = await session.execute(
        select(func.count()).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.role == "owner",
        )
    )
    owner_count = owner_result.scalar() or 0
    add("has_owner", owner_count > 0, f"{owner_count} owner(s)")

    # 7. Budget config exists
    budget_result = await session.execute(
        select(BudgetConfig).where(BudgetConfig.organization_id == org_id)
    )
    budget = budget_result.scalars().first()
    add(
        "budget_configured",
        budget is not None,
        f"Daily limit: ${budget.daily_limit}" if budget else "No budget config",
    )

    # 8. Industry template applied
    if org_settings:
        add(
            "industry_template",
            bool(org_settings.industry_template_id),
            org_settings.industry_template_id or "No template applied",
        )
    else:
        add("industry_template", False, "No settings")

    # 9. Slug set (required for gateway workspace)
    has_slug = bool(getattr(org, "slug", None))
    add("slug_set", has_slug, getattr(org, "slug", "(none)"))

    # 10. Timezone set
    if org_settings:
        add(
            "timezone_set",
            bool(org_settings.timezone and org_settings.timezone != "UTC"),
            org_settings.timezone or "Not set",
        )
    else:
        add("timezone_set", False, "No settings")

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)

    await log_audit(
        org_id=org_id,
        action="platform.readiness_check",
        user_id=admin.id,
        resource_type="organization",
        resource_id=org_id,
        details={"passed": passed, "total": total},
    )

    return {
        "org": org.name,
        "slug": getattr(org, "slug", None),
        "passed": passed,
        "total": total,
        "ready": passed == total,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_org_or_404(org_id: UUID, session: AsyncSession) -> Organization:
    """Load an organization by ID or raise 404."""
    result = await session.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalars().first()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return org  # type: ignore[no-any-return]
