# ruff: noqa: INP001
"""Tests for the skill-config resolution endpoint.

Skills call GET /skill-config/resolve to look up portfolio and board UUIDs
by name instead of hardcoding them.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import check_org_rate_limit, get_session, require_org_from_actor
from app.api.skill_config import router as skill_config_router
from app.models.boards import Board
from app.models.organization_members import OrganizationMember
from app.models.organizations import Organization
from app.models.paper_trading import PaperPortfolio
from app.services.organizations import OrganizationContext

# ---------------------------------------------------------------------------
# Test IDs
# ---------------------------------------------------------------------------

ORG_ID = uuid4()
OTHER_ORG_ID = uuid4()
USER_ID = uuid4()

# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------


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

    # Seed data
    async with session_maker() as session:
        # Org
        org = Organization(id=ORG_ID, name="Test Org", slug="test-org")
        other_org = Organization(id=OTHER_ORG_ID, name="Other Org", slug="other-org")
        session.add_all([org, other_org])
        await session.flush()

        # Portfolios for our org
        p_stocks = PaperPortfolio(
            id=uuid4(),
            name="Stocks",
            organization_id=ORG_ID,
            user_id=USER_ID,
            starting_balance=10000,
            cash_balance=10000,
        )
        p_bets = PaperPortfolio(
            id=uuid4(),
            name="Sports Betting",
            organization_id=ORG_ID,
            user_id=USER_ID,
            starting_balance=1000,
            cash_balance=1000,
        )
        # Portfolio for other org (should NOT be returned)
        p_other = PaperPortfolio(
            id=uuid4(),
            name="Stocks",
            organization_id=OTHER_ORG_ID,
            user_id=USER_ID,
            starting_balance=5000,
            cash_balance=5000,
        )
        session.add_all([p_stocks, p_bets, p_other])

        # Boards for our org
        b_watchlist = Board(
            id=uuid4(),
            name="Stock Watchlist",
            slug="stock-watchlist",
            organization_id=ORG_ID,
        )
        b_sports = Board(
            id=uuid4(),
            name="Sports Betting",
            slug="sports-betting",
            organization_id=ORG_ID,
        )
        # Board for other org (should NOT be returned)
        b_other = Board(
            id=uuid4(),
            name="Stock Watchlist",
            slug="stock-watchlist",
            organization_id=OTHER_ORG_ID,
        )
        session.add_all([b_watchlist, b_sports, b_other])
        await session.commit()

    # Store IDs for assertions
    test_data = {
        "stocks_id": str(p_stocks.id),
        "bets_id": str(p_bets.id),
        "other_stocks_id": str(p_other.id),
        "watchlist_board_id": str(b_watchlist.id),
        "sports_board_id": str(b_sports.id),
        "other_board_id": str(b_other.id),
    }

    # Override dependencies
    async def override_session():
        async with session_maker() as session:
            yield session

    member = OrganizationMember(
        id=uuid4(),
        organization_id=ORG_ID,
        user_id=USER_ID,
        role="owner",
    )
    org_ctx = OrganizationContext(
        organization=org,
        member=member,
    )

    from fastapi import APIRouter, FastAPI

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app = FastAPI(lifespan=noop_lifespan)
    api = APIRouter(prefix="/api/v1")
    api.include_router(skill_config_router)
    app.include_router(api)

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_org_from_actor] = lambda: org_ctx
    app.dependency_overrides[check_org_rate_limit] = lambda: None

    # Monkeypatch async_session_maker so the endpoint uses our test DB
    import app.api.skill_config as sc_mod

    sc_mod.async_session_maker = session_maker

    yield app, test_data


@pytest.mark.asyncio
async def test_resolve_portfolios(test_app):
    app, data = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            "/api/v1/skill-config/resolve",
            params={"portfolios": ["Stocks", "Sports Betting"]},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["portfolios"]["Stocks"] == data["stocks_id"]
    assert body["portfolios"]["Sports Betting"] == data["bets_id"]


@pytest.mark.asyncio
async def test_resolve_boards(test_app):
    app, data = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            "/api/v1/skill-config/resolve",
            params={"boards": ["Stock Watchlist", "Sports Betting"]},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["boards"]["Stock Watchlist"] == data["watchlist_board_id"]
    assert body["boards"]["Sports Betting"] == data["sports_board_id"]


@pytest.mark.asyncio
async def test_resolve_both(test_app):
    app, data = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            "/api/v1/skill-config/resolve",
            params={
                "portfolios": ["Stocks"],
                "boards": ["Sports Betting"],
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["portfolios"]["Stocks"] == data["stocks_id"]
    assert body["boards"]["Sports Betting"] == data["sports_board_id"]


@pytest.mark.asyncio
async def test_resolve_empty_params(test_app):
    app, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/skill-config/resolve")
    assert resp.status_code == 200
    assert resp.json() == {"portfolios": {}, "boards": {}}


@pytest.mark.asyncio
async def test_resolve_nonexistent_name(test_app):
    app, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            "/api/v1/skill-config/resolve",
            params={"portfolios": ["Nonexistent"]},
        )
    assert resp.status_code == 200
    assert resp.json()["portfolios"] == {}


@pytest.mark.asyncio
async def test_resolve_does_not_leak_other_org(test_app):
    """Other org's 'Stocks' portfolio should not be returned."""
    app, data = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(
            "/api/v1/skill-config/resolve",
            params={"portfolios": ["Stocks"]},
        )
    assert resp.status_code == 200
    resolved_id = resp.json()["portfolios"]["Stocks"]
    assert resolved_id == data["stocks_id"]
    assert resolved_id != data["other_stocks_id"]
