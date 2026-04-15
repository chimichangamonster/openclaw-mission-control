"""Langfuse observability client — lazy singleton for tracing agent operations.

Uses Langfuse SDK v4 with the self-hosted Langfuse v3 server (OTLP transport).

Returns None when observability is not configured, so callers can safely
check ``if client:`` before instrumenting. Zero overhead when disabled.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.core.logging import get_logger

if TYPE_CHECKING:
    from langfuse import Langfuse

logger = get_logger(__name__)

_langfuse: Langfuse | None = None
_init_attempted = False


def get_langfuse() -> Langfuse | None:
    """Return the Langfuse client singleton, or None if not configured."""
    global _langfuse, _init_attempted  # noqa: PLW0603

    if _init_attempted:
        return _langfuse

    _init_attempted = True

    if not settings.langfuse_secret_key or not settings.langfuse_public_key:
        logger.debug("langfuse.disabled — no keys configured")
        return None

    try:
        from langfuse import Langfuse

        _langfuse = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info("langfuse.initialized host=%s", settings.langfuse_host)
    except Exception:
        logger.warning("langfuse.init_failed", exc_info=True)
        _langfuse = None

    return _langfuse


# ── Embedding traces ──────────────────────────────────────────────────


def trace_embedding(
    *,
    org_id: str,
    model: str,
    input_text: str,
    token_count: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Log an embedding generation call to Langfuse."""
    client = get_langfuse()
    if not client:
        return

    try:
        span = client.start_observation(
            name="embedding",
            metadata={"org_id": org_id, **(metadata or {})},
        )
        gen = span.start_observation(
            name="get_embedding",
            as_type="generation",
            model=model,
            input=input_text[:500],
            usage_details={"input": token_count} if token_count else None,
        )
        gen.end()
        span.end()
    except Exception:
        logger.debug("langfuse.trace_embedding_failed", exc_info=True)


# ── Session titling traces ────────────────────────────────────────────


def trace_session_titling(
    *,
    org_id: str,
    model: str,
    title: str,
    token_count: int | None = None,
) -> None:
    """Log an auto-generated session title to Langfuse."""
    client = get_langfuse()
    if not client:
        return

    try:
        span = client.start_observation(
            name="session_titling",
            metadata={"org_id": org_id, "title": title},
        )
        gen = span.start_observation(
            name="generate_title",
            as_type="generation",
            model=model,
            output=title,
            usage_details={"total": token_count} if token_count else None,
        )
        gen.end()
        span.end()
    except Exception:
        logger.debug("langfuse.trace_session_titling_failed", exc_info=True)


# ── Gateway RPC traces ────────────────────────────────────────────────


def trace_rpc_call(
    *,
    method: str,
    duration_ms: int,
    success: bool,
    error_type: str | None = None,
    org_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Log a gateway WebSocket RPC call to Langfuse."""
    client = get_langfuse()
    if not client:
        return

    try:
        span = client.start_observation(
            name="gateway_rpc",
            metadata={
                "method": method,
                "org_id": org_id or "unknown",
                **(metadata or {}),
            },
        )
        child = span.start_observation(  # type: ignore[call-overload]
            name=f"rpc.{method}",
            metadata={
                "duration_ms": duration_ms,
                "success": success,
                "error_type": error_type,
            },
            level="DEFAULT" if success else "ERROR",
        )
        child.end()
        span.end()
    except Exception:
        logger.debug("langfuse.trace_rpc_failed", exc_info=True)


# ── Budget monitor traces ─────────────────────────────────────────────


def trace_budget_cycle(
    *,
    org_count: int,
    agent_count: int,
    monthly_total: float,
    duration_ms: int,
    compactions: int = 0,
    alerts_sent: int = 0,
) -> None:
    """Log a full budget check cycle to Langfuse."""
    client = get_langfuse()
    if not client:
        return

    try:
        span = client.start_observation(
            name="budget_check_cycle",
            metadata={
                "org_count": org_count,
                "agent_count": agent_count,
                "monthly_total_usd": round(monthly_total, 4),
                "duration_ms": duration_ms,
                "compactions_triggered": compactions,
                "alerts_sent": alerts_sent,
            },
        )
        span.score(
            name="monthly_spend_usd",
            value=round(monthly_total, 4),
        )
        span.end()
    except Exception:
        logger.debug("langfuse.trace_budget_cycle_failed", exc_info=True)


def trace_compaction(
    *,
    org_id: str,
    session_key: str,
    agent_name: str,
    context_pct: float,
    action: str,
    success: bool,
) -> None:
    """Log a proactive compaction attempt to Langfuse."""
    client = get_langfuse()
    if not client:
        return

    try:
        client.create_event(
            name="session_compaction",
            metadata={
                "org_id": org_id,
                "session_key": session_key,
                "agent_name": agent_name,
                "context_pct": round(context_pct, 1),
                "action": action,
                "success": success,
            },
        )
    except Exception:
        logger.debug("langfuse.trace_compaction_failed", exc_info=True)


# ── LLM routing traces ────────────────────────────────────────────────


def trace_llm_resolve(
    *,
    org_id: str,
    source: str,
    endpoint_url: str | None = None,
    duration_ms: int = 0,
) -> None:
    """Log an LLM endpoint resolution to Langfuse."""
    client = get_langfuse()
    if not client:
        return

    try:
        client.create_event(
            name="llm_endpoint_resolve",
            metadata={
                "org_id": org_id,
                "source": source,
                "endpoint_url": endpoint_url or "none",
                "duration_ms": duration_ms,
            },
        )
    except Exception:
        logger.debug("langfuse.trace_llm_resolve_failed", exc_info=True)


# ── Data retention traces ─────────────────────────────────────────────


def trace_retention_cleanup(
    *,
    results: dict[str, int],
    duration_ms: int,
) -> None:
    """Log a data retention cleanup cycle to Langfuse."""
    client = get_langfuse()
    if not client:
        return

    try:
        total = sum(results.values())
        client.create_event(
            name="data_retention_cleanup",
            metadata={
                "total_deleted": total,
                "duration_ms": duration_ms,
                **{f"deleted_{k}": v for k, v in results.items()},
            },
        )
    except Exception:
        logger.debug("langfuse.trace_retention_failed", exc_info=True)


# ── Quality scoring ───────────────────────────────────────────────────


def score_trace(
    *,
    trace_id: str,
    name: str,
    value: float,
    comment: str | None = None,
) -> None:
    """Submit a quality score for an existing trace.

    Used by the quality scoring API to attach human or automated feedback.
    """
    client = get_langfuse()
    if not client:
        return

    try:
        client.create_score(
            trace_id=trace_id,
            name=name,
            value=value,
            comment=comment,
        )
    except Exception:
        logger.debug("langfuse.score_trace_failed", exc_info=True)


# ── Shutdown ──────────────────────────────────────────────────────────


def flush() -> None:
    """Flush any pending Langfuse events. Call on shutdown."""
    if _langfuse:
        try:
            _langfuse.flush()
        except Exception:
            logger.debug("langfuse.flush_failed", exc_info=True)
