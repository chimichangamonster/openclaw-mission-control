"""Cost tracking endpoints — OpenRouter usage + gateway session token data."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends

from app.api.deps import ORG_MEMBER_DEP
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/cost-tracker", tags=["cost-tracker"])


@router.get("/usage", dependencies=[ORG_MEMBER_DEP])
async def get_usage():
    """Get OpenRouter usage and budget data."""
    api_key = settings.openrouter_api_key
    if not api_key:
        return {"error": "OpenRouter API key not configured"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Get key info (usage, limits)
        key_resp = await client.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        key_data = key_resp.json().get("data", {}) if key_resp.status_code == 200 else {}

        # Get credits
        credits_resp = await client.get(
            "https://openrouter.ai/api/v1/credits",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        credits_data = credits_resp.json().get("data", {}) if credits_resp.status_code == 200 else {}

    return {
        "total_credits": credits_data.get("total_credits", 0),
        "total_usage": credits_data.get("total_usage", 0),
        "remaining": key_data.get("limit_remaining", 0),
        "limit": key_data.get("limit", 0),
        "usage_daily": key_data.get("usage_daily", 0),
        "usage_weekly": key_data.get("usage_weekly", 0),
        "usage_monthly": key_data.get("usage_monthly", 0),
        "limit_reset": key_data.get("limit_reset", "monthly"),
        "is_free_tier": key_data.get("is_free_tier", False),
    }


@router.get("/sessions", dependencies=[ORG_MEMBER_DEP])
async def get_session_costs():
    """Get per-agent token usage from gateway sessions."""
    from app.services.organizations import OrganizationContext

    # Model pricing (per 1M tokens, prompt/completion)
    MODEL_PRICING = {
        "claude-sonnet-4": (3.0, 15.0),
        "claude-sonnet-4.6": (3.0, 15.0),
        "claude-opus-4.6": (5.0, 25.0),
        "deepseek-v3.2": (0.26, 0.38),
        "deepseek-chat-v3": (0.4, 1.3),
        "deepseek-chat-v3.1": (0.2, 0.8),
        "gemini-2.5-flash": (0.3, 2.5),
        "gemini-2.5-flash-lite": (0.1, 0.4),
        "gpt-5-nano": (0.05, 0.4),
        "gpt-4o-mini": (0.15, 0.6),
        "minimax-m2.7": (0.3, 1.2),
        "kimi-k2.5": (0.45, 2.2),
    }

    try:
        # Get gateway sessions via MC's gateway proxy
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "http://openclaw-business-platform-openclaw-gateway-1:18789/__openclaw__/canvas/",
            )
    except Exception:
        pass

    # Use the gateway status endpoint instead
    try:
        from sqlmodel.ext.asyncio.session import AsyncSession
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlmodel import select
        from app.models import Gateway

        # Direct gateway RPC won't work easily, so parse from MC's cached data
        pass
    except Exception:
        pass

    # For now, return the model pricing table so the frontend can calculate
    return {
        "model_pricing": {k: {"prompt_per_m": v[0], "completion_per_m": v[1]} for k, v in MODEL_PRICING.items()},
        "note": "Token counts come from the gateway sessions endpoint (/api/v1/gateways/status). Frontend combines both.",
    }
