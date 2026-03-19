"""Crypto trade execution worker."""

from __future__ import annotations

import asyncio
import time

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import async_session_maker
from app.services.binance.execution import execute_approved_crypto_trade
from app.services.binance.queue import dequeue_crypto_trade, requeue_if_failed

logger = get_logger(__name__)


async def process_crypto_trade_queue(*, block: bool = False, block_timeout: float = 0) -> int:
    processed = 0
    while True:
        try:
            item = dequeue_crypto_trade(block=block, block_timeout=block_timeout)
        except Exception:
            logger.exception("binance.worker.dequeue_failed")
            continue

        if item is None:
            break

        try:
            async with async_session_maker() as session:
                await execute_approved_crypto_trade(session, item.trade_proposal_id)
            processed += 1
        except Exception as exc:
            logger.exception(
                "binance.worker.failed",
                extra={"trade_proposal_id": str(item.trade_proposal_id), "error": str(exc)},
            )
            delay = float(settings.rq_dispatch_retry_base_seconds) * (2 ** item.attempts)
            delay = min(delay, float(settings.rq_dispatch_retry_max_seconds))
            try:
                requeue_if_failed(item, delay_seconds=delay)
            except Exception:
                logger.exception("binance.worker.requeue_failed")

        time.sleep(0.0)
        await asyncio.sleep(1.0)

    if processed > 0:
        logger.info("binance.worker.batch_complete", extra={"count": processed})
    return processed


def run_crypto_trade_worker() -> None:
    logger.info("binance.worker.started")
    start = time.time()
    asyncio.run(process_crypto_trade_queue())
    elapsed_ms = int((time.time() - start) * 1000)
    logger.info("binance.worker.finished", extra={"duration_ms": elapsed_ms})
