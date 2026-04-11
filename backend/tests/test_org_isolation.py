# ruff: noqa: INP001
"""Integration tests for multi-tenant org isolation.

Verifies that portfolio-scoped queries correctly filter by organization_id,
preventing cross-org data access. Tests run against in-memory SQLite.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.paper_bets import PaperBet
from app.models.paper_trading import PaperPortfolio, PaperPosition, PaperTrade
from app.models.watchlist import WatchlistItem

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ORG_A_ID = uuid4()
ORG_B_ID = uuid4()
USER_A_ID = uuid4()
USER_B_ID = uuid4()


async def _make_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return maker


async def _seed(session: AsyncSession) -> dict:
    """Seed two orgs with portfolios + data."""
    pa = PaperPortfolio(
        id=uuid4(),
        organization_id=ORG_A_ID,
        user_id=USER_A_ID,
        name="Org A",
        starting_balance=10000,
        cash_balance=9000,
    )
    pb = PaperPortfolio(
        id=uuid4(),
        organization_id=ORG_B_ID,
        user_id=USER_B_ID,
        name="Org B",
        starting_balance=20000,
        cash_balance=18000,
    )
    session.add_all([pa, pb])

    pos_a = PaperPosition(
        id=uuid4(),
        portfolio_id=pa.id,
        symbol="AAPL",
        asset_type="stock",
        side="long",
        quantity=10,
        entry_price=150,
        current_price=155,
        status="open",
    )
    pos_b = PaperPosition(
        id=uuid4(),
        portfolio_id=pb.id,
        symbol="GOOG",
        asset_type="stock",
        side="long",
        quantity=5,
        entry_price=2800,
        current_price=2850,
        status="open",
    )
    session.add_all([pos_a, pos_b])

    trade_a = PaperTrade(
        id=uuid4(),
        portfolio_id=pa.id,
        trade_type="buy",
        symbol="AAPL",
        asset_type="stock",
        quantity=10,
        price=150,
        total=1500,
        fees=9.99,
        proposed_by="test",
        approval_status="auto",
    )
    session.add(trade_a)

    bet_a = PaperBet(
        id=uuid4(),
        portfolio_id=pa.id,
        sport="nhl",
        game="EDM vs CGY",
        bet_type="moneyline",
        selection="EDM",
        odds=-150,
        stake=50,
        status="pending",
    )
    session.add(bet_a)

    watch_a = WatchlistItem(
        id=uuid4(),
        portfolio_id=pa.id,
        symbol="TSLA",
        yahoo_ticker="TSLA",
        status="watching",
    )
    session.add(watch_a)

    await session.commit()
    return {
        "pa": pa,
        "pb": pb,
        "pos_a": pos_a,
        "pos_b": pos_b,
        "trade_a": trade_a,
        "bet_a": bet_a,
        "watch_a": watch_a,
    }


# ---------------------------------------------------------------------------
# Helper to run a test body with a fresh session
# ---------------------------------------------------------------------------


async def _with_session(test_fn):
    maker = await _make_session()
    async with maker() as session:
        data = await _seed(session)
        await test_fn(session, data)


# ---------------------------------------------------------------------------
# Portfolio isolation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_portfolio_visible_to_own_org() -> None:
    async def _test(session, data):
        result = await session.execute(
            select(PaperPortfolio).where(
                PaperPortfolio.id == data["pa"].id,
                PaperPortfolio.organization_id == ORG_A_ID,
            )
        )
        assert result.scalars().first() is not None

    await _with_session(_test)


@pytest.mark.asyncio
async def test_portfolio_invisible_to_other_org() -> None:
    async def _test(session, data):
        result = await session.execute(
            select(PaperPortfolio).where(
                PaperPortfolio.id == data["pa"].id,
                PaperPortfolio.organization_id == ORG_B_ID,
            )
        )
        assert result.scalars().first() is None, "Org B should not see Org A's portfolio"

    await _with_session(_test)


@pytest.mark.asyncio
async def test_list_portfolios_scoped() -> None:
    async def _test(session, data):
        result = await session.execute(
            select(PaperPortfolio).where(PaperPortfolio.organization_id == ORG_A_ID)
        )
        portfolios = result.scalars().all()
        assert len(portfolios) == 1
        assert portfolios[0].name == "Org A"

    await _with_session(_test)


# ---------------------------------------------------------------------------
# Position isolation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_positions_only_through_own_portfolio() -> None:
    async def _test(session, data):
        result = await session.execute(
            select(PaperPosition).where(PaperPosition.portfolio_id == data["pa"].id)
        )
        positions = result.scalars().all()
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"

    await _with_session(_test)


@pytest.mark.asyncio
async def test_positions_not_leaked_across_orgs() -> None:
    async def _test(session, data):
        result = await session.execute(
            select(PaperPosition).where(PaperPosition.portfolio_id == data["pa"].id)
        )
        symbols = [p.symbol for p in result.scalars().all()]
        assert "GOOG" not in symbols

    await _with_session(_test)


# ---------------------------------------------------------------------------
# Trade isolation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trades_scoped_to_portfolio() -> None:
    async def _test(session, data):
        result = await session.execute(
            select(PaperTrade).where(PaperTrade.portfolio_id == data["pa"].id)
        )
        trades = result.scalars().all()
        assert len(trades) == 1
        assert trades[0].symbol == "AAPL"

        result = await session.execute(
            select(PaperTrade).where(PaperTrade.portfolio_id == data["pb"].id)
        )
        assert len(result.scalars().all()) == 0

    await _with_session(_test)


# ---------------------------------------------------------------------------
# Bet isolation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bets_scoped_to_portfolio() -> None:
    async def _test(session, data):
        result = await session.execute(
            select(PaperBet).where(PaperBet.portfolio_id == data["pa"].id)
        )
        bets = result.scalars().all()
        assert len(bets) == 1
        assert bets[0].game == "EDM vs CGY"

    await _with_session(_test)


@pytest.mark.asyncio
async def test_bets_not_on_other_portfolio() -> None:
    async def _test(session, data):
        result = await session.execute(
            select(PaperBet).where(PaperBet.portfolio_id == data["pb"].id)
        )
        assert len(result.scalars().all()) == 0

    await _with_session(_test)


# ---------------------------------------------------------------------------
# Watchlist isolation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watchlist_scoped_to_portfolio() -> None:
    async def _test(session, data):
        result = await session.execute(
            select(WatchlistItem).where(WatchlistItem.portfolio_id == data["pa"].id)
        )
        items = result.scalars().all()
        assert len(items) == 1
        assert items[0].symbol == "TSLA"

    await _with_session(_test)


@pytest.mark.asyncio
async def test_watchlist_not_on_other_portfolio() -> None:
    async def _test(session, data):
        result = await session.execute(
            select(WatchlistItem).where(WatchlistItem.portfolio_id == data["pb"].id)
        )
        assert len(result.scalars().all()) == 0

    await _with_session(_test)


# ---------------------------------------------------------------------------
# Cross-org access pattern tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guessing_portfolio_id_with_wrong_org_fails() -> None:
    """Even knowing the UUID, wrong org_id returns nothing."""

    async def _test(session, data):
        result = await session.execute(
            select(PaperPortfolio).where(
                PaperPortfolio.id == data["pb"].id,
                PaperPortfolio.organization_id == ORG_A_ID,
            )
        )
        assert result.scalars().first() is None

    await _with_session(_test)


@pytest.mark.asyncio
async def test_all_data_accessible_by_correct_org() -> None:
    """Org A can access all of its own data through the portfolio."""

    async def _test(session, data):
        pa_id = data["pa"].id
        positions = (
            (
                await session.execute(
                    select(PaperPosition).where(PaperPosition.portfolio_id == pa_id)
                )
            )
            .scalars()
            .all()
        )
        trades = (
            (await session.execute(select(PaperTrade).where(PaperTrade.portfolio_id == pa_id)))
            .scalars()
            .all()
        )
        bets = (
            (await session.execute(select(PaperBet).where(PaperBet.portfolio_id == pa_id)))
            .scalars()
            .all()
        )
        watchlist = (
            (
                await session.execute(
                    select(WatchlistItem).where(WatchlistItem.portfolio_id == pa_id)
                )
            )
            .scalars()
            .all()
        )

        assert len(positions) == 1
        assert len(trades) == 1
        assert len(bets) == 1
        assert len(watchlist) == 1

    await _with_session(_test)
