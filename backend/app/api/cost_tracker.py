"""Cost tracking endpoints — OpenRouter usage, live model pricing, gateway session data."""

from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, Depends, Query

from app.api.deps import ORG_MEMBER_DEP
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/cost-tracker", tags=["cost-tracker"])

# Cache live pricing for 1 hour to avoid hammering OpenRouter
_pricing_cache: dict | None = None
_pricing_cache_ts: float = 0


@router.get("/usage", dependencies=[ORG_MEMBER_DEP])
async def get_usage():
    """Get OpenRouter usage and budget data."""
    api_key = settings.openrouter_api_key
    if not api_key:
        return {"error": "OpenRouter API key not configured"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        key_resp = await client.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        key_data = key_resp.json().get("data", {}) if key_resp.status_code == 200 else {}

        credits_resp = await client.get(
            "https://openrouter.ai/api/v1/credits",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        credits_data = credits_resp.json().get("data", {}) if credits_resp.status_code == 200 else {}

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


@router.get("/models", dependencies=[ORG_MEMBER_DEP])
async def get_model_pricing(
    filter: str = Query("configured", description="'configured' = only models in our gateway, 'all' = everything on OpenRouter"),
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

    # Our configured models (from openclaw.json)
    configured_ids = {
        "anthropic/claude-sonnet-4",
        "anthropic/claude-sonnet-4.6",
        "anthropic/claude-opus-4-6",
        "deepseek/deepseek-v3.2",
        "deepseek/deepseek-chat-v3.1",
        "google/gemini-2.5-flash",
        "google/gemini-2.5-flash-lite",
        "x-ai/grok-4",
        "x-ai/grok-4-fast",
        "x-ai/grok-3",
        "openai/gpt-5-nano",
        "openai/gpt-5.4",
        "google/gemini-3-pro-preview",
        "minimax/minimax-m2.7",
        "moonshotai/kimi-k2.5",
        "qwen/qwen3-coder",
        "openrouter/auto",
    }

    # Agent assignments
    agent_usage = {
        "anthropic/claude-sonnet-4": ["The Claw", "Sports Analyst"],
        "deepseek/deepseek-v3.2": ["Stock Analyst", "Market Scout"],
        "x-ai/grok-4": ["Sentiment (subagent)"],
        "x-ai/grok-4-fast": ["Quick lookups (Tier 1)"],
        "google/gemini-2.5-flash": ["Fallback"],
        "openai/gpt-5-nano": ["Heartbeat"],
    }

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

        models.append({
            "id": model_id,
            "name": m.get("name", model_id),
            "prompt_per_m": round(prompt_price, 4),
            "completion_per_m": round(completion_price, 4),
            "context_length": m.get("context_length"),
            "configured": is_configured,
            "agents": agents,
            "tier": _classify_tier(prompt_price),
        })

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


@router.get("/usage-by-model", dependencies=[ORG_MEMBER_DEP])
async def get_usage_by_model():
    """Aggregate gateway session tokens by model and compute cost using live pricing."""
    from app.services.openclaw.gateway_rpc import GatewayConfig, openclaw_call
    from sqlmodel import select
    from app.db.session import async_session_maker
    from app.models.gateways import Gateway

    # Find gateway
    async with async_session_maker() as db_session:
        result = await db_session.execute(select(Gateway).limit(1))
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
        sessions_data
        if isinstance(sessions_data, list)
        else sessions_data.get("sessions", [])
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
        cost = (agg["input_tokens"] / 1_000_000) * prompt_pm + (agg["output_tokens"] / 1_000_000) * comp_pm
        total_cost += cost
        models_out.append({
            "model": agg["model"],
            "input_tokens": agg["input_tokens"],
            "output_tokens": agg["output_tokens"],
            "total_tokens": agg["input_tokens"] + agg["output_tokens"],
            "estimated_cost": round(cost, 6),
            "session_count": agg["session_count"],
            "agents": sorted(agg["agents"]),
            "tier": _classify_tier(prompt_pm),
        })

    # Include configured models with no active sessions for a complete leaderboard
    configured_short_names = {
        "claude-sonnet-4": ["The Claw", "Sports Analyst"],
        "deepseek-v3.2": ["Stock Analyst", "Market Scout"],
        "grok-4": ["Sentiment (subagent)"],
        "grok-4-fast": ["Quick lookups"],
        "gemini-2.5-flash": ["Fallback"],
        "gpt-5-nano": ["Heartbeat"],
    }
    seen = {m["model"] for m in models_out}
    for model_name, agents in configured_short_names.items():
        if model_name not in seen:
            prompt_pm, _ = _get_model_price(model_name)
            models_out.append({
                "model": model_name,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "estimated_cost": 0,
                "session_count": 0,
                "agents": agents,
                "tier": _classify_tier(prompt_pm),
            })

    # Sort by cost descending, then alphabetically for zero-cost
    models_out.sort(key=lambda x: (-x["estimated_cost"], x["model"]))

    return {"models": models_out, "total_cost": round(total_cost, 6)}


# Cache activity data for 10 minutes
_activity_cache: dict | None = None
_activity_cache_ts: float = 0


@router.get("/activity", dependencies=[ORG_MEMBER_DEP])
async def get_activity(
    period: str = Query("daily", description="'daily' = per-day rows, 'weekly' = aggregated by week, 'monthly' = aggregated by month"),
):
    """Get historical per-model spending from OpenRouter activity API (last 30 days)."""
    global _activity_cache, _activity_cache_ts

    mgmt_key = settings.openrouter_management_key or settings.openrouter_api_key
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
    period_model: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {
        "cost": 0.0, "requests": 0, "prompt_tokens": 0, "completion_tokens": 0,
    }))
    # Also track per-model totals
    model_totals: dict[str, dict] = defaultdict(lambda: {
        "cost": 0.0, "requests": 0, "prompt_tokens": 0, "completion_tokens": 0,
    })

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
            models_in_period.append({
                "model": model_name,
                "cost": round(agg["cost"], 6),
                "requests": agg["requests"],
                "prompt_tokens": agg["prompt_tokens"],
                "completion_tokens": agg["completion_tokens"],
                "tier": _classify_tier(_get_model_price(model_name)[0]),
            })
        periods_out.append({
            "period": pkey,
            "total_cost": round(period_cost, 6),
            "models": models_in_period,
        })

    # Model totals sorted by cost desc
    totals_out = [
        {"model": m, "cost": round(t["cost"], 6), "requests": t["requests"],
         "prompt_tokens": t["prompt_tokens"], "completion_tokens": t["completion_tokens"],
         "tier": _classify_tier(_get_model_price(m)[0])}
        for m, t in sorted(model_totals.items(), key=lambda x: -x[1]["cost"])
    ]

    grand_total = sum(t["cost"] for t in model_totals.values())

    return {
        "period_type": period,
        "periods": periods_out,
        "model_totals": totals_out,
        "grand_total": round(grand_total, 6),
    }
