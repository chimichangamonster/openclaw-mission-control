"""Outbound webhook dispatcher for the Partner API v1 namespace.

See `docs/business/partner-api-v1-scope.md` (Webhooks section + Webhook
security section + Retry schedule + Auto-disable trigger) for design.

The dispatcher has two halves:

* **Producer** — :func:`enqueue_partner_webhook_event` builds a Stripe-shaped
  envelope, signs it, persists nothing, and enqueues a ``QueuedTask`` for
  the shared :mod:`app.services.queue_worker` to consume.
* **Consumer** — :func:`process_partner_webhook_task` is the handler the
  shared worker invokes per dequeued task. It re-resolves DNS, fires the
  HTTPS POST, observes the response, and either marks the subscription
  recovered or writes a failure row + schedules a retry.

The retry schedule (1m / 5m / 30m / 2h / 6h / 24h → dead-letter) is encoded
in :data:`RETRY_DELAYS_SECONDS` and is intentionally distinct from the
codebase's generic exponential backoff: partner webhooks need 6 attempts
spanning ~33h, the internal worker default caps at ~120s after 3 attempts.

The dispatcher does NOT raise on partner-side failures — it returns
normally and records the audit row, because raising would cause the
shared queue worker to re-enqueue with its own generic schedule. We want
**this** module to own the schedule for partner webhooks.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.partner_webhook_delivery import (
    DELIVERY_STATUS_DEAD_LETTERED,
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_REJECTED_DNS,
    PartnerWebhookDelivery,
)
from app.models.partner_webhook_subscription import PartnerWebhookSubscription
from app.services.partner_webhook_signing import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    build_event_envelope,
    serialize_envelope,
    sign_body,
)
from app.services.partner_webhook_url_validation import (
    WebhookUrlValidationError,
    validate_resolved_host,
)
from app.services.queue import (
    QueuedTask,
    enqueue_task,
    enqueue_task_with_delay,
)

logger = get_logger(__name__)

TASK_TYPE = "partner_webhook_delivery"


def _queue_name() -> str:
    """Resolve at call time so tests / config overrides take effect.

    Partner webhooks share the default queue with the internal board-
    webhook task. Per-task-type retry semantics live in the worker's
    handler registry, so different schedules co-exist cleanly on one
    queue.
    """
    return settings.rq_queue_name

# Retry schedule from the scope doc, in seconds. Length determines max
# attempts: ``len(RETRY_DELAYS_SECONDS) + 1`` total attempts before
# dead-letter (the +1 is the initial attempt).
RETRY_DELAYS_SECONDS: tuple[int, ...] = (
    60,        # 1 minute
    5 * 60,    # 5 minutes
    30 * 60,   # 30 minutes
    2 * 3600,  # 2 hours
    6 * 3600,  # 6 hours
    24 * 3600, # 24 hours
)

# Auto-disable trigger threshold (scope doc spec).
AUTO_DISABLE_CONSECUTIVE_FAILURES = 20

# Per-request HTTP timeout. Partners shouldn't keep us hanging — if they
# can't respond in 10s, fail fast and let the retry schedule handle it.
HTTP_TIMEOUT_SECONDS = 10.0


# === Producer ============================================================


def enqueue_partner_webhook_event(
    *,
    subscription_id: UUID,
    organization_id: UUID,
    url: str,
    secret: str,
    event_type: str,
    data: dict[str, Any],
    event_id: UUID | None = None,
    occurred_at: datetime | None = None,
) -> str:
    """Build the envelope, sign it, and enqueue a delivery task.

    Returns the envelope's event ``id`` (``evt_<uuid>``) so callers (e.g.
    the test-event endpoint) can echo it back to the partner for trace
    correlation. The HMAC signing happens here at enqueue time so the
    signature timestamp matches the moment the event was *generated*,
    not the moment the worker happens to deliver it — that matters for
    the partner's replay-window check when retries fire hours later.
    """
    envelope = build_event_envelope(
        event_type=event_type,
        subscription_id=subscription_id,
        data=data,
        event_id=event_id,
        occurred_at=occurred_at,
    )
    body = serialize_envelope(envelope)
    signature, timestamp = sign_body(secret=secret, body=body)

    task = QueuedTask(
        task_type=TASK_TYPE,
        payload={
            "subscription_id": str(subscription_id),
            "organization_id": str(organization_id),
            "url": url,
            "envelope_id": envelope["id"],
            "event_type": event_type,
            "body": body.decode("utf-8"),
            "signature_header": signature,
            "timestamp_header": timestamp,
        },
        created_at=utcnow(),
        attempts=0,
    )
    ok = enqueue_task(task, _queue_name())
    if not ok:
        logger.warning(
            "partner_webhook.enqueue_failed subscription_id=%s event_type=%s",
            subscription_id,
            event_type,
        )
    return envelope["id"]


# === Consumer ============================================================


async def process_partner_webhook_task(task: QueuedTask) -> None:
    """Worker entry point — fires one delivery attempt.

    Returns normally on success OR partner-side failure (writes audit row
    + schedules retry as appropriate). Raises only on unrecoverable bugs
    so the shared worker can surface them.
    """
    payload = task.payload
    subscription_id = UUID(payload["subscription_id"])
    organization_id = UUID(payload["organization_id"])
    url = payload["url"]
    event_type = payload["event_type"]
    body_bytes = payload["body"].encode("utf-8")
    signature_header = payload["signature_header"]
    timestamp_header = payload["timestamp_header"]
    envelope_id = payload["envelope_id"]
    # ``evt_<uuid>`` — extract the UUID for the audit row's event_id column.
    event_uuid = UUID(envelope_id[len("evt_") :])

    attempt_number = task.attempts + 1  # 1-indexed for human-readable audit

    # Re-resolve the hostname before every fire (DNS-rebinding defense).
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    try:
        validate_resolved_host(hostname)
    except WebhookUrlValidationError as exc:
        await _record_failure_and_maybe_disable(
            subscription_id=subscription_id,
            organization_id=organization_id,
            event_type=event_type,
            event_id=event_uuid,
            attempts=attempt_number,
            http_status=None,
            reason=f"dns_resolved_to_private:{exc.reason}",
            status=DELIVERY_STATUS_REJECTED_DNS,
        )
        # No retry for DNS-rebinding — the URL is poisoned, retrying won't
        # help, and we don't want to waste the schedule on it. Auto-disable
        # will trigger if this keeps happening.
        return

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                content=body_bytes,
                headers={
                    "Content-Type": "application/json",
                    SIGNATURE_HEADER: signature_header,
                    TIMESTAMP_HEADER: timestamp_header,
                },
            )
        http_status = response.status_code
        ok = 200 <= http_status < 300
    except httpx.TimeoutException:
        http_status = None
        ok = False
        reason = "timeout"
    except httpx.HTTPError as exc:
        http_status = None
        ok = False
        reason = f"http_error:{type(exc).__name__}"
    else:
        reason = "" if ok else f"http_{http_status}"

    if ok:
        await _record_success(subscription_id=subscription_id)
        logger.info(
            "partner_webhook.delivered subscription_id=%s event_type=%s attempt=%d status=%d",
            subscription_id,
            event_type,
            attempt_number,
            http_status,
        )
        return

    # Failure path — either schedule a retry or dead-letter.
    is_final_attempt = task.attempts >= len(RETRY_DELAYS_SECONDS)
    audit_status = (
        DELIVERY_STATUS_DEAD_LETTERED if is_final_attempt else DELIVERY_STATUS_FAILED
    )
    await _record_failure_and_maybe_disable(
        subscription_id=subscription_id,
        organization_id=organization_id,
        event_type=event_type,
        event_id=event_uuid,
        attempts=attempt_number,
        http_status=http_status,
        reason=reason,
        status=audit_status,
    )

    if is_final_attempt:
        logger.warning(
            "partner_webhook.dead_lettered subscription_id=%s event_type=%s attempts=%d",
            subscription_id,
            event_type,
            attempt_number,
        )
        return

    # Schedule next attempt with the canonical delay.
    next_delay = RETRY_DELAYS_SECONDS[task.attempts]
    retry_task = QueuedTask(
        task_type=TASK_TYPE,
        payload=payload,  # same body + signature: partner replays must match
        created_at=task.created_at,
        attempts=task.attempts + 1,
    )
    enqueue_task_with_delay(
        retry_task,
        _queue_name(),
        delay_seconds=float(next_delay),
    )
    logger.info(
        "partner_webhook.retry_scheduled subscription_id=%s attempt=%d next_delay_s=%d",
        subscription_id,
        attempt_number,
        next_delay,
    )


async def _record_success(*, subscription_id: UUID) -> None:
    """Zero out ``consecutive_failures`` on the subscription. Best-effort."""
    async with async_session_maker() as session:
        sub = await session.get(PartnerWebhookSubscription, subscription_id)
        if sub is None:
            return
        if sub.consecutive_failures != 0:
            sub.consecutive_failures = 0
            session.add(sub)
            await session.commit()


async def _record_failure_and_maybe_disable(
    *,
    subscription_id: UUID,
    organization_id: UUID,
    event_type: str,
    event_id: UUID,
    attempts: int,
    http_status: int | None,
    reason: str,
    status: str,
) -> None:
    """Write the delivery audit row + bump consecutive_failures + auto-disable check."""
    async with async_session_maker() as session:
        # Audit row first — we want this persisted even if the subscription
        # was deleted between enqueue and fire.
        audit = PartnerWebhookDelivery(
            id=uuid4(),
            subscription_id=subscription_id,
            organization_id=organization_id,
            event_type=event_type,
            event_id=event_id,
            status=status,
            attempts=attempts,
            http_status=http_status,
            reason=reason,
        )
        session.add(audit)

        sub = await session.get(PartnerWebhookSubscription, subscription_id)
        if sub is not None:
            sub.consecutive_failures += 1
            if (
                sub.active
                and sub.consecutive_failures >= AUTO_DISABLE_CONSECUTIVE_FAILURES
            ):
                sub.active = False
                sub.auto_disabled_at = utcnow()
                logger.warning(
                    "partner_webhook.auto_disabled subscription_id=%s failures=%d",
                    subscription_id,
                    sub.consecutive_failures,
                )
            session.add(sub)
        await session.commit()


# === Convenience: synchronous queue-counting helper for diagnostics ======


def has_pending_partner_webhooks() -> bool:
    """Cheap health-check used by the operator dashboard (Step 10).

    Returns False on Redis errors (failures here shouldn't break the page).
    """
    try:
        import redis

        client = redis.Redis.from_url(settings.rq_redis_url)
        return bool(
            client.llen(_queue_name())
            or client.zcard(f"{_queue_name()}:scheduled")
        )
    except Exception:
        return False


# === Test-helper: drain queue synchronously (used by tests) ==============


async def _drain_partner_webhook_queue_for_tests(
    *,
    max_iterations: int = 10,
) -> int:
    """Test-only helper. NOT for production use.

    Drains the partner-webhook queue end-to-end on the same event loop so
    tests can verify dispatch behavior without running the worker loop.
    Caller is responsible for monkeypatching ``async_session_maker`` to
    point at the in-memory test session if isolation is required.
    """
    from app.services.queue import dequeue_task

    processed = 0
    for _ in range(max_iterations):
        task = dequeue_task(_queue_name())
        if task is None:
            break
        await process_partner_webhook_task(task)
        processed += 1
        await asyncio.sleep(0)
    return processed
