# ruff: noqa: INP001
"""Tests for partner webhook dispatch (Step 6 of Partner API v1).

Covers ``app/services/partner_webhook_dispatch.py`` and
``app/services/partner_webhook_signing.py``. Exercises the consumer
(``process_partner_webhook_task``) directly with hand-built ``QueuedTask``
objects so the tests don't depend on a real Redis.

The test event endpoint (``POST /api/v1/partner/webhooks/{id}/test``) is
covered alongside — it's a thin HTTP wrapper over the dispatcher's
``enqueue_partner_webhook_event`` producer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.partner import router as partner_router
from app.core import partner_auth
from app.core.partner_auth import PartnerAuthContext
from app.core.partner_tokens import hash_partner_secret
from app.db.session import get_session
from app.models.organizations import Organization
from app.models.partner_webhook_delivery import (
    DELIVERY_STATUS_DEAD_LETTERED,
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_REJECTED_DNS,
    PartnerWebhookDelivery,
)
from app.models.partner_webhook_subscription import PartnerWebhookSubscription
from app.services import partner_webhook_dispatch, partner_webhook_url_validation
from app.services.partner_webhook_dispatch import (
    AUTO_DISABLE_CONSECUTIVE_FAILURES,
    RETRY_DELAYS_SECONDS,
    TASK_TYPE,
    process_partner_webhook_task,
)
from app.services.partner_webhook_signing import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    build_event_envelope,
    serialize_envelope,
    sign_body,
    verify_signature,
)
from app.services.partner_webhook_url_validation import WebhookUrlValidationError
from app.services.queue import QueuedTask

# Capture the real AsyncClient class BEFORE any monkeypatch can rebind it,
# so the test-helper closures below can construct genuine clients with
# MockTransport without recursing into their own patch.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _mock_client_factory(handler):
    """Return a factory yielding a real AsyncClient bound to ``handler``.

    The factory is what tests pass to ``monkeypatch.setattr`` — patching the
    ``AsyncClient`` symbol in the dispatcher's ``httpx`` namespace. Because
    we close over ``_REAL_ASYNC_CLIENT`` (captured before patching), no
    recursion is possible.
    """

    def _factory(*args, **kwargs):
        return _REAL_ASYNC_CLIENT(
            transport=httpx.MockTransport(handler),
            timeout=kwargs.get("timeout"),
        )

    return _factory


# === Fixtures ===========================================================


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_org(db_session: AsyncSession) -> Organization:
    org = Organization(id=uuid4(), name="Test Partner Org", slug="test-partner-org")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture
async def seeded_subscription(
    db_session: AsyncSession,
    seeded_org: Organization,
) -> tuple[PartnerWebhookSubscription, str]:
    """Create a subscription with a known plaintext secret returned alongside."""
    secret = "whsec_known_test_secret_value"
    sub = PartnerWebhookSubscription(
        organization_id=seeded_org.id,
        url="https://partner.example.com/hooks",
        events=["vc.test.ping"],
        secret_hash=hash_partner_secret(secret),
        active=True,
        consecutive_failures=0,
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    return sub, secret


@pytest.fixture
def patched_session_maker(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Point the dispatcher's ``async_session_maker`` at the in-memory session.

    The dispatcher opens its own short-lived sessions via
    ``async_session_maker()`` to write audit rows; tests need those writes
    visible in the same in-memory DB the fixtures use.
    """

    @asynccontextmanager
    async def _fake_maker() -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setattr(
        partner_webhook_dispatch,
        "async_session_maker",
        _fake_maker,
    )


@pytest.fixture
def patched_dns_resolves_public(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass real DNS — the consumer's DNS-rebinding check always passes."""
    monkeypatch.setattr(
        partner_webhook_url_validation,
        "_resolve_all",
        lambda hostname: ["93.184.216.34"],
    )


def _build_task(
    *,
    subscription: PartnerWebhookSubscription,
    secret: str,
    event_type: str = "vc.test.ping",
    attempts: int = 0,
) -> tuple[QueuedTask, bytes, str]:
    """Build a QueuedTask the way the producer would. Returns (task, body, event_id)."""
    envelope = build_event_envelope(
        event_type=event_type,
        subscription_id=subscription.id,
        data={"message": "integration test"},
    )
    body = serialize_envelope(envelope)
    signature, timestamp = sign_body(secret=secret, body=body)
    task = QueuedTask(
        task_type=TASK_TYPE,
        payload={
            "subscription_id": str(subscription.id),
            "organization_id": str(subscription.organization_id),
            "url": subscription.url,
            "envelope_id": envelope["id"],
            "event_type": event_type,
            "body": body.decode("utf-8"),
            "signature_header": signature,
            "timestamp_header": timestamp,
        },
        created_at=datetime.now(UTC).replace(tzinfo=None),
        attempts=attempts,
    )
    return task, body, envelope["id"]


# === Signing primitives ===================================================


def test_sign_and_verify_round_trip() -> None:
    body = b'{"event":"vc.test.ping"}'
    sig, ts = sign_body(secret="abc123", body=body, timestamp_ms=1700000000000)
    assert sig.startswith("sha256=")
    assert ts == "1700000000000"
    assert verify_signature(
        secret="abc123",
        body=body,
        signature_header=sig,
        timestamp_header=ts,
        now_ms=1700000000000,
    )


def test_verify_rejects_tampered_body() -> None:
    body = b'{"event":"vc.test.ping"}'
    sig, ts = sign_body(secret="abc123", body=body, timestamp_ms=1700000000000)
    assert not verify_signature(
        secret="abc123",
        body=b'{"event":"evil"}',
        signature_header=sig,
        timestamp_header=ts,
        now_ms=1700000000000,
    )


def test_verify_rejects_wrong_secret() -> None:
    body = b'{"event":"vc.test.ping"}'
    sig, ts = sign_body(secret="abc123", body=body, timestamp_ms=1700000000000)
    assert not verify_signature(
        secret="wrong",
        body=body,
        signature_header=sig,
        timestamp_header=ts,
        now_ms=1700000000000,
    )


def test_verify_rejects_replay_outside_window() -> None:
    body = b'{"event":"vc.test.ping"}'
    sig, ts = sign_body(secret="abc123", body=body, timestamp_ms=1700000000000)
    # 6 minutes later — outside the 5-minute window.
    assert not verify_signature(
        secret="abc123",
        body=body,
        signature_header=sig,
        timestamp_header=ts,
        tolerance_seconds=300,
        now_ms=1700000000000 + 6 * 60 * 1000,
    )


def test_verify_accepts_within_window() -> None:
    body = b'{"event":"vc.test.ping"}'
    sig, ts = sign_body(secret="abc123", body=body, timestamp_ms=1700000000000)
    # 4 minutes later — within the 5-minute window.
    assert verify_signature(
        secret="abc123",
        body=body,
        signature_header=sig,
        timestamp_header=ts,
        tolerance_seconds=300,
        now_ms=1700000000000 + 4 * 60 * 1000,
    )


def test_envelope_shape_matches_scope_doc() -> None:
    sub_id = uuid4()
    env = build_event_envelope(
        event_type="vc.test.ping",
        subscription_id=sub_id,
        data={"message": "integration test"},
    )
    assert env["event"] == "vc.test.ping"
    assert env["id"].startswith("evt_")
    UUID(env["id"][len("evt_") :])  # parses as UUID
    assert env["subscription_id"] == f"wh_{sub_id}"
    assert env["data"] == {"message": "integration test"}
    assert "occurred_at" in env


# === Dispatch (consumer) ==================================================


@pytest.mark.asyncio
async def test_dispatch_success_marks_consecutive_failures_zero(
    patched_session_maker: None,
    patched_dns_resolves_public: None,
    db_session: AsyncSession,
    seeded_subscription: tuple[PartnerWebhookSubscription, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sub, secret = seeded_subscription
    # Pre-populate failures to verify they reset on success.
    sub.consecutive_failures = 3
    db_session.add(sub)
    await db_session.commit()

    task, body, event_id = _build_task(subscription=sub, secret=secret)

    captured: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(
        partner_webhook_dispatch.httpx,
        "AsyncClient",
        _mock_client_factory(_handler),
    )

    await process_partner_webhook_task(task)

    # consecutive_failures reset to 0
    await db_session.refresh(sub)
    assert sub.consecutive_failures == 0

    # No audit row was written (success path doesn't audit).
    rows = (await db_session.exec(select(PartnerWebhookDelivery))).all()
    assert rows == []

    # The outbound request carried the HMAC headers.
    assert len(captured) == 1
    req = captured[0]
    assert req.headers[SIGNATURE_HEADER].startswith("sha256=")
    assert req.headers[TIMESTAMP_HEADER].isdigit()
    assert req.content == body


@pytest.mark.asyncio
async def test_dispatch_failure_writes_audit_and_increments_counter(
    patched_session_maker: None,
    patched_dns_resolves_public: None,
    db_session: AsyncSession,
    seeded_subscription: tuple[PartnerWebhookSubscription, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sub, secret = seeded_subscription
    task, _, _ = _build_task(subscription=sub, secret=secret)

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    monkeypatch.setattr(
        partner_webhook_dispatch.httpx,
        "AsyncClient",
        _mock_client_factory(_handler),
    )
    # Stop the retry enqueue from actually touching Redis.
    enqueued: list[Any] = []
    monkeypatch.setattr(
        partner_webhook_dispatch,
        "enqueue_task_with_delay",
        lambda task, queue, delay_seconds: enqueued.append(
            (task, queue, delay_seconds)
        )
        or True,
    )

    await process_partner_webhook_task(task)

    await db_session.refresh(sub)
    assert sub.consecutive_failures == 1
    assert sub.active is True  # still under threshold

    rows = (await db_session.exec(select(PartnerWebhookDelivery))).all()
    assert len(rows) == 1
    audit = rows[0]
    assert audit.status == DELIVERY_STATUS_FAILED
    assert audit.http_status == 502
    assert audit.reason == "http_502"
    assert audit.attempts == 1

    # Retry was scheduled with the first canonical delay (1 minute).
    assert len(enqueued) == 1
    _retry_task, _q, delay = enqueued[0]
    assert delay == float(RETRY_DELAYS_SECONDS[0])


@pytest.mark.asyncio
async def test_dispatch_final_attempt_dead_letters(
    patched_session_maker: None,
    patched_dns_resolves_public: None,
    db_session: AsyncSession,
    seeded_subscription: tuple[PartnerWebhookSubscription, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When attempts == len(RETRY_DELAYS_SECONDS), no further retry, status=dead_lettered."""
    sub, secret = seeded_subscription
    # Build a task at the FINAL attempt — len(RETRY_DELAYS_SECONDS) prior failures.
    task, _, _ = _build_task(
        subscription=sub, secret=secret, attempts=len(RETRY_DELAYS_SECONDS)
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    monkeypatch.setattr(
        partner_webhook_dispatch.httpx,
        "AsyncClient",
        _mock_client_factory(_handler),
    )
    enqueued: list[Any] = []
    monkeypatch.setattr(
        partner_webhook_dispatch,
        "enqueue_task_with_delay",
        lambda task, queue, delay_seconds: enqueued.append(
            (task, queue, delay_seconds)
        )
        or True,
    )

    await process_partner_webhook_task(task)

    rows = (await db_session.exec(select(PartnerWebhookDelivery))).all()
    assert len(rows) == 1
    assert rows[0].status == DELIVERY_STATUS_DEAD_LETTERED
    assert rows[0].attempts == len(RETRY_DELAYS_SECONDS) + 1

    # No retry was scheduled after the final attempt.
    assert enqueued == []


@pytest.mark.asyncio
async def test_dispatch_auto_disables_after_threshold(
    patched_session_maker: None,
    patched_dns_resolves_public: None,
    db_session: AsyncSession,
    seeded_subscription: tuple[PartnerWebhookSubscription, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Subscription with N-1 prior failures auto-disables on the Nth."""
    sub, secret = seeded_subscription
    sub.consecutive_failures = AUTO_DISABLE_CONSECUTIVE_FAILURES - 1
    db_session.add(sub)
    await db_session.commit()

    task, _, _ = _build_task(subscription=sub, secret=secret)

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    monkeypatch.setattr(
        partner_webhook_dispatch.httpx,
        "AsyncClient",
        _mock_client_factory(_handler),
    )
    monkeypatch.setattr(
        partner_webhook_dispatch,
        "enqueue_task_with_delay",
        lambda *a, **kw: True,
    )

    await process_partner_webhook_task(task)

    await db_session.refresh(sub)
    assert sub.consecutive_failures == AUTO_DISABLE_CONSECUTIVE_FAILURES
    assert sub.active is False
    assert sub.auto_disabled_at is not None


@pytest.mark.asyncio
async def test_dispatch_rejects_dns_rebinding(
    patched_session_maker: None,
    db_session: AsyncSession,
    seeded_subscription: tuple[PartnerWebhookSubscription, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DNS now resolving to a private IP → reject without HTTP attempt."""
    sub, secret = seeded_subscription
    # Force DNS to "rebind" to a private address at fire time.
    monkeypatch.setattr(
        partner_webhook_url_validation,
        "_resolve_all",
        lambda hostname: ["10.0.0.5"],
    )

    task, _, _ = _build_task(subscription=sub, secret=secret)

    # If the dispatcher ever calls httpx, we want to know about it.
    called: list[Any] = []
    monkeypatch.setattr(
        partner_webhook_dispatch.httpx,
        "AsyncClient",
        lambda *args, **kwargs: called.append("nope")  # type: ignore[func-returns-value]
        or pytest.fail("DNS rejection should skip HTTP"),
    )
    monkeypatch.setattr(
        partner_webhook_dispatch,
        "enqueue_task_with_delay",
        lambda *a, **kw: True,
    )

    await process_partner_webhook_task(task)

    rows = (await db_session.exec(select(PartnerWebhookDelivery))).all()
    assert len(rows) == 1
    assert rows[0].status == DELIVERY_STATUS_REJECTED_DNS
    assert rows[0].reason.startswith("dns_resolved_to_private")
    assert rows[0].http_status is None
    assert called == []


@pytest.mark.asyncio
async def test_dispatch_timeout_recorded(
    patched_session_maker: None,
    patched_dns_resolves_public: None,
    db_session: AsyncSession,
    seeded_subscription: tuple[PartnerWebhookSubscription, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Network timeout → failure row with reason='timeout', http_status=None."""
    sub, secret = seeded_subscription
    task, _, _ = _build_task(subscription=sub, secret=secret)

    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout", request=request)

    monkeypatch.setattr(
        partner_webhook_dispatch.httpx,
        "AsyncClient",
        _mock_client_factory(_handler),
    )
    monkeypatch.setattr(
        partner_webhook_dispatch,
        "enqueue_task_with_delay",
        lambda *a, **kw: True,
    )

    await process_partner_webhook_task(task)

    rows = (await db_session.exec(select(PartnerWebhookDelivery))).all()
    assert len(rows) == 1
    assert rows[0].reason == "timeout"
    assert rows[0].http_status is None


@pytest.mark.asyncio
async def test_dispatch_retry_schedule_uses_per_attempt_delay(
    patched_session_maker: None,
    patched_dns_resolves_public: None,
    db_session: AsyncSession,
    seeded_subscription: tuple[PartnerWebhookSubscription, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each successive attempt schedules the next canonical delay from RETRY_DELAYS_SECONDS."""
    sub, secret = seeded_subscription

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    monkeypatch.setattr(
        partner_webhook_dispatch.httpx,
        "AsyncClient",
        _mock_client_factory(_handler),
    )
    delays: list[float] = []
    monkeypatch.setattr(
        partner_webhook_dispatch,
        "enqueue_task_with_delay",
        lambda task, queue, delay_seconds: delays.append(delay_seconds) or True,
    )

    # Fire attempts 0..N-1 in sequence — each should schedule the next delay.
    for attempts in range(len(RETRY_DELAYS_SECONDS)):
        task, _, _ = _build_task(subscription=sub, secret=secret, attempts=attempts)
        await process_partner_webhook_task(task)

    assert delays == [float(d) for d in RETRY_DELAYS_SECONDS]


# === Test event endpoint ==================================================


def _build_test_app(
    db_session: AsyncSession,
    ctx: PartnerAuthContext,
) -> FastAPI:
    app = FastAPI()
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(partner_router)
    app.include_router(api_v1)

    async def _override_require_webhooks() -> PartnerAuthContext:
        return ctx

    async def _override_rate_limit() -> None:
        return None

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[partner_auth.require_partner_webhooks_manage] = (
        _override_require_webhooks
    )
    app.dependency_overrides[partner_auth.check_partner_rate_limit] = (
        _override_rate_limit
    )
    app.dependency_overrides[get_session] = _override_session
    return app


@pytest.mark.asyncio
async def test_test_endpoint_fires_with_correct_secret(
    db_session: AsyncSession,
    seeded_subscription: tuple[PartnerWebhookSubscription, str],
) -> None:
    sub, secret = seeded_subscription
    ctx = PartnerAuthContext(
        api_key=SimpleNamespace(  # type: ignore[arg-type]
            id=uuid4(),
            organization_id=sub.organization_id,
            key_id="kid_test",
            scopes=["webhooks:manage"],
            rate_limit_override=None,
        ),
        organization=SimpleNamespace(id=sub.organization_id, slug="test"),  # type: ignore[arg-type]
    )
    app = _build_test_app(db_session, ctx)

    # Don't actually enqueue to Redis — capture the call instead.
    with patch.object(
        partner_webhook_dispatch,
        "enqueue_task",
        return_value=True,
    ) as fake_enqueue:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.post(
                f"/api/v1/partner/webhooks/wh_{sub.id}/test",
                json={"secret": secret},
            )

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["enqueued"] is True
    assert payload["event_id"].startswith("evt_")
    fake_enqueue.assert_called_once()


@pytest.mark.asyncio
async def test_test_endpoint_rejects_wrong_secret(
    db_session: AsyncSession,
    seeded_subscription: tuple[PartnerWebhookSubscription, str],
) -> None:
    sub, _correct_secret = seeded_subscription
    ctx = PartnerAuthContext(
        api_key=SimpleNamespace(  # type: ignore[arg-type]
            id=uuid4(),
            organization_id=sub.organization_id,
            key_id="kid_test",
            scopes=["webhooks:manage"],
            rate_limit_override=None,
        ),
        organization=SimpleNamespace(id=sub.organization_id, slug="test"),  # type: ignore[arg-type]
    )
    app = _build_test_app(db_session, ctx)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.post(
            f"/api/v1/partner/webhooks/wh_{sub.id}/test",
            json={"secret": "whsec_wrong"},
        )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_test_endpoint_rejects_inactive_subscription(
    db_session: AsyncSession,
    seeded_subscription: tuple[PartnerWebhookSubscription, str],
) -> None:
    sub, secret = seeded_subscription
    sub.active = False
    db_session.add(sub)
    await db_session.commit()

    ctx = PartnerAuthContext(
        api_key=SimpleNamespace(  # type: ignore[arg-type]
            id=uuid4(),
            organization_id=sub.organization_id,
            key_id="kid_test",
            scopes=["webhooks:manage"],
            rate_limit_override=None,
        ),
        organization=SimpleNamespace(id=sub.organization_id, slug="test"),  # type: ignore[arg-type]
    )
    app = _build_test_app(db_session, ctx)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.post(
            f"/api/v1/partner/webhooks/wh_{sub.id}/test",
            json={"secret": secret},
        )

    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_test_endpoint_rejects_other_orgs_subscription(
    db_session: AsyncSession,
    seeded_subscription: tuple[PartnerWebhookSubscription, str],
) -> None:
    """Cross-org test attempt → 404, not 403 (no existence leak)."""
    sub, secret = seeded_subscription
    # Build a context for a DIFFERENT org.
    other_org_id = uuid4()
    ctx = PartnerAuthContext(
        api_key=SimpleNamespace(  # type: ignore[arg-type]
            id=uuid4(),
            organization_id=other_org_id,
            key_id="kid_other",
            scopes=["webhooks:manage"],
            rate_limit_override=None,
        ),
        organization=SimpleNamespace(id=other_org_id, slug="other"),  # type: ignore[arg-type]
    )
    app = _build_test_app(db_session, ctx)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.post(
            f"/api/v1/partner/webhooks/wh_{sub.id}/test",
            json={"secret": secret},
        )

    assert resp.status_code == 404


# === Worker registration ==================================================


def test_dispatch_task_type_registered_in_shared_worker() -> None:
    """The shared queue worker MUST have a handler for PARTNER_WEBHOOK task type.

    Without this, enqueued partner webhooks would be silently logged as
    ``queue.worker.task_unhandled`` and dropped.
    """
    from app.services.queue_worker import _TASK_HANDLERS

    assert TASK_TYPE in _TASK_HANDLERS
    handler = _TASK_HANDLERS[TASK_TYPE]
    # The partner dispatcher owns its own retry loop, so the worker-level
    # requeue MUST be a no-op (returns False) — otherwise we'd double-retry.
    assert handler.requeue(None, 0.0) is False  # type: ignore[arg-type]


# === Sanity check: URL validator helper still rejects ====================


def test_validate_resolved_host_rejects_private_ip() -> None:
    """Defensive: the shared validator is what the dispatcher uses for rebinding."""
    from app.services.partner_webhook_url_validation import validate_resolved_host

    with pytest.raises(WebhookUrlValidationError):
        validate_resolved_host("127.0.0.1")
