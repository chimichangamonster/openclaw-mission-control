# ruff: noqa: INP001
"""Tests for ``GET /api/v1/partner/webhooks/{id}/failures`` (Step 7).

Covers the cursor-paginated delivery-failure audit endpoint. The dispatcher
itself is tested separately in ``test_partner_webhook_dispatch.py`` — these
tests pre-seed audit rows directly and exercise the read endpoint.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.partner import router as partner_router
from app.core import partner_auth
from app.core.partner_auth import PartnerAuthContext
from app.db.session import get_session
from app.models.organizations import Organization
from app.models.partner_webhook_delivery import (
    DELIVERY_STATUS_FAILED,
    PartnerWebhookDelivery,
)
from app.models.partner_webhook_subscription import PartnerWebhookSubscription


# === Fixtures ============================================================


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
async def seeded_org_and_subscription(
    db_session: AsyncSession,
) -> tuple[Organization, PartnerWebhookSubscription]:
    org = Organization(id=uuid4(), name="Test", slug="test")
    sub = PartnerWebhookSubscription(
        organization_id=org.id,
        url="https://partner.example.com/hooks",
        events=[],
        secret_hash="dummy",
    )
    db_session.add(org)
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(org)
    await db_session.refresh(sub)
    return org, sub


def _build_app(
    db_session: AsyncSession,
    org: Organization,
) -> FastAPI:
    app = FastAPI()
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(partner_router)
    app.include_router(api_v1)

    ctx = PartnerAuthContext(
        api_key=SimpleNamespace(  # type: ignore[arg-type]
            id=uuid4(),
            organization_id=org.id,
            key_id="kid_test",
            scopes=["webhooks:manage"],
            rate_limit_override=None,
        ),
        organization=org,
    )

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


async def _seed_failures(
    db_session: AsyncSession,
    sub: PartnerWebhookSubscription,
    org_id: uuid4,
    n: int,
    *,
    base_time: datetime | None = None,
) -> list[PartnerWebhookDelivery]:
    """Insert N audit rows with strictly increasing created_at. Returns them oldest-first."""
    base = base_time or datetime(2026, 5, 21, 12, 0, 0)
    rows: list[PartnerWebhookDelivery] = []
    for i in range(n):
        row = PartnerWebhookDelivery(
            id=uuid4(),
            subscription_id=sub.id,
            organization_id=org_id,
            event_type="vc.test.ping",
            event_id=uuid4(),
            status=DELIVERY_STATUS_FAILED,
            attempts=1,
            http_status=502,
            reason="http_502",
            created_at=base + timedelta(seconds=i),
        )
        db_session.add(row)
        rows.append(row)
    await db_session.commit()
    return rows


# === Tests ==============================================================


@pytest.mark.asyncio
async def test_failures_returns_newest_first(
    db_session: AsyncSession,
    seeded_org_and_subscription: tuple[Organization, PartnerWebhookSubscription],
) -> None:
    org, sub = seeded_org_and_subscription
    rows = await _seed_failures(db_session, sub, org.id, n=5)
    expected_newest_first = list(reversed(rows))

    app = _build_app(db_session, org)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get(f"/api/v1/partner/webhooks/wh_{sub.id}/failures")

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["next_cursor"] is None  # all fit in one page
    ids_returned = [item["id"] for item in payload["items"]]
    ids_expected = [str(r.id) for r in expected_newest_first]
    assert ids_returned == ids_expected


@pytest.mark.asyncio
async def test_failures_paginates_with_cursor(
    db_session: AsyncSession,
    seeded_org_and_subscription: tuple[Organization, PartnerWebhookSubscription],
) -> None:
    org, sub = seeded_org_and_subscription
    rows = await _seed_failures(db_session, sub, org.id, n=7)
    newest_first = list(reversed(rows))

    app = _build_app(db_session, org)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # First page: 3 items, cursor present
        resp1 = await client.get(
            f"/api/v1/partner/webhooks/wh_{sub.id}/failures?limit=3",
        )
        assert resp1.status_code == 200
        page1 = resp1.json()
        assert len(page1["items"]) == 3
        assert page1["next_cursor"] is not None
        assert [i["id"] for i in page1["items"]] == [
            str(newest_first[0].id),
            str(newest_first[1].id),
            str(newest_first[2].id),
        ]

        # Second page using the cursor
        resp2 = await client.get(
            f"/api/v1/partner/webhooks/wh_{sub.id}/failures?limit=3&cursor={page1['next_cursor']}",
        )
        assert resp2.status_code == 200
        page2 = resp2.json()
        assert len(page2["items"]) == 3
        assert [i["id"] for i in page2["items"]] == [
            str(newest_first[3].id),
            str(newest_first[4].id),
            str(newest_first[5].id),
        ]

        # Third page wraps up
        resp3 = await client.get(
            f"/api/v1/partner/webhooks/wh_{sub.id}/failures?limit=3&cursor={page2['next_cursor']}",
        )
        assert resp3.status_code == 200
        page3 = resp3.json()
        assert len(page3["items"]) == 1
        assert page3["items"][0]["id"] == str(newest_first[6].id)
        assert page3["next_cursor"] is None


@pytest.mark.asyncio
async def test_failures_rejects_other_orgs_subscription(
    db_session: AsyncSession,
    seeded_org_and_subscription: tuple[Organization, PartnerWebhookSubscription],
) -> None:
    """Cross-org failure-listing attempt → 404."""
    _own_org, sub = seeded_org_and_subscription
    # Build app under a DIFFERENT org context.
    other_org = Organization(id=uuid4(), name="Other", slug="other")
    db_session.add(other_org)
    await db_session.commit()

    app = _build_app(db_session, other_org)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get(f"/api/v1/partner/webhooks/wh_{sub.id}/failures")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_failures_rejects_invalid_cursor(
    db_session: AsyncSession,
    seeded_org_and_subscription: tuple[Organization, PartnerWebhookSubscription],
) -> None:
    org, sub = seeded_org_and_subscription
    app = _build_app(db_session, org)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # Not even a UUID
        resp = await client.get(
            f"/api/v1/partner/webhooks/wh_{sub.id}/failures?cursor=garbage",
        )
        assert resp.status_code == 400

        # Valid UUID, but no such row
        resp2 = await client.get(
            f"/api/v1/partner/webhooks/wh_{sub.id}/failures?cursor={uuid4()}",
        )
        assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_failures_payload_excludes_internal_fields(
    db_session: AsyncSession,
    seeded_org_and_subscription: tuple[Organization, PartnerWebhookSubscription],
) -> None:
    """Audit rows should not surface internal fields like the raw subscription FK."""
    org, sub = seeded_org_and_subscription
    await _seed_failures(db_session, sub, org.id, n=1)

    app = _build_app(db_session, org)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get(f"/api/v1/partner/webhooks/wh_{sub.id}/failures")
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    # subscription_id is exposed in wh_-prefixed form
    assert item["subscription_id"].startswith("wh_")
    # The raw organization_id FK is never returned — partners know their own org
    assert "organization_id" not in item


@pytest.mark.asyncio
async def test_failures_rejects_unknown_subscription(
    db_session: AsyncSession,
    seeded_org_and_subscription: tuple[Organization, PartnerWebhookSubscription],
) -> None:
    """Non-existent ``wh_<uuid>`` → 404."""
    org, _sub = seeded_org_and_subscription
    app = _build_app(db_session, org)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get(f"/api/v1/partner/webhooks/wh_{uuid4()}/failures")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_failures_enforces_limit_bounds(
    db_session: AsyncSession,
    seeded_org_and_subscription: tuple[Organization, PartnerWebhookSubscription],
) -> None:
    """Limit ≤ 0 or > 200 rejected by Pydantic Query bounds."""
    org, sub = seeded_org_and_subscription
    app = _build_app(db_session, org)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp_high = await client.get(
            f"/api/v1/partner/webhooks/wh_{sub.id}/failures?limit=999",
        )
        resp_zero = await client.get(
            f"/api/v1/partner/webhooks/wh_{sub.id}/failures?limit=0",
        )
    assert resp_high.status_code == 422
    assert resp_zero.status_code == 422
