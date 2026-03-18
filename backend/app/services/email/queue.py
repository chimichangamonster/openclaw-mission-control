"""Email sync queue persistence helpers."""

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
TASK_TYPE = "email_sync"


@dataclass(frozen=True)
class QueuedEmailSync:
    """Payload metadata for deferred email account sync."""

    email_account_id: UUID
    organization_id: UUID
    attempts: int = 0


def _task_from_payload(payload: QueuedEmailSync) -> QueuedTask:
    return QueuedTask(
        task_type=TASK_TYPE,
        payload={
            "email_account_id": str(payload.email_account_id),
            "organization_id": str(payload.organization_id),
        },
        created_at=datetime.now(UTC),
        attempts=payload.attempts,
    )


def decode_email_sync_task(task: QueuedTask) -> QueuedEmailSync:
    if task.task_type != TASK_TYPE:
        raise ValueError(f"Unexpected task_type={task.task_type!r}; expected {TASK_TYPE!r}")
    payload: dict[str, Any] = task.payload
    return QueuedEmailSync(
        email_account_id=UUID(payload["email_account_id"]),
        organization_id=UUID(payload["organization_id"]),
        attempts=int(payload.get("attempts", task.attempts)),
    )


def enqueue_email_sync(payload: QueuedEmailSync) -> bool:
    """Enqueue an email account sync job."""
    try:
        queued = _task_from_payload(payload)
        enqueue_task(queued, settings.email_sync_queue_name, redis_url=settings.rq_redis_url)
        logger.info(
            "email.queue.enqueued",
            extra={
                "email_account_id": str(payload.email_account_id),
                "attempt": payload.attempts,
            },
        )
        return True
    except Exception as exc:
        logger.warning(
            "email.queue.enqueue_failed",
            extra={
                "email_account_id": str(payload.email_account_id),
                "error": str(exc),
            },
        )
        return False


def dequeue_email_sync(
    *,
    block: bool = False,
    block_timeout: float = 0,
) -> QueuedEmailSync | None:
    """Pop one queued email sync job."""
    task = dequeue_task(
        settings.email_sync_queue_name,
        redis_url=settings.rq_redis_url,
        block=block,
        block_timeout=block_timeout,
    )
    if task is None:
        return None
    return decode_email_sync_task(task)


def requeue_if_failed(
    payload: QueuedEmailSync,
    *,
    delay_seconds: float = 0,
) -> bool:
    """Requeue a failed email sync with capped retries."""
    return generic_requeue_if_failed(
        _task_from_payload(payload),
        settings.email_sync_queue_name,
        max_retries=settings.rq_dispatch_max_retries,
        redis_url=settings.rq_redis_url,
        delay_seconds=delay_seconds,
    )
