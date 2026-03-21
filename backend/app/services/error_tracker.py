"""Persist notable errors to ActivityEvent table for visibility in Mission Control."""

from __future__ import annotations

from uuid import uuid4

from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.activity_events import ActivityEvent

logger = get_logger(__name__)

# Event type prefix for all tracked errors
ERROR_PREFIX = "system.error"


async def track_error(
    source: str,
    message: str,
    *,
    severity: str = "error",
) -> None:
    """Persist an error event to the activity_events table.

    Args:
        source: Component that produced the error (e.g., "openrouter", "gateway_rpc", "cron")
        message: Human-readable error description
        severity: "error" or "warning"
    """
    event_type = f"{ERROR_PREFIX}.{source}"
    full_message = f"[{severity.upper()}] {message}"

    try:
        async with async_session_maker() as session:
            event = ActivityEvent(
                id=uuid4(),
                event_type=event_type,
                message=full_message[:1000],  # Truncate to avoid DB bloat
                created_at=utcnow(),
            )
            session.add(event)
            await session.commit()
    except Exception:  # noqa: BLE001
        # Don't let error tracking itself cause failures
        logger.warning("error_tracker.persist_failed source=%s", source)
