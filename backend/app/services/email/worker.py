"""Email sync worker — processes queued email sync jobs."""

from __future__ import annotations

import asyncio
import time

from app.core.config import settings
from app.core.logging import get_logger
from app.services.email.queue import dequeue_email_sync, requeue_if_failed
from app.services.email.sync import sync_email_account

logger = get_logger(__name__)


async def process_email_sync_queue(*, block: bool = False, block_timeout: float = 0) -> int:
    """Consume queued email sync jobs in a batch."""
    processed = 0
    while True:
        try:
            item = dequeue_email_sync(block=block, block_timeout=block_timeout)
        except Exception:
            logger.exception("email.worker.dequeue_failed")
            continue

        if item is None:
            break

        try:
            new_count = await sync_email_account(item.email_account_id)
            processed += 1
            logger.info(
                "email.worker.sync_success",
                extra={
                    "email_account_id": str(item.email_account_id),
                    "new_messages": new_count,
                    "attempt": item.attempts,
                },
            )
        except Exception as exc:
            logger.exception(
                "email.worker.sync_failed",
                extra={
                    "email_account_id": str(item.email_account_id),
                    "attempt": item.attempts,
                    "error": str(exc),
                },
            )
            delay = float(settings.rq_dispatch_retry_base_seconds) * (2 ** item.attempts)
            delay = min(delay, float(settings.rq_dispatch_retry_max_seconds))
            try:
                requeue_if_failed(item, delay_seconds=delay)
            except Exception:
                logger.exception("email.worker.requeue_failed")

        time.sleep(0.0)
        await asyncio.sleep(1.0)

    if processed > 0:
        logger.info("email.worker.batch_complete", extra={"count": processed})
    return processed


def run_email_sync_worker() -> None:
    """RQ entrypoint for running the email sync worker."""
    logger.info("email.worker.started")
    start = time.time()
    asyncio.run(process_email_sync_queue())
    elapsed_ms = int((time.time() - start) * 1000)
    logger.info("email.worker.finished", extra={"duration_ms": elapsed_ms})
