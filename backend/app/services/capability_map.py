"""Per-org capability map — composite read-only deployment snapshot (items 144 + 145).

One aggregation, two audiences:

- ``redacted=False`` (item 144) — the owner/admin "what is this org made of" view.
  Includes the skills section (the first MC rendering of ``registry.yml`` skill
  assignment beyond the item-120 drift card) and full integration detail.

- ``redacted=True`` (item 145) — the member/client-facing "Your platform" view.
  **Deliberately omits the skills section entirely** — skills are the proprietary
  layer (release packaging already excludes them from client deliverables, and
  skill names can leak operational detail, e.g. ``bedroom-tscm-baseline``).
  Capabilities are surfaced via feature flags mapped to friendly labels instead,
  integration detail is reduced to provider + connected, and a trust-posture
  block makes the trust-engineered constraints (HITL on sends, auto-post-never,
  tenant isolation) visible features rather than verbal promises.

Live sources only (no hand-maintained lists):
- agents       → ``agents`` table (via the org's gateway)
- skills       → ``gateways/registry.yml`` parsed by ``skill_drift.parse_registry``
- crons        → ``cron.list`` RPC through the ``gateway_resolver`` chokepoint
                 (same path as item 142; never the structurally-dead disk read)
- integrations → per-provider connection tables
- flags        → ``OrganizationSettings.feature_flags``
- template     → ``OrganizationSettings.industry_template_id`` + template catalog

This module performs ZERO mutations — read aggregation only.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlmodel import select

from app.core.logging import get_logger
from app.models.agents import Agent
from app.models.email_accounts import EmailAccount
from app.models.gateways import Gateway
from app.models.google_calendar_connection import GoogleCalendarConnection
from app.models.microsoft_connection import MicrosoftConnection
from app.models.organization_settings import OrganizationSettings
from app.models.wecom_connection import WeComConnection
from app.services.industry_templates import get_template
from app.services.openclaw.gateway_resolver import optional_gateway_client_config
from app.services.openclaw.gateway_rpc import OpenClawGatewayError, openclaw_call
from app.services.skill_drift import parse_registry

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.organizations import Organization

logger = get_logger(__name__)

# Feature flags as client-facing capability labels. Only flags that map to a
# business-relevant capability are exposed in the redacted (client) view —
# internal/dev flags (paper_trading, pentest, observability, …) are intentionally
# absent so the client surface reads as a product, not an internals dump.
_CLIENT_CAPABILITY_LABELS: dict[str, tuple[str, str]] = {
    "email": ("Email management", "AI-assisted inbox triage, drafting, and organization"),
    "cron_jobs": ("Scheduled automation", "Recurring tasks that run on a schedule you control"),
    "document_generation": ("Document generation", "Branded proposals, reports, and PDFs on demand"),
    "bookkeeping": ("Invoicing & bookkeeping", "Invoice creation, delivery, and reconciliation"),
    "microsoft_graph": ("Microsoft 365", "Outlook mail, calendar, and OneDrive integration"),
    "google_calendar": ("Calendar", "Calendar scheduling and event management"),
    "agent_memory": ("Long-term memory", "Your AI remembers prior context across sessions"),
    "org_context": ("Knowledge base", "Your reference documents ground the AI's answers"),
    "regulatory": ("Regulatory tracking", "Track regulatory requirements and approvals"),
    "grants_tracker": ("Grants tracking", "Monitor grant opportunities and applications"),
    "ecosystem_intel": ("Ecosystem intelligence", "Curated tracking of relevant tools and trends"),
    "wechat": ("WeCom / WeChat", "Enterprise WeChat messaging integration"),
    "cost_tracker": ("Usage transparency", "See exactly what your AI spend looks like"),
}


def _agent_role(agent: Agent) -> str | None:
    """Extract a plain-language role from an agent's identity profile, if present."""
    profile = agent.identity_profile
    if not isinstance(profile, dict):
        return None
    for key in ("role", "title", "tagline", "summary"):
        value = profile.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


async def _collect_agents(session: AsyncSession, gateway_ids: list[Any]) -> list[dict[str, Any]]:
    """Agents for the org, via the org's gateway(s). Live source: agents table."""
    if not gateway_ids:
        return []
    result = await session.execute(
        select(Agent).where(Agent.gateway_id.in_(gateway_ids))  # type: ignore[attr-defined]
    )
    agents = result.scalars().all()
    out: list[dict[str, Any]] = []
    for agent in sorted(agents, key=lambda a: (not a.is_board_lead, a.name.lower())):
        out.append(
            {
                "name": agent.name,
                "role": _agent_role(agent),
                "status": agent.status,
                "is_lead": agent.is_board_lead,
            }
        )
    return out


def _collect_skills(slug: str | None) -> dict[str, Any] | None:
    """Per-org skills from registry.yml. Returns None when the registry is unreadable.

    Only called for the full (non-redacted) view — skills are never surfaced to
    the client-facing surface.
    """
    if not slug:
        return None
    registry_path = Path(os.environ.get("SKILL_REGISTRY_PATH", "/app/registry.yml"))
    if not (registry_path.exists() and registry_path.is_file()):
        return None
    try:
        content = registry_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("capability_map.registry_read_failed path=%s error=%s", registry_path, exc)
        return None
    shared, per_org = parse_registry(content)
    org_skills = sorted(per_org.get(slug, set()))
    return {
        "shared": sorted(shared),
        "shared_count": len(shared),
        "org_specific": org_skills,
        "org_specific_count": len(org_skills),
        "total": len(shared) + len(org_skills),
    }


def _format_schedule(schedule: Any) -> str | None:
    """Render a gateway cron schedule dict as a compact human string."""
    if not isinstance(schedule, dict):
        return None
    kind = schedule.get("kind")
    expr = schedule.get("expr")
    tz = schedule.get("tz")
    if kind == "cron" and expr:
        return f"{expr} ({tz})" if tz else str(expr)
    if expr:
        return str(expr)
    return str(kind) if kind else None


async def _collect_crons(gateway: Gateway | None, *, redacted: bool) -> dict[str, Any]:
    """Cron jobs via the cron.list RPC. Live source: gateway, never the dead disk path."""
    if gateway is None:
        return {"reachable": False, "jobs": []}
    config = optional_gateway_client_config(gateway)
    if config is None:
        return {"reachable": False, "jobs": []}
    try:
        result = await openclaw_call(
            "cron.list", None, config=config, org_id=str(gateway.organization_id)
        )
    except OpenClawGatewayError as exc:
        logger.warning(
            "capability_map.cron_list_failed org=%s error=%s", gateway.organization_id, exc
        )
        return {"reachable": False, "jobs": []}

    if isinstance(result, dict) and "jobs" in result:
        raw_jobs = result["jobs"]
    elif isinstance(result, list):
        raw_jobs = result
    else:
        raw_jobs = []
    if not isinstance(raw_jobs, list):
        raw_jobs = []

    jobs: list[dict[str, Any]] = []
    for job in raw_jobs:
        if not isinstance(job, dict):
            continue
        state = job.get("state") if isinstance(job.get("state"), dict) else {}
        entry: dict[str, Any] = {
            "name": job.get("name", ""),
            "schedule": _format_schedule(job.get("schedule")),
            "enabled": bool(job.get("enabled", True)),
        }
        if not redacted:
            # Full view: surface last-run status for the operator. The client view
            # omits it — a stale "error" badge erodes trust and the detail is infra.
            entry["last_status"] = state.get("lastRunStatus")
        jobs.append(entry)
    return {"reachable": True, "jobs": jobs}


async def _collect_integrations(
    session: AsyncSession, org_id: Any, *, redacted: bool
) -> list[dict[str, Any]]:
    """Connected services from per-provider tables. Live source: connection tables."""
    integrations: list[dict[str, Any]] = []

    email_rows = (
        (await session.execute(select(EmailAccount).where(EmailAccount.organization_id == org_id)))
        .scalars()
        .all()
    )
    for acct in email_rows:
        entry: dict[str, Any] = {
            "type": "email",
            "provider": acct.provider,
            "connected": bool(acct.sync_enabled),
        }
        if not redacted:
            entry.update(
                {
                    "address": acct.email_address,
                    "visibility": acct.visibility,
                    "agent_access": acct.agent_access,
                    "last_sync_at": acct.last_sync_at.isoformat() if acct.last_sync_at else None,
                }
            )
        integrations.append(entry)

    ms_rows = (
        (
            await session.execute(
                select(MicrosoftConnection).where(MicrosoftConnection.organization_id == org_id)
            )
        )
        .scalars()
        .all()
    )
    for conn in ms_rows:
        entry = {
            "type": "microsoft_graph",
            "provider": "microsoft",
            "connected": bool(conn.is_active),
        }
        if not redacted:
            entry["address"] = conn.email_address
        integrations.append(entry)

    gcal_rows = (
        (
            await session.execute(
                select(GoogleCalendarConnection).where(
                    GoogleCalendarConnection.organization_id == org_id
                )
            )
        )
        .scalars()
        .all()
    )
    for conn in gcal_rows:
        entry = {
            "type": "google_calendar",
            "provider": "google",
            "connected": bool(conn.is_active),
        }
        if not redacted:
            entry.update({"address": conn.email_address, "visibility": conn.visibility})
        integrations.append(entry)

    wecom_rows = (
        (
            await session.execute(
                select(WeComConnection).where(WeComConnection.organization_id == org_id)
            )
        )
        .scalars()
        .all()
    )
    for conn in wecom_rows:
        entry = {
            "type": "wecom",
            "provider": "wecom",
            "connected": bool(conn.is_active),
        }
        if not redacted:
            entry["label"] = conn.label
        integrations.append(entry)

    return integrations


def _client_capabilities(flags: dict[str, bool]) -> list[dict[str, str]]:
    """Map enabled flags to friendly client-facing capability labels."""
    caps: list[dict[str, str]] = []
    for flag, (label, description) in _CLIENT_CAPABILITY_LABELS.items():
        if flags.get(flag):
            caps.append({"label": label, "description": description})
    return caps


def _trust_posture(flags: dict[str, bool], data_policy: dict[str, Any]) -> dict[str, list[str]]:
    """Derive the trust/HITL block for the client-facing view.

    These statements are a mix of architectural guarantees (auto-post-never,
    HITL on all sends, tenant isolation — load-bearing platform invariants) and
    flag/policy-derived facts. They make the trust-engineered constraints visible
    instead of narrated in a demo script.
    """
    human_approval = [
        "Every outbound email is drafted for your review — nothing sends without human approval.",
        "Social media posts are never auto-published; you approve each one.",
    ]
    if flags.get("approvals"):
        human_approval.append(
            "Agent actions that need sign-off are queued in an approval workflow for you."
        )

    boundaries = [
        "Your AI cannot send email, post publicly, or take irreversible actions on its own.",
        "Your data is isolated to your organization — it is never shared across tenants.",
    ]
    if flags.get("email"):
        boundaries.append(
            "You control which inboxes the AI can access — mark any inbox private to exclude it."
        )

    data_protection = []
    level = data_policy.get("redaction_level")
    if isinstance(level, str) and level:
        data_protection.append(
            f"Sensitive data (credentials, card numbers, IDs) is stripped before reaching AI models (level: {level})."
        )
    if data_policy.get("allow_email_content_to_llm") is False:
        data_protection.append("Email message bodies are withheld from AI models by your policy.")
    if not data_protection:
        data_protection.append("Sensitive data is redacted before reaching AI models.")

    return {
        "human_approval": human_approval,
        "boundaries": boundaries,
        "data_protection": data_protection,
    }


async def build_capability_map(
    session: AsyncSession, org: Organization, *, redacted: bool
) -> dict[str, Any]:
    """Assemble the per-org capability map from live sources.

    Args:
        session: DB session.
        org: The organization to snapshot.
        redacted: When True, produce the client-facing view (no skills, no infra
            detail, friendly capability labels, trust-posture block). When False,
            produce the full owner/admin view.
    """
    org_id = org.id
    slug = getattr(org, "slug", None)

    settings = (
        (
            await session.execute(
                select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
            )
        )
        .scalars()
        .first()
    )
    flags = settings.feature_flags if settings else {}
    data_policy = settings.data_policy if settings else {}
    template_id = settings.industry_template_id if settings else None

    gateways = (
        (await session.execute(select(Gateway).where(Gateway.organization_id == org_id)))
        .scalars()
        .all()
    )
    gateway = gateways[0] if gateways else None
    gateway_ids = [gw.id for gw in gateways]

    template_obj = get_template(template_id) if template_id else None
    template_block = (
        {"id": template_id, "name": template_obj.name if template_obj else template_id}
        if template_id
        else None
    )

    result: dict[str, Any] = {
        "org": {"id": str(org_id), "name": org.name, "slug": slug},
        "agents": await _collect_agents(session, gateway_ids),
        "crons": await _collect_crons(gateway, redacted=redacted),
        "integrations": await _collect_integrations(session, org_id, redacted=redacted),
        "industry_template": template_block,
    }

    if redacted:
        result["capabilities"] = _client_capabilities(flags)
        result["trust_posture"] = _trust_posture(flags, data_policy)
    else:
        result["skills"] = _collect_skills(slug)
        result["feature_flags"] = flags

    return result
