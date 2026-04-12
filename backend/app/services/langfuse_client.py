"""Langfuse observability client — lazy singleton for tracing agent operations.

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
            enabled=True,
        )
        logger.info("langfuse.initialized host=%s", settings.langfuse_host)
    except Exception:
        logger.warning("langfuse.init_failed", exc_info=True)
        _langfuse = None

    return _langfuse


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
        trace = client.trace(
            name="embedding",
            metadata={"org_id": org_id, **(metadata or {})},
        )
        trace.generation(
            name="get_embedding",
            model=model,
            input=input_text[:500],
            usage={"input": token_count} if token_count else None,
        )
    except Exception:
        logger.debug("langfuse.trace_embedding_failed", exc_info=True)


def flush() -> None:
    """Flush any pending Langfuse events. Call on shutdown."""
    if _langfuse:
        try:
            _langfuse.flush()
        except Exception:
            logger.debug("langfuse.flush_failed", exc_info=True)
