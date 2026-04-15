"""Thin wrapper around LLM API calls that logs every request to model_call_log.

Every call mc-backend makes to an LLM — chat completions, embeddings, vision,
whatever — should flow through this wrapper. It preserves the caller's error
handling (re-raises on failure) while guaranteeing a log row exists for both
success and failure paths.

Covers the ~10% of platform LLM traffic originating in mc-backend. Gateway-side
traffic is captured separately via OpenRouter Activity polling (Layer 2).
"""

from __future__ import annotations

import asyncio
import json
from time import perf_counter
from typing import Any
from uuid import UUID

import httpx

from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.model_call_log import ModelCallLog

logger = get_logger(__name__)

_ERROR_BODY_CLIP = 500


def _classify_error(
    *, http_status: int | None, exc: BaseException | None
) -> tuple[str, str]:
    """Return (status, error_type) for a failed call.

    status ∈ {"error", "timeout"}
    error_type ∈ {"timeout", "rate_limit", "server_error", "auth", "bad_request",
                  "connect_error", "unknown"}
    """
    if isinstance(exc, httpx.TimeoutException | asyncio.TimeoutError):
        return "timeout", "timeout"
    if isinstance(exc, httpx.ConnectError):
        return "error", "connect_error"
    if http_status is None:
        return "error", "unknown"
    if http_status == 429:
        return "error", "rate_limit"
    if http_status in (401, 403):
        return "error", "auth"
    if 400 <= http_status < 500:
        return "error", "bad_request"
    if http_status >= 500:
        return "error", "server_error"
    return "error", "unknown"


def _extract_provider_name(body: str | None) -> str | None:
    """Pull provider_name out of an OpenRouter error body.

    OpenRouter surfaces the underlying provider in error.metadata.provider_name
    (e.g., "Anthropic returned 503 via OpenRouter"). Returns None if not present.
    """
    if not body:
        return None
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    err = data.get("error") if isinstance(data, dict) else None
    if not isinstance(err, dict):
        return None
    meta = err.get("metadata")
    if isinstance(meta, dict):
        pn = meta.get("provider_name")
        if isinstance(pn, str):
            return pn
    return None


def _compute_cost(
    model: str, tokens_in: int | None, tokens_out: int | None
) -> float | None:
    """Compute USD cost via the model registry. Returns None if pricing unknown."""
    if tokens_in is None and tokens_out is None:
        return None
    try:
        from app.services.model_registry import get_registry

        entry = get_registry().get_model(model)
        if not entry:
            return None
        in_cost = (tokens_in or 0) / 1_000_000 * entry.prompt_price_per_m
        out_cost = (tokens_out or 0) / 1_000_000 * entry.completion_price_per_m
        return round(in_cost + out_cost, 6)
    except Exception:
        return None


async def _log_call(
    *,
    organization_id: UUID | None,
    model: str,
    provider: str,
    provider_name: str | None,
    skill_name: str,
    status: str,
    http_status: int | None,
    error_type: str | None,
    error_body: str | None,
    latency_ms: int,
    tokens_in: int | None,
    tokens_out: int | None,
) -> None:
    """Persist one ModelCallLog row. Swallows all errors — logging must never block the caller."""
    try:
        row = ModelCallLog(
            organization_id=organization_id,
            model=model,
            provider=provider,
            provider_name=provider_name,
            skill_name=skill_name,
            status=status,
            http_status=http_status,
            error_type=error_type,
            error_body=error_body[:_ERROR_BODY_CLIP] if error_body else None,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=_compute_cost(model, tokens_in, tokens_out),
            created_at=utcnow(),
        )
        async with async_session_maker() as session:
            session.add(row)
            await session.commit()
    except Exception:
        logger.debug("model_call_log.persist_failed", exc_info=True)


def _detect_provider(api_url: str) -> str:
    """Classify the endpoint URL into provider buckets."""
    if "openrouter.ai" in api_url:
        return "openrouter"
    if "anthropic.com" in api_url:
        return "anthropic_direct"
    if "openai.com" in api_url:
        return "openai_direct"
    return "custom"


async def llm_call(
    client: httpx.AsyncClient,
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    json_body: dict[str, Any],
    skill_name: str,
    model: str,
    organization_id: UUID | None,
) -> httpx.Response:
    """Execute an HTTP LLM call and log the outcome to model_call_log.

    Re-raises the original exception on failure so callers can handle errors
    normally. The log row is persisted regardless.

    Cost is computed best-effort via the model registry when token counts are
    returned. Usage tokens are pulled from the standard OpenAI-compatible
    response shape (data.usage.prompt_tokens / completion_tokens).
    """
    start = perf_counter()
    provider = _detect_provider(url)
    http_status: int | None = None
    error_body: str | None = None
    exc_to_reraise: BaseException | None = None
    response: httpx.Response | None = None

    try:
        response = await client.request(method, url, headers=headers, json=json_body)
        http_status = response.status_code
        if response.status_code >= 400:
            try:
                error_body = response.text
            except Exception:
                error_body = None
    except BaseException as exc:
        exc_to_reraise = exc

    latency_ms = int((perf_counter() - start) * 1000)

    # Successful response path
    if exc_to_reraise is None and response is not None and response.status_code < 400:
        tokens_in: int | None = None
        tokens_out: int | None = None
        try:
            data = response.json()
            usage = data.get("usage") if isinstance(data, dict) else None
            if isinstance(usage, dict):
                ti = usage.get("prompt_tokens") or usage.get("input_tokens")
                to = usage.get("completion_tokens") or usage.get("output_tokens")
                tokens_in = int(ti) if isinstance(ti, int | float) else None
                tokens_out = int(to) if isinstance(to, int | float) else None
        except Exception:
            pass

        await _log_call(
            organization_id=organization_id,
            model=model,
            provider=provider,
            provider_name=None,
            skill_name=skill_name,
            status="success",
            http_status=http_status,
            error_type=None,
            error_body=None,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        return response

    # Failure path — log, then re-raise or return so caller handles it
    status, error_type = _classify_error(http_status=http_status, exc=exc_to_reraise)
    provider_name = _extract_provider_name(error_body)

    await _log_call(
        organization_id=organization_id,
        model=model,
        provider=provider,
        provider_name=provider_name,
        skill_name=skill_name,
        status=status,
        http_status=http_status,
        error_type=error_type,
        error_body=error_body,
        latency_ms=latency_ms,
        tokens_in=None,
        tokens_out=None,
    )

    if exc_to_reraise is not None:
        raise exc_to_reraise
    # response is an HTTP error — return it unchanged; caller decides whether
    # to raise_for_status or inspect the body
    assert response is not None
    return response
