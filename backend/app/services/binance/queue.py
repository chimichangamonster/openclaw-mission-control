"""Crypto trade execution queue."""

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
TASK_TYPE = "crypto_trade"
QUEUE_NAME = "crypto_trade"


@dataclass(frozen=True)
class QueuedCryptoTrade:
    trade_proposal_id: UUID
    organization_id: UUID
    attempts: int = 0


def _task_from_payload(payload: QueuedCryptoTrade) -> QueuedTask:
    return QueuedTask(
        task_type=TASK_TYPE,
        payload={
            "trade_proposal_id": str(payload.trade_proposal_id),
            "organization_id": str(payload.organization_id),
        },
        created_at=datetime.now(UTC),
        attempts=payload.attempts,
    )


def enqueue_crypto_trade(payload: QueuedCryptoTrade) -> bool:
    try:
        queued = _task_from_payload(payload)
        enqueue_task(queued, QUEUE_NAME, redis_url=settings.rq_redis_url)
        logger.info(
            "binance.queue.enqueued",
            extra={"trade_proposal_id": str(payload.trade_proposal_id)},
        )
        return True
    except Exception as exc:
        logger.warning(
            "binance.queue.enqueue_failed",
            extra={"error": str(exc)},
        )
        return False


def dequeue_crypto_trade(
    *, block: bool = False, block_timeout: float = 0
) -> QueuedCryptoTrade | None:
    task = dequeue_task(
        QUEUE_NAME,
        redis_url=settings.rq_redis_url,
        block=block,
        block_timeout=block_timeout,
    )
    if task is None:
        return None
    payload: dict[str, Any] = task.payload
    return QueuedCryptoTrade(
        trade_proposal_id=UUID(payload["trade_proposal_id"]),
        organization_id=UUID(payload["organization_id"]),
        attempts=int(payload.get("attempts", task.attempts)),
    )


def requeue_if_failed(payload: QueuedCryptoTrade, *, delay_seconds: float = 0) -> bool:
    return generic_requeue_if_failed(
        _task_from_payload(payload),
        QUEUE_NAME,
        max_retries=settings.rq_dispatch_max_retries,
        redis_url=settings.rq_redis_url,
        delay_seconds=delay_seconds,
    )
