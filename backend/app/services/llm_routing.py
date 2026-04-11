"""LLM endpoint resolution — per-org routing to OpenRouter or custom endpoints.

Resolves the correct LLM API endpoint and key for an organization:
1. Custom self-hosted endpoint (enterprise) — if configured
2. Per-org OpenRouter BYOK key — if org has their own key
3. Platform OpenRouter key — only for platform owner org

Enterprise clients can point to their own OpenAI-compatible LLM server
(vLLM, Ollama, TGI, Azure OpenAI, etc.) and never send data to OpenRouter.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.core.encryption import decrypt_token
from app.core.logging import get_logger
from app.models.organization_settings import OrganizationSettings

logger = get_logger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class LLMEndpoint:
    """Resolved LLM endpoint for an organization."""

    api_url: (
        str  # Base URL (e.g., "https://openrouter.ai/api/v1" or "https://llm.corp.internal/v1")
    )
    api_key: str  # API key for authentication
    source: str  # "custom", "byok_openrouter", "platform_openrouter"
    name: str  # Human-readable name
    models: list[str]  # Available models (empty = all)
    is_openrouter: bool  # Whether cost tracking via OpenRouter APIs applies


async def resolve_llm_endpoint(
    session: AsyncSession,
    org_id: UUID,
) -> LLMEndpoint | None:
    """Resolve the LLM endpoint for an organization.

    Priority:
    1. Custom self-hosted endpoint (enterprise)
    2. Per-org OpenRouter BYOK key
    3. Platform OpenRouter key (owner org only)
    """
    result = await session.execute(
        select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
    )
    org_settings = result.scalars().first()

    # 1. Custom endpoint (enterprise)
    if org_settings:
        endpoint_config = org_settings.custom_llm_endpoint
        if endpoint_config.get("api_url"):
            api_key = ""
            if org_settings.custom_llm_api_key_encrypted:
                try:
                    api_key = decrypt_token(org_settings.custom_llm_api_key_encrypted)
                except Exception:
                    logger.warning("llm_routing.custom_key_decrypt_failed org_id=%s", org_id)

            return LLMEndpoint(
                api_url=endpoint_config["api_url"].rstrip("/"),
                api_key=api_key,
                source="custom",
                name=endpoint_config.get("name", "Custom LLM"),
                models=endpoint_config.get("models", []),
                is_openrouter=False,
            )

    # 2. Per-org BYOK OpenRouter key
    if org_settings and org_settings.openrouter_api_key_encrypted:
        try:
            key = decrypt_token(org_settings.openrouter_api_key_encrypted)
            return LLMEndpoint(
                api_url=OPENROUTER_BASE_URL,
                api_key=key,
                source="byok_openrouter",
                name="OpenRouter (BYOK)",
                models=[],
                is_openrouter=True,
            )
        except Exception:
            logger.warning("llm_routing.byok_key_decrypt_failed org_id=%s", org_id)

    # 3. Platform owner fallback
    from app.services.openrouter_keys import _is_platform_owner

    if settings.openrouter_api_key and await _is_platform_owner(session, org_id):
        return LLMEndpoint(
            api_url=OPENROUTER_BASE_URL,
            api_key=settings.openrouter_api_key,
            source="platform_openrouter",
            name="OpenRouter (Platform)",
            models=[],
            is_openrouter=True,
        )

    return None


async def check_endpoint_health(
    api_url: str,
    api_key: str,
) -> dict[str, object]:
    """Health check a custom LLM endpoint.

    Tests:
    1. Connectivity — can we reach the endpoint?
    2. Auth — does the API key work?
    3. Models — can we list available models?
    4. Inference — can we get a simple completion?
    """
    result: dict[str, object] = {
        "reachable": False,
        "authenticated": False,
        "models": [],
        "inference_ok": False,
        "latency_ms": None,
        "error": None,
    }

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # 1. List models
            resp = await client.get(f"{api_url}/models", headers=headers)
            result["reachable"] = True

            if resp.status_code == 401:
                result["error"] = "Authentication failed (401)"
                return result
            if resp.status_code == 403:
                result["error"] = "Access denied (403)"
                return result

            result["authenticated"] = True

            if resp.status_code == 200:
                data = resp.json()
                models = data.get("data", data.get("models", []))
                result["models"] = [
                    m.get("id", m.get("name", str(m)))
                    for m in (models if isinstance(models, list) else [])
                ][
                    :20
                ]  # cap at 20

            # 2. Simple inference test
            import time

            test_payload = {
                "model": result["models"][0] if result["models"] else "test",
                "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                "max_tokens": 5,
            }
            start = time.time()
            resp = await client.post(
                f"{api_url}/chat/completions",
                headers={**headers, "Content-Type": "application/json"},
                json=test_payload,
            )
            latency = int((time.time() - start) * 1000)
            result["latency_ms"] = latency

            if resp.status_code == 200:
                result["inference_ok"] = True
            else:
                result["error"] = f"Inference returned {resp.status_code}"

    except httpx.ConnectError:
        result["error"] = "Connection refused — endpoint unreachable"
    except httpx.TimeoutException:
        result["error"] = "Connection timed out (15s)"
    except Exception as exc:
        result["error"] = str(exc)[:200]

    return result
