"""Cron watchdog — detect stale tasks from failed cron jobs and alert."""

from __future__ import annotations

from datetime import datetime, timedelta, UTC
from uuid import UUID

from sqlalchemy import text
from sqlmodel import select

from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.gateways import Gateway
from app.models.tasks import Task
from app.services.error_tracker import track_error
from app.services.openclaw.gateway_rpc import GatewayConfig, send_message

logger = get_logger(__name__)

# Cron task titles start with these prefixes (set by skill SKILL.md files)
CRON_TASK_PREFIXES = [
    "Morning Scan",
    "Portfolio Monitor",
    "Cost Optimizer",
]

# How long a cron task can stay in_progress before we consider it stale
STALE_THRESHOLD = timedelta(minutes=30)

# Track already-alerted tasks to avoid spam (reset on restart — acceptable)
_alerted_task_ids: set[UUID] = set()


async def _get_first_gateway_config() -> GatewayConfig | None:
    """Get the first available gateway config for sending alerts."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(Gateway).where(Gateway.url.isnot(None)).limit(1)  # type: ignore[union-attr]
        )
        gateway = result.scalars().first()
    if not gateway or not gateway.url:
        return None
    return GatewayConfig(url=gateway.url, token=gateway.token)


async def _send_alert(gw_config: GatewayConfig, message: str) -> None:
    """Send alert to #notifications via gateway."""
    try:
        await send_message(
            message,
            session_key="agent:notification-agent:alerts",
            config=gw_config,
        )
    except Exception:  # noqa: BLE001
        logger.warning("cron_watchdog.alert_send_failed")


async def check_stale_cron_tasks() -> None:
    """Find cron tasks stuck in in_progress and alert.

    Called every 10 minutes from lifespan background loop.
    """
    now = utcnow()
    cutoff = now - STALE_THRESHOLD

    async with async_session_maker() as session:
        result = await session.execute(
            text(
                "SELECT id, title, board_id, in_progress_at, created_at "
                "FROM tasks "
                "WHERE status = 'in_progress' "
                "AND created_at < :cutoff "
                "ORDER BY created_at DESC "
                "LIMIT 20"
            ),
            {"cutoff": cutoff},
        )
        stale_tasks = result.all()

    if not stale_tasks:
        return

    # Filter to cron-created tasks (match by title prefix)
    cron_stale = []
    for row in stale_tasks:
        task_id, title, board_id, in_progress_at, created_at = row
        task_uuid = UUID(str(task_id))
        if task_uuid in _alerted_task_ids:
            continue
        if any(title.startswith(prefix) for prefix in CRON_TASK_PREFIXES):
            cron_stale.append((task_uuid, title, created_at))

    if not cron_stale:
        return

    gw_config = await _get_first_gateway_config()
    if not gw_config:
        logger.warning("cron_watchdog.no_gateway_config")
        return

    for task_uuid, title, created_at in cron_stale:
        age_min = int((now - created_at).total_seconds() / 60)
        alert_msg = (
            f"**CRON WATCHDOG — Stale Task Detected**\n"
            f"Task: {title}\n"
            f"Created: {created_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"Stuck in `in_progress` for {age_min} minutes\n"
            f"The cron job may have failed silently. Check `docker logs` for the gateway."
        )
        await _send_alert(gw_config, alert_msg)
        await track_error(
            "cron_watchdog",
            f"Stale cron task: {title} (created {created_at.isoformat()}, {age_min}min old)",
            severity="warning",
        )
        _alerted_task_ids.add(task_uuid)
        logger.info(
            "cron_watchdog.stale_task_alerted task=%s title=%s age_min=%d",
            task_uuid,
            title,
            age_min,
        )

    # Prune old entries from alert set (keep last 100)
    if len(_alerted_task_ids) > 100:
        _alerted_task_ids.clear()
