"""Trade execution queue persistence helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.core.logging import get_logger
from app.services.queue import QueuedTask, dequeue_task, enqueue_task
from app.services.queue import requeue_if_failed as generic_requeue_if_failed

logger = get_logger(__name__)
TASK_TYPE = "trade_execution"


@dataclass(frozen=True)
class QueuedTradeExecution:
    """Payload for deferred trade execution after approval."""

    trade_proposal_id: UUID
    organization_id: UUID
    attempts: int = 0


def _task_from_payload(payload: QueuedTradeExecution) -> QueuedTask:
    return QueuedTask(
        task_type=TASK_TYPE,
        payload={
            "trade_proposal_id": str(payload.trade_proposal_id),
            "organization_id": str(payload.organization_id),
        },
        created_at=datetime.now(UTC),
        attempts=payload.attempts,
    )


def decode_trade_task(task: QueuedTask) -> QueuedTradeExecution:
    if task.task_type != TASK_TYPE:
        raise ValueError(f"Unexpected task_type={task.task_type!r}; expected {TASK_TYPE!r}")
    payload: dict[str, Any] = task.payload
    return QueuedTradeExecution(
        trade_proposal_id=UUID(payload["trade_proposal_id"]),
        organization_id=UUID(payload["organization_id"]),
        attempts=int(payload.get("attempts", task.attempts)),
    )


def enqueue_trade_execution(payload: QueuedTradeExecution) -> bool:
    """Enqueue an approved trade for execution."""
    try:
        queued = _task_from_payload(payload)
        enqueue_task(queued, settings.polymarket_queue_name, redis_url=settings.rq_redis_url)
        logger.info(
            "polymarket.queue.enqueued",
            extra={
                "trade_proposal_id": str(payload.trade_proposal_id),
                "attempt": payload.attempts,
            },
        )
        return True
    except Exception as exc:
        logger.warning(
            "polymarket.queue.enqueue_failed",
            extra={
                "trade_proposal_id": str(payload.trade_proposal_id),
                "error": str(exc),
            },
        )
        return False


def dequeue_trade_execution(
    *,
    block: bool = False,
    block_timeout: float = 0,
) -> QueuedTradeExecution | None:
    """Pop one queued trade execution job."""
    task = dequeue_task(
        settings.polymarket_queue_name,
        redis_url=settings.rq_redis_url,
        block=block,
        block_timeout=block_timeout,
    )
    if task is None:
        return None
    return decode_trade_task(task)


def requeue_if_failed(
    payload: QueuedTradeExecution,
    *,
    delay_seconds: float = 0,
) -> bool:
    """Requeue a failed trade execution with capped retries."""
    return generic_requeue_if_failed(
        _task_from_payload(payload),
        settings.polymarket_queue_name,
        max_retries=settings.rq_dispatch_max_retries,
        redis_url=settings.rq_redis_url,
        delay_seconds=delay_seconds,
    )
