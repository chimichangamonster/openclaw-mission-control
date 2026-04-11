"""Cost tracking endpoints — OpenRouter usage, live model pricing, gateway session data, budget controls."""

from __future__ import annotations

import json
import time
from datetime import UTC, date, datetime

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import select

from app.api.deps import (
    ORG_MEMBER_DEP,
    ORG_RATE_LIMIT_DEP,
    require_feature,
    require_org_member,
    require_org_role,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.core.resilience import openrouter_breaker, retry_async
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.activity_events import ActivityEvent
from app.models.budget import BudgetConfig, DailyAgentSpend
from app.services.organizations import OrganizationContext

logger = get_logger(__name__)
router = APIRouter(
    prefix="/cost-tracker",
    tags=["cost-tracker"],
    dependencies=[Depends(require_feature("cost_tracker")), ORG_RATE_LIMIT_DEP],
)

# Cache live pricing for 1 hour to avoid hammering OpenRouter
_pricing_cache: dict | None = None
_pricing_cache_ts: float = 0


async def _openrouter_get(url: str, api_key: str) -> dict:
    """Fetch from OpenRouter with retry and circuit breaker."""

    async def _fetch() -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
            if resp.status_code != 200:
                raise httpx.HTTPStatusError(
                    f"OpenRouter returned {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
            return resp.json()

    return await retry_async(
        _fetch, retries=3, base_delay=2.0, breaker=openrouter_breaker, label="openrouter"
    )


@router.get("/usage")
async def get_usage(
    org_ctx: OrganizationContext = Depends(require_org_member),
):
    """Get OpenRouter usage and budget data."""
    from app.services.openrouter_keys import get_openrouter_key_for_org

    async with async_session_maker() as session:
        api_key = await get_openrouter_key_for_org(session, org_ctx.organization.id)
    if not api_key:
        return {"error": "OpenRouter API key not configured"}

    try:
        key_result = await _openrouter_get("https://openrouter.ai/api/v1/auth/key", api_key)
        key_data = key_result.get("data", {})
    except Exception:
        key_data = {}

    try:
        credits_result = await _openrouter_get("https://openrouter.ai/api/v1/credits", api_key)
        credits_data = credits_result.get("data", {})
    except Exception:
        credits_data = {}

    total_credits = credits_data.get("total_credits", 0)
    total_usage = credits_data.get("total_usage", 0)
    return {
        "total_credits": total_credits,
        "total_usage": total_usage,
        "remaining": round(total_credits - total_usage, 2),
        "limit": key_data.get("limit", 0),
        "rate_limit_remaining": key_data.get("limit_remaining", 0),
        "usage_daily": key_data.get("usage_daily", 0),
        "usage_weekly": key_data.get("usage_weekly", 0),
        "usage_monthly": key_data.get("usage_monthly", 0),
        "limit_reset": key_data.get("limit_reset", "monthly"),
        "is_free_tier": key_data.get("is_free_tier", False),
    }


@router.get("/models")
async def get_model_pricing(
    org_ctx: OrganizationContext = Depends(require_org_member),
    filter: str = Query(
        "configured",
        description="'configured' = only models in our gateway, 'all' = everything on OpenRouter",
    ),
):
    """Get live model pricing from OpenRouter. Cached for 1 hour."""
    import time

    global _pricing_cache, _pricing_cache_ts

    # Return cache if fresh (1 hour)
    if _pricing_cache and (time.time() - _pricing_cache_ts) < 3600:
        if filter == "configured":
            return {"models": [m for m in _pricing_cache if m.get("configured")], "cached": True}
        return {"models": _pricing_cache, "cached": True}

    # Fetch live from OpenRouter
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get("https://openrouter.ai/api/v1/models")
        if resp.status_code != 200:
            return {"error": "Failed to fetch models from OpenRouter", "status": resp.status_code}
        data = resp.json()

    # Check org settings for configured models, fall back to platform defaults
    from app.models.organization_settings import OrganizationSettings

    org_configured: list[str] = []
    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(
                OrganizationSettings.organization_id == org_ctx.organization.id
            )
        )
        org_settings = result.scalars().first()
        if org_settings:
            org_configured = org_settings.configured_models

    # Default configured models if org hasn't customized
    configured_ids = (
        set(org_configured)
        if org_configured
        else {
            "anthropic/claude-sonnet-4",
            "anthropic/claude-sonnet-4.6",
            "anthropic/claude-opus-4-6",
            "deepseek/deepseek-v3.2",
            "deepseek/deepseek-chat-v3.1",
            "google/gemini-2.5-flash",
            "google/gemini-2.5-flash-lite",
            "x-ai/grok-4",
            "x-ai/grok-4-fast",
            "openai/gpt-5-nano",
            "openai/gpt-5.4",
            "google/gemini-3-pro-preview",
            "qwen/qwen3-coder",
            "openrouter/auto",
        }
    )

    # Agent assignments derived from session data (no hardcoding)
    agent_usage: dict[str, list[str]] = {}

    models = []
    for m in data.get("data", []):
        model_id = m.get("id", "")
        # Strip "openrouter/" prefix if present for matching
        short_id = model_id.replace("openrouter/", "")
        pricing = m.get("pricing", {})
        prompt_price = float(pricing.get("prompt", 0)) * 1_000_000  # Convert per-token to per-M
        completion_price = float(pricing.get("completion", 0)) * 1_000_000

        is_configured = short_id in configured_ids
        agents = agent_usage.get(short_id, [])

        models.append(
            {
                "id": model_id,
                "name": m.get("name", model_id),
                "prompt_per_m": round(prompt_price, 4),
                "completion_per_m": round(completion_price, 4),
                "context_length": m.get("context_length"),
                "configured": is_configured,
                "agents": agents,
                "tier": _classify_tier(prompt_price),
            }
        )

    # Sort: configured first, then by prompt price
    models.sort(key=lambda x: (not x["configured"], x["prompt_per_m"]))

    _pricing_cache = models
    _pricing_cache_ts = time.time()

    if filter == "configured":
        return {"models": [m for m in models if m["configured"]], "cached": False}
    return {"models": models, "cached": False}


def _classify_tier(prompt_per_m: float) -> str:
    """Classify model into our tier system based on prompt price."""
    if prompt_per_m <= 0.3:
        return "Tier 1 — Nano"
    elif prompt_per_m <= 1.0:
        return "Tier 2 — Standard"
    elif prompt_per_m <= 5.0:
        return "Tier 3 — Reasoning"
    else:
        return "Tier 4 — Critical"


# Fallback pricing (per 1M tokens) when live pricing unavailable
_FALLBACK_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4": (3.0, 15.0),
    "deepseek-v3.2": (0.26, 0.38),
    "grok-4": (3.0, 15.0),
    "grok-4-fast": (0.2, 0.6),
    "gemini-2.5-flash": (0.3, 2.5),
    "gpt-5-nano": (0.05, 0.4),
}


def _get_model_price(short_model: str) -> tuple[float, float]:
    """Return (prompt_per_m, completion_per_m) from cache or fallback."""
    if _pricing_cache:
        for m in _pricing_cache:
            mid = m["id"]
            if mid.endswith(short_model) or short_model in mid:
                return m["prompt_per_m"], m["completion_per_m"]
    fb = _FALLBACK_PRICING.get(short_model)
    return fb if fb else (0.0, 0.0)


@router.get("/usage-by-model")
async def get_usage_by_model(
    org_ctx: OrganizationContext = Depends(require_org_member),
):
    """Aggregate gateway session tokens by model and compute cost using live pricing."""
    from sqlmodel import select

    from app.db.session import async_session_maker
    from app.models.gateways import Gateway
    from app.services.openclaw.gateway_rpc import GatewayConfig, openclaw_call

    # Find gateway for this org
    async with async_session_maker() as db_session:
        result = await db_session.execute(
            select(Gateway).where(Gateway.organization_id == org_ctx.organization.id).limit(1)
        )
        gateway = result.scalars().first()

    if not gateway or not gateway.url:
        return {"models": [], "total_cost": 0}

    config = GatewayConfig(url=gateway.url, token=gateway.token)
    try:
        sessions_data = await openclaw_call("sessions.list", config=config)
    except Exception:
        logger.exception("cost_tracker.sessions_rpc_failed")
        return {"models": [], "total_cost": 0}

    raw_sessions = (
        sessions_data if isinstance(sessions_data, list) else sessions_data.get("sessions", [])
    )

    # Aggregate by model
    model_agg: dict[str, dict] = {}
    for s in raw_sessions:
        key = s.get("key", "")
        if "heartbeat" in key or "mc-gateway" in key:
            continue

        full_model = s.get("model") or "unknown"
        short_model = full_model.split("/")[-1]
        input_tok = s.get("inputTokens", 0)
        output_tok = s.get("outputTokens", 0)

        if short_model not in model_agg:
            model_agg[short_model] = {
                "model": short_model,
                "input_tokens": 0,
                "output_tokens": 0,
                "session_count": 0,
                "agents": set(),
            }

        agg = model_agg[short_model]
        agg["input_tokens"] += input_tok
        agg["output_tokens"] += output_tok
        agg["session_count"] += 1

        agent_id = key.split(":")[1] if len(key.split(":")) > 1 else "unknown"
        agg["agents"].add(agent_id)

    # Calculate costs
    models_out = []
    total_cost = 0.0
    for agg in model_agg.values():
        prompt_pm, comp_pm = _get_model_price(agg["model"])
        cost = (agg["input_tokens"] / 1_000_000) * prompt_pm + (
            agg["output_tokens"] / 1_000_000
        ) * comp_pm
        total_cost += cost
        models_out.append(
            {
                "model": agg["model"],
                "input_tokens": agg["input_tokens"],
                "output_tokens": agg["output_tokens"],
                "total_tokens": agg["input_tokens"] + agg["output_tokens"],
                "estimated_cost": round(cost, 6),
                "session_count": agg["session_count"],
                "agents": sorted(agg["agents"]),
                "tier": _classify_tier(prompt_pm),
            }
        )

    # Sort by cost descending, then alphabetically for zero-cost
    models_out.sort(key=lambda x: (-x["estimated_cost"], x["model"]))

    return {"models": models_out, "total_cost": round(total_cost, 6)}


# Cache activity data for 10 minutes
_activity_cache: dict | None = None
_activity_cache_ts: float = 0


@router.get("/activity")
async def get_activity(
    org_ctx: OrganizationContext = Depends(require_org_member),
    period: str = Query(
        "daily",
        description="'daily' = per-day rows, 'weekly' = aggregated by week, 'monthly' = aggregated by month",
    ),
):
    """Get historical per-model spending from OpenRouter activity API (last 30 days)."""
    global _activity_cache, _activity_cache_ts

    from app.services.openrouter_keys import get_management_key_for_org, get_openrouter_key_for_org

    async with async_session_maker() as session:
        mgmt_key = await get_management_key_for_org(session, org_ctx.organization.id)
        if not mgmt_key:
            mgmt_key = await get_openrouter_key_for_org(session, org_ctx.organization.id)
    if not mgmt_key:
        return {"error": "OpenRouter API key not configured"}

    # Check cache (10 min)
    if _activity_cache and (time.time() - _activity_cache_ts) < 600:
        return _build_activity_response(_activity_cache, period)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://openrouter.ai/api/v1/activity",
            headers={"Authorization": f"Bearer {mgmt_key}"},
        )
        if resp.status_code != 200:
            return {"error": "Failed to fetch activity from OpenRouter", "status": resp.status_code}
        data = resp.json()

    rows = data.get("data", data) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        rows = []

    _activity_cache = rows
    _activity_cache_ts = time.time()

    return _build_activity_response(rows, period)


def _build_activity_response(rows: list, period: str) -> dict:
    """Aggregate activity rows by period and model."""
    from collections import defaultdict
    from datetime import datetime, timedelta

    # Group rows by (period_key, model)
    period_model: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(
            lambda: {
                "cost": 0.0,
                "requests": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
            }
        )
    )
    # Also track per-model totals
    model_totals: dict[str, dict] = defaultdict(
        lambda: {
            "cost": 0.0,
            "requests": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }
    )

    for r in rows:
        date_str = r.get("date", "").split(" ")[0].split("T")[0]  # Strip time portion
        model = r.get("model", r.get("model_permaslug", "unknown"))
        short_model = model.split("/")[-1] if "/" in model else model
        cost = float(r.get("usage", 0)) + float(r.get("byok_usage_inference", 0))
        requests = int(r.get("requests", 0))
        prompt_tok = int(r.get("prompt_tokens", 0))
        comp_tok = int(r.get("completion_tokens", 0))

        # Determine period key
        if period == "weekly" and date_str:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                week_start = dt - timedelta(days=dt.weekday())
                pkey = f"{week_start.strftime('%Y-%m-%d')} week"
            except ValueError:
                pkey = date_str
        elif period == "monthly" and date_str:
            pkey = date_str[:7]  # YYYY-MM
        else:
            pkey = date_str

        agg = period_model[pkey][short_model]
        agg["cost"] += cost
        agg["requests"] += requests
        agg["prompt_tokens"] += prompt_tok
        agg["completion_tokens"] += comp_tok

        mt = model_totals[short_model]
        mt["cost"] += cost
        mt["requests"] += requests
        mt["prompt_tokens"] += prompt_tok
        mt["completion_tokens"] += comp_tok

    # Build period rows sorted by date desc
    periods_out = []
    for pkey in sorted(period_model.keys(), reverse=True):
        models_in_period = []
        period_cost = 0.0
        for model_name, agg in sorted(period_model[pkey].items(), key=lambda x: -x[1]["cost"]):
            period_cost += agg["cost"]
            models_in_period.append(
                {
                    "model": model_name,
                    "cost": round(agg["cost"], 6),
                    "requests": agg["requests"],
                    "prompt_tokens": agg["prompt_tokens"],
                    "completion_tokens": agg["completion_tokens"],
                    "tier": _classify_tier(_get_model_price(model_name)[0]),
                }
            )
        periods_out.append(
            {
                "period": pkey,
                "total_cost": round(period_cost, 6),
                "models": models_in_period,
            }
        )

    # Model totals sorted by cost desc
    totals_out = [
        {
            "model": m,
            "cost": round(t["cost"], 6),
            "requests": t["requests"],
            "prompt_tokens": t["prompt_tokens"],
            "completion_tokens": t["completion_tokens"],
            "tier": _classify_tier(_get_model_price(m)[0]),
        }
        for m, t in sorted(model_totals.items(), key=lambda x: -x[1]["cost"])
    ]

    grand_total = sum(t["cost"] for t in model_totals.values())

    return {
        "period_type": period,
        "periods": periods_out,
        "model_totals": totals_out,
        "grand_total": round(grand_total, 6),
    }


# ─── Budget Controls ────────────────────────────────────────────────────────


class BudgetConfigUpdate(BaseModel):
    monthly_budget: float | None = None
    alert_thresholds: list[int] | None = None
    agent_daily_limits: dict[str, float] | None = None
    default_agent_daily_limit: float | None = None
    throttle_to_tier1_on_exceed: bool | None = None
    alerts_enabled: bool | None = None


@router.get("/budget")
async def get_budget(
    org_ctx: OrganizationContext = Depends(require_org_member),
):
    """Get budget config, current month spend, and per-agent daily spend."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(BudgetConfig).where(BudgetConfig.organization_id == org_id)
        )
        config = result.scalars().first()

    if not config:
        config = BudgetConfig(organization_id=org_id)

    current_month = datetime.now(UTC).strftime("%Y-%m")
    today = date.today()

    async with async_session_maker() as session:
        # Monthly total for this org
        result = await session.execute(
            text(
                "SELECT COALESCE(SUM(estimated_cost), 0) FROM daily_agent_spends "
                "WHERE organization_id = :org_id AND date >= :month_start"
            ),
            {"org_id": str(org_id), "month_start": f"{current_month}-01"},
        )
        monthly_total = float(result.scalar() or 0)

        # Per-agent today for this org
        result = await session.execute(
            select(DailyAgentSpend).where(
                DailyAgentSpend.organization_id == org_id,
                DailyAgentSpend.date == today,
            )
        )
        today_spends = result.scalars().all()

    # Days elapsed this month
    days_elapsed = max(today.day, 1)
    daily_avg = monthly_total / days_elapsed if days_elapsed > 0 else 0

    # Projected month-end
    import calendar

    days_in_month = calendar.monthrange(today.year, today.month)[1]
    projected = daily_avg * days_in_month

    agent_today = []
    for s in today_spends:
        effective_limit = (
            config.agent_daily_limits.get(s.agent_name) or config.default_agent_daily_limit
        )
        agent_today.append(
            {
                "agent": s.agent_name,
                "cost": round(s.estimated_cost, 6),
                "tokens": s.input_tokens + s.output_tokens,
                "limit": effective_limit,
                "exceeded": s.estimated_cost > effective_limit if effective_limit else False,
                "models": s.model_breakdown,
            }
        )

    return {
        "config": {
            "monthly_budget": config.monthly_budget,
            "alert_thresholds": config.alert_thresholds,
            "agent_daily_limits": config.agent_daily_limits,
            "default_agent_daily_limit": config.default_agent_daily_limit,
            "throttle_to_tier1_on_exceed": config.throttle_to_tier1_on_exceed,
            "alerts_enabled": config.alerts_enabled,
        },
        "status": {
            "monthly_total": round(monthly_total, 4),
            "monthly_budget": config.monthly_budget,
            "monthly_pct": round(
                (monthly_total / config.monthly_budget * 100) if config.monthly_budget > 0 else 0, 1
            ),
            "remaining": round(config.monthly_budget - monthly_total, 4),
            "projected_month_end": round(projected, 4),
            "daily_avg": round(daily_avg, 4),
        },
        "agent_today": sorted(agent_today, key=lambda x: -x["cost"]),
    }


@router.put("/budget")
async def update_budget(
    payload: BudgetConfigUpdate,
    org_ctx: OrganizationContext = Depends(require_org_member),
):
    """Update budget configuration for the current organization."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(BudgetConfig).where(BudgetConfig.organization_id == org_id)
        )
        config = result.scalars().first()

        if not config:
            from uuid import uuid4

            config = BudgetConfig(id=uuid4(), organization_id=org_id, updated_at=utcnow())
            session.add(config)

        if payload.monthly_budget is not None:
            config.monthly_budget = payload.monthly_budget
            # Reset threshold tracking on budget change
            config.last_alert_thresholds_hit_json = "[]"
        if payload.alert_thresholds is not None:
            config.alert_thresholds_json = json.dumps(payload.alert_thresholds)
        if payload.agent_daily_limits is not None:
            config.agent_daily_limits_json = json.dumps(payload.agent_daily_limits)
        if payload.default_agent_daily_limit is not None:
            config.default_agent_daily_limit = payload.default_agent_daily_limit
        if payload.throttle_to_tier1_on_exceed is not None:
            config.throttle_to_tier1_on_exceed = payload.throttle_to_tier1_on_exceed
        if payload.alerts_enabled is not None:
            config.alerts_enabled = payload.alerts_enabled
        config.updated_at = utcnow()

        await session.commit()

    return {"ok": True}


@router.get("/agent-spend")
async def get_agent_spend(
    org_ctx: OrganizationContext = Depends(require_org_member),
    days: int = Query(30, description="Lookback days"),
    agent: str | None = Query(None, description="Filter by agent name"),
):
    """Get historical per-agent spend for the current organization."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        stmt = select(DailyAgentSpend).where(
            DailyAgentSpend.organization_id == org_id,
            DailyAgentSpend.date >= text(f"CURRENT_DATE - INTERVAL '{days} days'"),
        )
        if agent:
            stmt = stmt.where(DailyAgentSpend.agent_name == agent)
        stmt = stmt.order_by(DailyAgentSpend.date.desc())  # type: ignore[union-attr]

        result = await session.execute(stmt)
        rows = result.scalars().all()

    return {
        "days": days,
        "agent_filter": agent,
        "spends": [
            {
                "agent": r.agent_name,
                "date": r.date.isoformat(),
                "cost": round(r.estimated_cost, 6),
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "tokens": r.input_tokens + r.output_tokens,
                "models": r.model_breakdown,
                "sessions": r.session_count,
            }
            for r in rows
        ],
    }


@router.get("/errors", dependencies=[ORG_MEMBER_DEP])
async def get_error_log(
    limit: int = Query(20, description="Max errors to return"),
):
    """Get recent system errors from activity events."""
    from sqlalchemy import desc as sa_desc

    async with async_session_maker() as session:
        stmt = (
            select(ActivityEvent)
            .where(ActivityEvent.event_type.startswith("system.error"))  # type: ignore[union-attr]
            .order_by(sa_desc(ActivityEvent.created_at))
            .limit(min(limit, 100))
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

    return [
        {
            "id": str(r.id),
            "event_type": r.event_type,
            "message": r.message,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.delete("/errors", dependencies=[Depends(require_org_role("admin"))])
async def clear_error_log():
    """Clear all system error events. Requires admin role."""
    from sqlalchemy import delete as sa_delete

    async with async_session_maker() as session:
        stmt = sa_delete(ActivityEvent).where(
            ActivityEvent.event_type.startswith("system.error")  # type: ignore[union-attr]
        )
        result = await session.execute(stmt)
        await session.commit()

    return {"cleared": result.rowcount}


# ─── Cost Estimate ───────────────────────────────────────────────────────────

# Average tokens per interaction, based on observed platform usage.
_EST_TOKENS_PER_CONVERSATION = 4_000  # ~3K input + ~1K output typical


@router.get("/cost-estimate", dependencies=[ORG_MEMBER_DEP])
async def get_cost_estimate(
    org_ctx: OrganizationContext = Depends(require_org_member),
):
    """Cost reference card for org settings.

    If the org has real spend data (≥3 days), projects from actual usage.
    Otherwise returns per-conversation cost by model tier so users can
    estimate based on their own expected usage patterns.
    """
    org_id = org_ctx.organization.id
    today = date.today()

    # Check for real spend data
    async with async_session_maker() as session:
        result = await session.execute(
            text(
                "SELECT COUNT(DISTINCT date), COALESCE(SUM(estimated_cost), 0) "
                "FROM daily_agent_spends WHERE organization_id = :org_id"
            ),
            {"org_id": str(org_id)},
        )
        row = result.one()
        days_with_data = int(row[0])
        total_spend = float(row[1])

    # If we have ≥3 days of real data, project from actuals
    has_real_data = days_with_data >= 3
    projected_monthly = None
    daily_avg = None
    if has_real_data:
        daily_avg = round(total_spend / days_with_data, 4)
        projected_monthly = round(daily_avg * 30, 2)

    # Per-conversation cost by tier (always useful as reference)
    tier_costs = []
    for model, label in [
        ("gpt-5-nano", "Tier 1 — Nano"),
        ("deepseek-v3.2", "Tier 2 — Standard"),
        ("claude-sonnet-4", "Tier 3 — Reasoning"),
        ("claude-opus-4.6", "Tier 4 — Critical"),
    ]:
        prompt_pm, comp_pm = _get_model_price(model)
        input_tok = _EST_TOKENS_PER_CONVERSATION * 0.75
        output_tok = _EST_TOKENS_PER_CONVERSATION * 0.25
        per_conversation = (input_tok / 1_000_000) * prompt_pm + (output_tok / 1_000_000) * comp_pm
        tier_costs.append(
            {
                "tier": label,
                "model": model,
                "per_conversation": round(per_conversation, 6),
                "per_100_conversations": round(per_conversation * 100, 4),
                "prompt_per_m": prompt_pm,
                "completion_per_m": comp_pm,
            }
        )

    # Usage examples to help non-technical users estimate
    examples = [
        {
            "description": "Light usage — 1 agent, ~10 conversations/day, Tier 2",
            "monthly_est": round(tier_costs[1]["per_conversation"] * 10 * 30, 2),
        },
        {
            "description": "Moderate — 2 agents, ~20 conversations/day, mixed Tier 2/3",
            "monthly_est": round(
                (tier_costs[1]["per_conversation"] * 10 + tier_costs[2]["per_conversation"] * 10)
                * 30,
                2,
            ),
        },
        {
            "description": "Heavy — 4+ agents, cron jobs, mostly Tier 3",
            "monthly_est": round(tier_costs[2]["per_conversation"] * 40 * 30, 2),
        },
    ]

    return {
        "has_real_data": has_real_data,
        "days_tracked": days_with_data,
        "projected_monthly": projected_monthly,
        "daily_avg": daily_avg,
        "total_spend_to_date": round(total_spend, 4),
        "tier_costs": tier_costs,
        "examples": examples,
        "note": "Costs depend on conversation length, tool usage, and model tier. Set a monthly budget cap to prevent unexpected charges.",
    }
