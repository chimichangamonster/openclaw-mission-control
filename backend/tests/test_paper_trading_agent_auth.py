# ruff: noqa: INP001
"""Regression: paper-trading endpoints must accept agent actors, not just users.

Before this fix, `/paper-trading/*` used `require_org_member` which rejects agents,
so agent-driven cron skills got 401s even with valid agent tokens. This left
position.current_price NULL in prod.

These tests verify the auth dep is now `require_org_from_actor` (user OR agent)
by overriding the dep with a synthetic agent-derived OrganizationContext and
confirming the endpoint resolves the portfolio and returns data.

Actual agent-token → context resolution is covered in test_agent_auth_security.py.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import (
    check_org_rate_limit,
    get_session,
    require_feature,
    require_org_from_actor,
)
from app.api.paper_trading import router as paper_trading_router
from app.models.organization_members import OrganizationMember
from app.models.organization_settings import OrganizationSettings
from app.models.organizations import Organization
from app.models.paper_trading import PaperPortfolio, PaperPosition
from app.services.organizations import OrganizationContext

ORG_ID = uuid4()
OTHER_ORG_ID = uuid4()


async def _make_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


@pytest_asyncio.fixture
async def test_app():
    engine = await _make_engine()
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    portfolio_id = uuid4()
    position_id = uuid4()
    other_portfolio_id = uuid4()

    async with session_maker() as session:
        org = Organization(id=ORG_ID, name="Test Org", slug="test-org")
        other_org = Organization(id=OTHER_ORG_ID, name="Other Org", slug="other-org")
        session.add_all([org, other_org])
        session.add(
            OrganizationSettings(
                id=uuid4(),
                organization_id=ORG_ID,
                feature_flags_json=json.dumps({"paper_trading": True}),
            ),
        )
        session.add(
            PaperPortfolio(
                id=portfolio_id,
                organization_id=ORG_ID,
                user_id=ORG_ID,  # placeholder (synthetic agent-context uses org_id as user_id)
                name="Stocks",
                starting_balance=10000.0,
                cash_balance=5000.0,
            ),
        )
        session.add(
            PaperPosition(
                id=position_id,
                portfolio_id=portfolio_id,
                symbol="JNJ",
                asset_type="stock",
                quantity=10.0,
                entry_price=235.0,
                status="open",
            ),
        )
        session.add(
            PaperPortfolio(
                id=other_portfolio_id,
                organization_id=OTHER_ORG_ID,
                user_id=OTHER_ORG_ID,
                name="Other Stocks",
                starting_balance=10000.0,
                cash_balance=5000.0,
            ),
        )
        await session.commit()

    # Synthetic agent-derived context (matches what require_org_from_actor builds for agents)
    agent_ctx = OrganizationContext(
        organization=org,
        member=OrganizationMember(organization_id=ORG_ID, user_id=ORG_ID, role="operator"),
    )

    async def override_session():
        async with session_maker() as session:
            yield session

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app = FastAPI(lifespan=noop_lifespan)
    api = APIRouter(prefix="/api/v1")
    api.include_router(paper_trading_router)
    app.include_router(api)

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_org_from_actor] = lambda: agent_ctx
    app.dependency_overrides[check_org_rate_limit] = lambda: None
    app.dependency_overrides[require_feature("paper_trading")] = lambda: None

    # Make endpoint's module-level async_session_maker use our test DB
    import app.api.paper_trading as pt_mod

    pt_mod.async_session_maker = session_maker  # type: ignore[attr-defined]

    yield {
        "app": app,
        "portfolio_id": str(portfolio_id),
        "position_id": str(position_id),
        "other_portfolio_id": str(other_portfolio_id),
        "session_maker": session_maker,
    }

    await engine.dispose()


@pytest.mark.asyncio
async def test_agent_actor_can_list_positions(test_app) -> None:
    """Regression: agent-actor context resolves portfolio + positions correctly."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app["app"]), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v1/paper-trading/portfolios/{test_app['portfolio_id']}/positions",
        )

    assert resp.status_code == 200, resp.text
    positions = resp.json()
    assert isinstance(positions, list)
    assert len(positions) == 1
    assert positions[0]["symbol"] == "JNJ"


@pytest.mark.asyncio
async def test_agent_actor_can_patch_position_price(test_app) -> None:
    """The exact failure mode on VPS: agent PATCHed current_price, got 401, price stayed NULL."""
    portfolio_id = test_app["portfolio_id"]
    position_id = test_app["position_id"]

    async with AsyncClient(
        transport=ASGITransport(app=test_app["app"]), base_url="http://test"
    ) as client:
        resp = await client.patch(
            f"/api/v1/paper-trading/portfolios/{portfolio_id}/positions/{position_id}"
            f"?current_price=240.50",
        )

    assert resp.status_code == 200, resp.text

    # Verify the price actually landed in the DB — this is the regression
    from uuid import UUID

    async with test_app["session_maker"]() as session:
        refreshed = await session.get(PaperPosition, UUID(position_id))
        assert refreshed is not None
        assert refreshed.current_price == 240.50
        assert refreshed.price_updated_at is not None


@pytest.mark.asyncio
async def test_agent_from_other_org_cannot_access_portfolio(test_app) -> None:
    """Org isolation must hold — PORTFOLIO_DEP scopes to caller's org_id, returns 404."""
    other_portfolio_id = test_app["other_portfolio_id"]

    async with AsyncClient(
        transport=ASGITransport(app=test_app["app"]), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v1/paper-trading/portfolios/{other_portfolio_id}/positions",
        )

    # Agent context is for ORG_ID, portfolio belongs to OTHER_ORG_ID → 404
    assert resp.status_code == 404
