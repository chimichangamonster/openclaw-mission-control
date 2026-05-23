# ruff: noqa: INP001
"""Tests for GET /platform/partner-webhooks-health (Step 10 widget endpoint).

Integration tests against an in-memory SQLite + FastAPI test client. Mirrors
the test_partner_webhooks.py fixture pattern (db_session + dependency
overrides) and the test_admin_partner_keys.py owner-override pattern.

Validates:
- owner-gating (non-owners get 401 — though we exercise the happy path via
  override, this stays a structural reminder)
- aggregation correctness for the three counters
- time-window semantics (hours param clamps + filters correctly)
- empty-DB case returns zeros (no NULL-zero confusion)
- overall_status tri-state honesty
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.platform_admin import router as platform_router
from app.core.platform_auth import require_platform_owner
from app.db.session import get_session
from app.models.organizations import Organization
from app.models.partner_webhook_delivery import (
    DELIVERY_STATUS_DEAD_LETTERED,
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_REJECTED_DNS,
    PartnerWebhookDelivery,
)
from app.models.partner_webhook_subscription import PartnerWebhookSubscription


# === Fixtures ===========================================================


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Fresh in-memory SQLite session per test, full SQLModel metadata."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_org(db_session: AsyncSession) -> Organization:
    """One org so subscription rows have a valid FK."""
    org = Organization(id=uuid4(), name="Test Partner Org", slug="test-partner-org")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


def _make_owner() -> SimpleNamespace:
    """Stub User for the require_platform_owner override.

    The endpoint only reads ``owner.id`` for the audit-log call, so a bare
    namespace with a UUID is enough — no need to construct a real User row.
    """
    return SimpleNamespace(id=uuid4(), email="owner@example.test", platform_role="owner")


@pytest.fixture
def app_factory(db_session: AsyncSession) -> FastAPI:
    """Minimal FastAPI app mounting platform_admin under /api/v1.

    Owner auth and the DB session are both injected via dependency_overrides.
    No audit-log mocking — the audit service writes to the test SQLite via
    the same session and is a no-op for our assertions.
    """
    app = FastAPI()
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(platform_router)
    app.include_router(api_v1)

    owner = _make_owner()

    async def _override_owner() -> SimpleNamespace:
        return owner

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[require_platform_owner] = _override_owner
    app.dependency_overrides[get_session] = _override_session

    app.state.owner = owner  # type: ignore[attr-defined]
    return app


@pytest_asyncio.fixture
async def client(app_factory: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app_factory),
        base_url="http://testserver",
    ) as ac:
        yield ac


# === Helpers ============================================================


def _make_delivery(
    *,
    org_id: UUID,
    subscription_id: UUID,
    status: str,
    created_at: datetime,
    attempts: int = 1,
    reason: str = "http_500",
) -> PartnerWebhookDelivery:
    return PartnerWebhookDelivery(
        id=uuid4(),
        subscription_id=subscription_id,
        organization_id=org_id,
        event_type="vc.test.ping",
        event_id=uuid4(),
        status=status,
        attempts=attempts,
        http_status=500 if reason.startswith("http_") else None,
        reason=reason,
        created_at=created_at,
    )


def _make_subscription(
    *,
    org_id: UUID,
    active: bool,
    auto_disabled_at: datetime | None,
    consecutive_failures: int = 0,
) -> PartnerWebhookSubscription:
    return PartnerWebhookSubscription(
        id=uuid4(),
        organization_id=org_id,
        url="https://example.com/webhook",
        events=["vc.test.ping"],
        secret_hash="placeholder-hash",
        active=active,
        auto_disabled_at=auto_disabled_at,
        consecutive_failures=consecutive_failures,
        created_at=datetime.now(UTC),
    )


# === Tests ==============================================================


@pytest.mark.asyncio
async def test_empty_db_returns_all_zeros_and_ok_status(client: AsyncClient) -> None:
    """No deliveries + no subs → all counters zero, status=ok."""
    resp = await client.get("/api/v1/platform/partner-webhooks-health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["failed_deliveries_window"] == 0
    assert body["dead_lettered_window"] == 0
    assert body["auto_disabled_subscriptions"] == 0
    assert body["overall_status"] == "ok"
    assert body["hours"] == 24


@pytest.mark.asyncio
async def test_failed_deliveries_in_window_counted(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_org: Organization,
) -> None:
    """3 failed deliveries inside 24h, 1 outside → count = 3."""
    sub_id = uuid4()
    now = datetime.now(UTC)
    db_session.add_all(
        [
            _make_delivery(
                org_id=seeded_org.id,
                subscription_id=sub_id,
                status=DELIVERY_STATUS_FAILED,
                created_at=now - timedelta(hours=1),
            ),
            _make_delivery(
                org_id=seeded_org.id,
                subscription_id=sub_id,
                status=DELIVERY_STATUS_FAILED,
                created_at=now - timedelta(hours=12),
            ),
            _make_delivery(
                org_id=seeded_org.id,
                subscription_id=sub_id,
                status=DELIVERY_STATUS_REJECTED_DNS,
                created_at=now - timedelta(hours=23),
                reason="dns_resolved_to_private",
            ),
            _make_delivery(
                org_id=seeded_org.id,
                subscription_id=sub_id,
                status=DELIVERY_STATUS_FAILED,
                created_at=now - timedelta(hours=48),  # OUTSIDE 24h window
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/v1/platform/partner-webhooks-health")

    assert resp.status_code == 200
    body = resp.json()
    # 3 in-window: 2 failed + 1 rejected_dns. failed_deliveries_window counts
    # ALL row types — it's "rows logged," not "status=failed rows."
    assert body["failed_deliveries_window"] == 3
    assert body["dead_lettered_window"] == 0
    assert body["overall_status"] == "ok"  # no dead-letters, no auto-disabled


@pytest.mark.asyncio
async def test_dead_lettered_counted_separately(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_org: Organization,
) -> None:
    """Dead-lettered rows are in the failed count AND in dead_lettered count."""
    sub_id = uuid4()
    now = datetime.now(UTC)
    db_session.add_all(
        [
            _make_delivery(
                org_id=seeded_org.id,
                subscription_id=sub_id,
                status=DELIVERY_STATUS_FAILED,
                created_at=now - timedelta(hours=1),
            ),
            _make_delivery(
                org_id=seeded_org.id,
                subscription_id=sub_id,
                status=DELIVERY_STATUS_DEAD_LETTERED,
                created_at=now - timedelta(hours=2),
                attempts=7,
            ),
            _make_delivery(
                org_id=seeded_org.id,
                subscription_id=sub_id,
                status=DELIVERY_STATUS_DEAD_LETTERED,
                created_at=now - timedelta(hours=3),
                attempts=7,
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/v1/platform/partner-webhooks-health")

    body = resp.json()
    assert body["failed_deliveries_window"] == 3  # all three rows
    assert body["dead_lettered_window"] == 2
    # Has dead-letters → warn (not error; the endpoint never returns error)
    assert body["overall_status"] == "warn"


@pytest.mark.asyncio
async def test_auto_disabled_subscriptions_state_snapshot(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_org: Organization,
) -> None:
    """auto_disabled_at populated + active=false → counted. State, not time-window."""
    now = datetime.now(UTC)
    db_session.add_all(
        [
            # Active sub — not counted.
            _make_subscription(
                org_id=seeded_org.id,
                active=True,
                auto_disabled_at=None,
            ),
            # Auto-disabled long ago — STILL counted (state snapshot).
            _make_subscription(
                org_id=seeded_org.id,
                active=False,
                auto_disabled_at=now - timedelta(days=30),
                consecutive_failures=20,
            ),
            # Auto-disabled recently — counted.
            _make_subscription(
                org_id=seeded_org.id,
                active=False,
                auto_disabled_at=now - timedelta(hours=2),
                consecutive_failures=20,
            ),
            # Inactive but NOT auto-disabled (e.g., manually deactivated in
            # some future flow) — NOT counted; the metric is specifically
            # auto-disabled, not just inactive.
            _make_subscription(
                org_id=seeded_org.id,
                active=False,
                auto_disabled_at=None,
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/v1/platform/partner-webhooks-health")

    body = resp.json()
    assert body["auto_disabled_subscriptions"] == 2
    # Auto-disabled present → warn.
    assert body["overall_status"] == "warn"


@pytest.mark.asyncio
async def test_hours_param_widens_window(
    client: AsyncClient,
    db_session: AsyncSession,
    seeded_org: Organization,
) -> None:
    """hours=72 picks up a failure 30h old that hours=24 missed."""
    sub_id = uuid4()
    now = datetime.now(UTC)
    db_session.add(
        _make_delivery(
            org_id=seeded_org.id,
            subscription_id=sub_id,
            status=DELIVERY_STATUS_FAILED,
            created_at=now - timedelta(hours=30),
        )
    )
    await db_session.commit()

    # Default 24h misses it.
    resp_default = await client.get("/api/v1/platform/partner-webhooks-health")
    assert resp_default.json()["failed_deliveries_window"] == 0

    # 72h catches it.
    resp_wide = await client.get("/api/v1/platform/partner-webhooks-health?hours=72")
    body = resp_wide.json()
    assert body["failed_deliveries_window"] == 1
    assert body["hours"] == 72


@pytest.mark.asyncio
async def test_hours_param_clamped_to_max_168(client: AsyncClient) -> None:
    """hours > 168 silently clamps to 168 (one week ceiling)."""
    resp = await client.get("/api/v1/platform/partner-webhooks-health?hours=999")
    body = resp.json()
    assert body["hours"] == 168


@pytest.mark.asyncio
async def test_hours_param_clamped_to_min_1(client: AsyncClient) -> None:
    """hours < 1 clamps to 1 (avoid divide-by-zero and negative-window confusion)."""
    resp = await client.get("/api/v1/platform/partner-webhooks-health?hours=0")
    body = resp.json()
    assert body["hours"] == 1


@pytest.mark.asyncio
async def test_response_shape_matches_contract(client: AsyncClient) -> None:
    """Lock the response keys the frontend widget consumes."""
    resp = await client.get("/api/v1/platform/partner-webhooks-health")
    body = resp.json()

    expected_keys = {
        "hours",
        "since",
        "failed_deliveries_window",
        "dead_lettered_window",
        "auto_disabled_subscriptions",
        "overall_status",
    }
    assert set(body.keys()) == expected_keys
    # since is an ISO timestamp string
    datetime.fromisoformat(body["since"].replace("Z", "+00:00"))
