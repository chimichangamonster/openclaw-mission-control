"""Trade execution worker — processes approved trades from the queue."""

from __future__ import annotations

import asyncio
import time

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import async_session_maker
from app.services.polymarket.execution import execute_approved_trade
from app.services.polymarket.queue import dequeue_trade_execution, requeue_if_failed

logger = get_logger(__name__)


async def process_trade_execution_queue(*, block: bool = False, block_timeout: float = 0) -> int:
    """Consume queued trade execution jobs."""
    processed = 0
    while True:
        try:
            item = dequeue_trade_execution(block=block, block_timeout=block_timeout)
        except Exception:
            logger.exception("polymarket.worker.dequeue_failed")
            continue

        if item is None:
            break

        try:
            async with async_session_maker() as session:
                result = await execute_approved_trade(session, item.trade_proposal_id)
            processed += 1
            logger.info(
                "polymarket.worker.success",
                extra={
                    "trade_proposal_id": str(item.trade_proposal_id),
                    "executed": result is not None,
                    "attempt": item.attempts,
                },
            )
        except Exception as exc:
            logger.exception(
                "polymarket.worker.failed",
                extra={
                    "trade_proposal_id": str(item.trade_proposal_id),
                    "attempt": item.attempts,
                    "error": str(exc),
                },
            )
            delay = float(settings.rq_dispatch_retry_base_seconds) * (2**item.attempts)
            delay = min(delay, float(settings.rq_dispatch_retry_max_seconds))
            try:
                requeue_if_failed(item, delay_seconds=delay)
            except Exception:
                logger.exception("polymarket.worker.requeue_failed")

        time.sleep(0.0)
        await asyncio.sleep(1.0)

    if processed > 0:
        logger.info("polymarket.worker.batch_complete", extra={"count": processed})
    return processed


def run_trade_execution_worker() -> None:
    """RQ entrypoint for the trade execution worker."""
    logger.info("polymarket.worker.started")
    start = time.time()
    asyncio.run(process_trade_execution_queue())
    elapsed_ms = int((time.time() - start) * 1000)
    logger.info("polymarket.worker.finished", extra={"duration_ms": elapsed_ms})
