"""Cost tracking endpoints — OpenRouter usage, live model pricing, gateway session data."""

from __future__ import annotations

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
