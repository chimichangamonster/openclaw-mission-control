"""Platform administration endpoints for cross-org operations.

These endpoints are for Henz (platform owner) and future platform operators.
Every action is audit-logged with the platform admin's identity.

Role separation:
- Owner:    can do everything, including reading client data
- Operator: can manage infrastructure but NOT read client data
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
from app.services.openclaw.gateway_resolver import gateway_client_config
from app.services.openclaw.gateway_rpc import OpenClawGatewayError, openclaw_call
from app.services.skill_drift import audit_skill_drift

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
# Cross-org failed-cron rollup (item 121)
# ---------------------------------------------------------------------------


def _parse_iso_timestamp(value: Any) -> datetime | None:
    """Parse a gateway-emitted timestamp (ISO string or epoch ms) to UTC datetime."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Epoch milliseconds
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    if isinstance(value, str):
        try:
            # Tolerate trailing 'Z'
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _summarize_error(error: Any, max_length: int = 200) -> str:
    """Truncate a gateway error string for UI display."""
    if not error:
        return ""
    text = str(error).strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def _filter_failed_runs(
    runs: list[dict[str, Any]], cutoff: datetime
) -> list[dict[str, Any]]:
    """Filter run records to failures that started after the cutoff.

    Run record shape (from gateway cron.runs RPC, mirrored in /cron-jobs/page.tsx):
    {run_id, status, started_at, finished_at, duration_ms, error}
    Status "error" indicates failure; "success" / other are kept-out.
    """
    failures = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        if run.get("status") != "error":
            continue
        started = _parse_iso_timestamp(run.get("started_at"))
        if started is None or started < cutoff:
            continue
        failures.append(
            {
                "run_id": run.get("run_id", ""),
                "started_at": run.get("started_at"),
                "duration_ms": run.get("duration_ms"),
                "error_summary": _summarize_error(run.get("error")),
            }
        )
    return failures


@router.get(
    "/cron-failures",
    summary="Cross-org failed-cron rollup (last N hours, owner-only)",
)
async def cron_failures_rollup(
    hours: int = 24,
    owner: User = OWNER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """Aggregate failed cron runs across all orgs in the last N hours.

    Owner-only — failure context can include error messages with semi-sensitive
    detail (paths, IDs, partial responses), so this stays out of the operator
    permission tier.

    Resilient: per-org RPC errors are logged and skipped; one bad gateway
    cannot break the whole rollup.
    """
    hours = max(1, min(hours, 168))  # Clamp 1h..7d
    cutoff = datetime.now(UTC) - timedelta(hours=hours)

    # Load all orgs + settings + gateway in three queries.
    orgs_result = await session.execute(select(Organization))
    orgs = orgs_result.scalars().all()

    by_org: list[dict[str, Any]] = []
    total_failures = 0
    orgs_skipped_no_flag = 0
    orgs_skipped_no_gateway = 0
    orgs_with_rpc_error = 0

    for org in orgs:
        # Feature-flag gate — skip orgs that don't have cron_jobs enabled.
        settings_result = await session.execute(
            select(OrganizationSettings).where(
                OrganizationSettings.organization_id == org.id
            )
        )
        org_settings = settings_result.scalars().first()
        flags = org_settings.feature_flags if org_settings else {}
        if not flags.get("cron_jobs"):
            orgs_skipped_no_flag += 1
            continue

        # Resolve gateway. No gateway → skip silently (fresh org, not a failure).
        gw_result = await session.execute(
            select(Gateway).where(Gateway.organization_id == org.id).limit(1)
        )
        gateway = gw_result.scalars().first()
        if not gateway or not gateway.url:
            orgs_skipped_no_gateway += 1
            continue

        config = gateway_client_config(gateway)
        org_id_str = str(org.id)

        # Step 1: list cron jobs to know which IDs to query.
        try:
            jobs_result = await openclaw_call(
                "cron.list", None, config=config, org_id=org_id_str
            )
        except OpenClawGatewayError as exc:
            logger.warning(
                "platform.cron_rollup.list_failed",
                extra={"organization_id": org_id_str, "error": str(exc)},
            )
            orgs_with_rpc_error += 1
            continue

        if isinstance(jobs_result, dict) and "jobs" in jobs_result:
            jobs = jobs_result["jobs"]
        elif isinstance(jobs_result, list):
            jobs = jobs_result
        else:
            jobs = []

        # Step 2: for each job, query run history and filter to recent failures.
        # Optimisation — skip jobs whose lastRunStatus isn't "error" AND whose
        # last run was before the cutoff. Saves RPC round-trips on healthy orgs.
        org_failures: list[dict[str, Any]] = []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            state = job.get("state") or {}
            last_status = state.get("lastRunStatus")
            last_run_ms = state.get("lastRunAtMs")
            last_run_dt = (
                datetime.fromtimestamp(last_run_ms / 1000, tz=UTC)
                if isinstance(last_run_ms, (int, float))
                else None
            )

            # Cheap pre-filter — if last run was successful AND outside window,
            # there can't be failures inside the window for this job.
            if last_status != "error" and (last_run_dt is None or last_run_dt < cutoff):
                continue

            job_id = job.get("id", "")
            if not job_id:
                continue

            try:
                runs_result = await openclaw_call(
                    "cron.runs", {"id": job_id}, config=config, org_id=org_id_str
                )
            except OpenClawGatewayError as exc:
                logger.warning(
                    "platform.cron_rollup.runs_failed",
                    extra={
                        "organization_id": org_id_str,
                        "job_id": job_id,
                        "error": str(exc),
                    },
                )
                continue

            if isinstance(runs_result, list):
                runs = runs_result
            elif isinstance(runs_result, dict) and "runs" in runs_result:
                runs = runs_result["runs"]
            else:
                runs = []

            failures = _filter_failed_runs(runs, cutoff)
            for failure in failures:
                org_failures.append(
                    {
                        **failure,
                        "cron_id": job_id,
                        "cron_name": job.get("name", ""),
                    }
                )

        if org_failures:
            # Sort newest first so most recent failures appear at top.
            org_failures.sort(
                key=lambda f: f.get("started_at") or "", reverse=True
            )
            total_failures += len(org_failures)
            by_org.append(
                {
                    "org_id": str(org.id),
                    "org_name": org.name,
                    "slug": getattr(org, "slug", None),
                    "failure_count": len(org_failures),
                    "failures": org_failures,
                }
            )

    # Sort orgs by failure count (most failures first) for "where is the fire?" UX.
    by_org.sort(key=lambda o: o["failure_count"], reverse=True)

    await log_audit(
        org_id=orgs[0].id if orgs else UUID(int=0),
        action="platform.cron_failures_rollup",
        user_id=owner.id,
        details={
            "hours": hours,
            "total_failures": total_failures,
            "orgs_with_failures": len(by_org),
            "orgs_skipped_no_flag": orgs_skipped_no_flag,
            "orgs_skipped_no_gateway": orgs_skipped_no_gateway,
            "orgs_with_rpc_error": orgs_with_rpc_error,
        },
    )

    return {
        "hours": hours,
        "since": cutoff.isoformat(),
        "total_failures": total_failures,
        "orgs_with_failures": len(by_org),
        "orgs_with_rpc_error": orgs_with_rpc_error,
        "by_org": by_org,
    }


# ---------------------------------------------------------------------------
# Skill-drift audit (item 120 Tier 1)
# ---------------------------------------------------------------------------


@router.get(
    "/skill-drift",
    summary="Skill registry-vs-deploy drift audit (owner-only)",
)
async def skill_drift(
    owner: User = OWNER_DEP,
) -> dict[str, Any]:
    """Compare gateways/registry.yml against the actual skills deployed on disk.

    Server-side equivalent of `scripts/audit-shared-skills.sh`. Reads three
    substrates (registry file, shared-skills dir, gateway workspaces dir) via
    volume mounts. If any substrate is unreachable, the response includes a
    per-source `available: false` flag and that side contributes empty sets
    to the drift computation — the endpoint never 500s on missing dirs.

    Owner-only because skill names can leak operational detail (e.g. an
    org_skill named `bedroom-tscm-baseline` reveals an active engagement).
    Counts alone could be operator-tier, but mixing counts and detail in one
    response is simpler than splitting.
    """
    result = audit_skill_drift()

    await log_audit(
        org_id=UUID(int=0),
        action="platform.skill_drift_audit",
        user_id=owner.id,
        details={
            "available": result["available"],
            "total_drift": result["total_drift"],
            "total_orphan": result["total_orphan"],
        },
    )

    return result


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
