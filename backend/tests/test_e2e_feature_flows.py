# ruff: noqa: INP001
"""E2E feature flow tests — full lifecycle through HTTP endpoints.

Tests the happy-path flows that real users and agents exercise:
- Trade flow: buy → position created → sell → P&L realized → summary + equity curve
- Bet flow: place → resolve (won/lost/push) → bankroll updated → summary correct
- Watchlist flow: bulk add → update prices → summary → remove

Uses the same test harness as test_e2e_org_isolation.py: in-memory SQLite,
dependency overrides, real FastAPI routers.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import (
    get_portfolio_for_org,
    get_session,
    require_org_member,
    require_org_from_actor,
    check_org_rate_limit,
)
from app.api.paper_trading import router as paper_trading_router
from app.api.paper_bets import router as paper_bets_router
from app.api.watchlist import router as watchlist_router
from app.models.organization_members import OrganizationMember
from app.models.organization_settings import DEFAULT_FEATURE_FLAGS, OrganizationSettings
from app.models.organizations import Organization
from app.models.paper_trading import PaperPortfolio
from app.models.users import User
from app.services.organizations import OrganizationContext

# ---------------------------------------------------------------------------
# Test IDs
# ---------------------------------------------------------------------------

ORG_ID = uuid4()
USER_ID = uuid4()

STARTING_BALANCE = 10000.0


# ---------------------------------------------------------------------------
# Shared test engine / session
# ---------------------------------------------------------------------------


async def _make_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


async def _seed(session: AsyncSession) -> dict:
    """Seed one org with one empty portfolio — tests build state from scratch."""
    from app.core.time import utcnow

    now = utcnow()

    org = Organization(id=ORG_ID, name="Flow Test Org", created_at=now, updated_at=now)
    session.add(org)

    user = User(
        id=USER_ID, clerk_user_id="flow-test-clerk", email="flow@test.com",
        name="Flow Tester", active_organization_id=ORG_ID,
    )
    session.add(user)

    member = OrganizationMember(
        id=uuid4(), organization_id=ORG_ID, user_id=USER_ID,
        role="owner", all_boards_read=True, all_boards_write=True,
        created_at=now, updated_at=now,
    )
    session.add(member)

    settings = OrganizationSettings(
        id=uuid4(), organization_id=ORG_ID,
        feature_flags_json=json.dumps({k: True for k in DEFAULT_FEATURE_FLAGS}),
    )
    session.add(settings)

    portfolio = PaperPortfolio(
        id=uuid4(), organization_id=ORG_ID, user_id=USER_ID,
        name="Test Portfolio", starting_balance=STARTING_BALANCE,
        cash_balance=STARTING_BALANCE,
    )
    session.add(portfolio)

    await session.commit()
    return {
        "org": org, "user": user, "member": member,
        "portfolio": portfolio,
    }


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _build_app(
    session_maker: async_sessionmaker[AsyncSession],
    org_ctx: OrganizationContext,
) -> FastAPI:
    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        yield

    app = FastAPI(lifespan=_lifespan)
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(paper_trading_router)
    api_v1.include_router(paper_bets_router)
    api_v1.include_router(watchlist_router)
    app.include_router(api_v1)

    async def _override_session():
        async with session_maker() as session:
            yield session

    async def _override_org_member() -> OrganizationContext:
        return org_ctx

    async def _override_rate_limit() -> None:
        return None

    async def _override_portfolio(portfolio_id: UUID) -> PaperPortfolio:
        async with session_maker() as session:
            result = await session.execute(
                select(PaperPortfolio).where(
                    PaperPortfolio.id == portfolio_id,
                    PaperPortfolio.organization_id == org_ctx.organization.id,
                )
            )
            portfolio = result.scalars().first()
            if portfolio is None:
                raise HTTPException(status_code=404)
            return portfolio

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_org_member] = _override_org_member
    app.dependency_overrides[get_portfolio_for_org] = _override_portfolio
    app.dependency_overrides[check_org_rate_limit] = _override_rate_limit
    app.dependency_overrides[require_org_from_actor] = _override_org_member

    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def env():
    engine = await _make_engine()
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as session:
        data = await _seed(session)

    ctx = OrganizationContext(organization=data["org"], member=data["member"])
    app = _build_app(maker, ctx)

    yield {
        "app": app,
        "maker": maker,
        "data": data,
        "portfolio_id": str(data["portfolio"].id),
    }

    await engine.dispose()


# ===========================================================================
# TRADE FLOW TESTS
# ===========================================================================


class TestTradeFlow:
    """Buy → position created → sell → P&L realized → summary + equity curve."""

    @pytest.mark.asyncio
    async def test_buy_creates_position_and_deducts_cash(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={
                    "symbol": "NVDA", "trade_type": "buy", "quantity": 10,
                    "price": 100.0, "stop_loss": 90.0, "take_profit": 120.0,
                    "company_name": "NVIDIA", "sector": "Technology",
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["symbol"] == "NVDA"
            assert body["trade_type"] == "buy"
            assert body["quantity"] == 10
            assert body["fees"] == 9.99
            # Cash = 10000 - (10*100) - 9.99 = 8990.01
            assert body["cash_remaining"] == 8990.01

    @pytest.mark.asyncio
    async def test_position_appears_after_buy(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            # Buy
            await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "MSFT", "trade_type": "buy", "quantity": 5, "price": 200.0},
            )
            # Check positions
            resp = await c.get(f"/api/v1/paper-trading/portfolios/{pid}/positions")
            assert resp.status_code == 200
            positions = resp.json()
            msft = [p for p in positions if p["symbol"] == "MSFT"]
            assert len(msft) == 1
            assert msft[0]["quantity"] == 5
            assert msft[0]["entry_price"] == 200.0
            assert msft[0]["status"] == "open"

    @pytest.mark.asyncio
    async def test_second_buy_averages_up(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            # Buy 10 @ $100
            await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "GOOG", "trade_type": "buy", "quantity": 10, "price": 100.0},
            )
            # Buy 10 more @ $120 (average up)
            await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "GOOG", "trade_type": "buy", "quantity": 10, "price": 120.0},
            )
            # Check position: qty=20, entry_price=(100*10+120*10)/20=110
            resp = await c.get(f"/api/v1/paper-trading/portfolios/{pid}/positions")
            goog = [p for p in resp.json() if p["symbol"] == "GOOG"]
            assert len(goog) == 1
            assert goog[0]["quantity"] == 20
            assert goog[0]["entry_price"] == 110.0

    @pytest.mark.asyncio
    async def test_sell_realizes_pnl_and_closes_position(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            # Buy 10 @ $100
            await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "AAPL", "trade_type": "buy", "quantity": 10, "price": 100.0},
            )
            # Sell 10 @ $120 (profit = (120-100)*10 = $200)
            resp = await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "AAPL", "trade_type": "sell", "quantity": 10, "price": 120.0},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["trade_type"] == "sell"
            # Cash: 10000 - 1000 - 9.99 (buy) + 1200 - 9.99 (sell) = 10180.02
            assert body["cash_remaining"] == 10180.02

            # Position should be closed
            resp = await c.get(f"/api/v1/paper-trading/portfolios/{pid}/positions?status=all")
            aapl = [p for p in resp.json() if p["symbol"] == "AAPL"]
            assert len(aapl) == 1
            assert aapl[0]["status"] == "closed"
            assert aapl[0]["quantity"] == 0

    @pytest.mark.asyncio
    async def test_partial_sell_keeps_position_open(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            # Buy 20 @ $50
            await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "AMD", "trade_type": "buy", "quantity": 20, "price": 50.0},
            )
            # Sell 5 @ $60
            await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "AMD", "trade_type": "sell", "quantity": 5, "price": 60.0},
            )
            # Position still open with 15 remaining
            resp = await c.get(f"/api/v1/paper-trading/portfolios/{pid}/positions")
            amd = [p for p in resp.json() if p["symbol"] == "AMD"]
            assert len(amd) == 1
            assert amd[0]["status"] == "open"
            assert amd[0]["quantity"] == 15

    @pytest.mark.asyncio
    async def test_sell_without_position_returns_400(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "FAKE", "trade_type": "sell", "quantity": 5, "price": 100.0},
            )
            assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_insufficient_cash_returns_400(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "BRK", "trade_type": "buy", "quantity": 100, "price": 1000.0},
            )
            assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_summary_reflects_closed_trade(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            # Buy 10 @ $100, sell 10 @ $130 (win: $300)
            await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "WIN", "trade_type": "buy", "quantity": 10, "price": 100.0},
            )
            await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "WIN", "trade_type": "sell", "quantity": 10, "price": 130.0},
            )
            # Buy 5 @ $80, sell 5 @ $70 (loss: -$50)
            await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "LOSE", "trade_type": "buy", "quantity": 5, "price": 80.0},
            )
            await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "LOSE", "trade_type": "sell", "quantity": 5, "price": 70.0},
            )

            resp = await c.get(f"/api/v1/paper-trading/portfolios/{pid}/summary")
            assert resp.status_code == 200
            s = resp.json()
            assert s["closed_positions"] == 2
            assert s["winning_trades"] == 1
            assert s["losing_trades"] == 1
            assert s["win_rate_pct"] == 50.0
            assert s["realized_pnl"] == 250.0  # 300 - 50
            assert s["total_trades"] == 4  # 2 buys + 2 sells
            assert s["best_trade"]["symbol"] == "WIN"
            assert s["worst_trade"]["symbol"] == "LOSE"
            assert s["total_fees"] == 4 * 9.99  # 4 trades

    @pytest.mark.asyncio
    async def test_equity_curve_after_sell(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            # Buy 10 @ $100
            await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "CURV", "trade_type": "buy", "quantity": 10, "price": 100.0},
            )
            # Sell 10 @ $150 (realized P&L = $500)
            await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "CURV", "trade_type": "sell", "quantity": 10, "price": 150.0},
            )

            resp = await c.get(f"/api/v1/paper-trading/portfolios/{pid}/equity-curve")
            assert resp.status_code == 200
            curve = resp.json()
            # Should have at least one entry (sell creates realized P&L)
            assert len(curve) >= 1
            # Last entry should reflect realized gain
            last = curve[-1]
            assert last["cumulative_pnl"] == 500.0
            assert last["equity"] == STARTING_BALANCE + 500.0

    @pytest.mark.asyncio
    async def test_equity_curve_empty_before_any_sells(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            # Buy only — no sells means no realized P&L, empty curve
            await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "HOLD", "trade_type": "buy", "quantity": 5, "price": 50.0},
            )
            resp = await c.get(f"/api/v1/paper-trading/portfolios/{pid}/equity-curve")
            assert resp.status_code == 200
            assert resp.json() == []

    @pytest.mark.asyncio
    async def test_trade_list_records_all_trades(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "LOG", "trade_type": "buy", "quantity": 10, "price": 50.0},
            )
            await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "LOG", "trade_type": "sell", "quantity": 10, "price": 55.0},
            )
            resp = await c.get(f"/api/v1/paper-trading/portfolios/{pid}/trades")
            assert resp.status_code == 200
            trades = resp.json()
            log_trades = [t for t in trades if t["symbol"] == "LOG"]
            assert len(log_trades) == 2
            types = {t["trade_type"] for t in log_trades}
            assert types == {"buy", "sell"}

    @pytest.mark.asyncio
    async def test_portfolio_total_value_includes_positions(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            # Buy 10 @ $100 → cash drops by 1009.99
            await c.post(
                f"/api/v1/paper-trading/portfolios/{pid}/trades",
                params={"symbol": "VAL", "trade_type": "buy", "quantity": 10, "price": 100.0},
            )
            resp = await c.get(f"/api/v1/paper-trading/portfolios/{pid}")
            assert resp.status_code == 200
            p = resp.json()
            # positions_value = 10 * 100 = 1000
            # total_value = cash + positions = (10000 - 1009.99) + 1000 = 9990.01
            assert p["total_value"] == 9990.01


# ===========================================================================
# BET FLOW TESTS
# ===========================================================================


class TestBetFlow:
    """Place bet → resolve (won/lost/push) → bankroll updates → summary correct."""

    @pytest.mark.asyncio
    async def test_place_bet_deducts_stake(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/paper-bets/portfolios/{pid}/bets",
                params={
                    "sport": "nhl", "game": "EDM vs CGY", "game_date": "2026-03-22",
                    "bet_type": "moneyline", "selection": "EDM",
                    "odds": -150, "stake": 100, "confidence": 75,
                    "reasoning": "EDM at home", "book": "Bet365",
                },
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["sport"] == "nhl"
            assert body["stake"] == 100
            assert body["bankroll_remaining"] == STARTING_BALANCE - 100

    @pytest.mark.asyncio
    async def test_resolve_won_pays_out(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            # Place bet: $100 @ -150 odds → decimal = 1.6667 → payout = $166.67
            resp = await c.post(
                f"/api/v1/paper-bets/portfolios/{pid}/bets",
                params={
                    "sport": "nhl", "game": "TOR vs MTL", "game_date": "2026-03-22",
                    "bet_type": "moneyline", "selection": "TOR",
                    "odds": -150, "stake": 100, "book": "Bet365",
                },
            )
            bet_id = resp.json()["bet_id"]
            bankroll_after_bet = resp.json()["bankroll_remaining"]

            # Resolve as won
            resp = await c.patch(
                f"/api/v1/paper-bets/portfolios/{pid}/bets/{bet_id}",
                params={"result": "won"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "won"
            # Payout = 100 * (100/150 + 1) = 100 * 1.6667 = 166.67
            assert body["payout"] == pytest.approx(166.67, abs=0.01)
            assert body["pnl"] == pytest.approx(66.67, abs=0.01)
            # Bankroll = bankroll_after_bet + payout
            assert body["bankroll"] == pytest.approx(bankroll_after_bet + 166.67, abs=0.01)

    @pytest.mark.asyncio
    async def test_resolve_lost_zero_payout(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/paper-bets/portfolios/{pid}/bets",
                params={
                    "sport": "nba", "game": "LAL vs BOS", "game_date": "2026-03-22",
                    "bet_type": "spread", "selection": "LAL -3.5",
                    "odds": -110, "stake": 50, "book": "Bet365",
                },
            )
            bet_id = resp.json()["bet_id"]
            bankroll_after_bet = resp.json()["bankroll_remaining"]

            resp = await c.patch(
                f"/api/v1/paper-bets/portfolios/{pid}/bets/{bet_id}",
                params={"result": "lost"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "lost"
            assert body["payout"] == 0.0
            assert body["pnl"] == -50.0
            # Bankroll unchanged (stake already deducted)
            assert body["bankroll"] == bankroll_after_bet

    @pytest.mark.asyncio
    async def test_resolve_push_refunds_stake(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/paper-bets/portfolios/{pid}/bets",
                params={
                    "sport": "nfl", "game": "KC vs BUF", "game_date": "2026-03-22",
                    "bet_type": "spread", "selection": "KC -7",
                    "odds": -110, "stake": 75, "book": "Bet365",
                },
            )
            bet_id = resp.json()["bet_id"]
            bankroll_after_bet = resp.json()["bankroll_remaining"]

            resp = await c.patch(
                f"/api/v1/paper-bets/portfolios/{pid}/bets/{bet_id}",
                params={"result": "push"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "push"
            assert body["payout"] == 75.0
            assert body["pnl"] == 0.0
            # Bankroll restored (refund)
            assert body["bankroll"] == bankroll_after_bet + 75.0

    @pytest.mark.asyncio
    async def test_resolve_already_resolved_returns_400(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/paper-bets/portfolios/{pid}/bets",
                params={
                    "sport": "nhl", "game": "VAN vs SEA", "game_date": "2026-03-22",
                    "bet_type": "moneyline", "selection": "VAN",
                    "odds": +130, "stake": 40, "book": "Bet365",
                },
            )
            bet_id = resp.json()["bet_id"]

            # Resolve once
            await c.patch(
                f"/api/v1/paper-bets/portfolios/{pid}/bets/{bet_id}",
                params={"result": "won"},
            )
            # Try to resolve again
            resp = await c.patch(
                f"/api/v1/paper-bets/portfolios/{pid}/bets/{bet_id}",
                params={"result": "lost"},
            )
            assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_positive_odds_payout(self, env) -> None:
        """Underdog bet: +200 odds → $100 stake → $300 payout ($200 profit)."""
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/paper-bets/portfolios/{pid}/bets",
                params={
                    "sport": "mlb", "game": "NYY vs BOS", "game_date": "2026-03-22",
                    "bet_type": "moneyline", "selection": "BOS",
                    "odds": 200, "stake": 100, "book": "Bet365",
                },
            )
            bet_id = resp.json()["bet_id"]

            resp = await c.patch(
                f"/api/v1/paper-bets/portfolios/{pid}/bets/{bet_id}",
                params={"result": "won"},
            )
            body = resp.json()
            # +200: decimal = (200/100)+1 = 3.0 → payout = 300
            assert body["payout"] == 300.0
            assert body["pnl"] == 200.0

    @pytest.mark.asyncio
    async def test_bet_summary_after_mixed_results(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            # Bet 1: win $100 @ -150 (pnl ~+66.67)
            r1 = await c.post(
                f"/api/v1/paper-bets/portfolios/{pid}/bets",
                params={
                    "sport": "nhl", "game": "G1", "game_date": "2026-03-22",
                    "bet_type": "moneyline", "selection": "A",
                    "odds": -150, "stake": 100, "book": "Bet365",
                },
            )
            await c.patch(
                f"/api/v1/paper-bets/portfolios/{pid}/bets/{r1.json()['bet_id']}",
                params={"result": "won"},
            )

            # Bet 2: loss $50 @ -110 (pnl -50)
            r2 = await c.post(
                f"/api/v1/paper-bets/portfolios/{pid}/bets",
                params={
                    "sport": "nba", "game": "G2", "game_date": "2026-03-22",
                    "bet_type": "spread", "selection": "B",
                    "odds": -110, "stake": 50, "book": "Bet365",
                },
            )
            await c.patch(
                f"/api/v1/paper-bets/portfolios/{pid}/bets/{r2.json()['bet_id']}",
                params={"result": "lost"},
            )

            # Bet 3: push $30 (pnl 0)
            r3 = await c.post(
                f"/api/v1/paper-bets/portfolios/{pid}/bets",
                params={
                    "sport": "nhl", "game": "G3", "game_date": "2026-03-22",
                    "bet_type": "total", "selection": "Over 5.5",
                    "odds": -110, "stake": 30, "book": "Bet365",
                },
            )
            await c.patch(
                f"/api/v1/paper-bets/portfolios/{pid}/bets/{r3.json()['bet_id']}",
                params={"result": "push"},
            )

            # Check summary
            resp = await c.get(f"/api/v1/paper-bets/portfolios/{pid}/bets/summary")
            assert resp.status_code == 200
            s = resp.json()
            assert s["total_bets"] == 3
            assert s["wins"] == 1
            assert s["losses"] == 1
            assert s["pushes"] == 1
            assert s["pending_bets"] == 0
            # Win rate = 1/3 = 33.3%
            assert s["win_rate"] == pytest.approx(33.3, abs=0.1)
            # By sport: nhl has 1 win + 1 push, nba has 1 loss
            assert "nhl" in s["by_sport"]
            assert "nba" in s["by_sport"]
            assert s["by_sport"]["nhl"]["record"] == "1-0-1"
            assert s["by_sport"]["nba"]["record"] == "0-1-0"

    @pytest.mark.asyncio
    async def test_bet_list_filters_by_status(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            # Place two bets, resolve one
            r1 = await c.post(
                f"/api/v1/paper-bets/portfolios/{pid}/bets",
                params={
                    "sport": "nhl", "game": "FILT1", "game_date": "2026-03-22",
                    "bet_type": "moneyline", "selection": "X",
                    "odds": -110, "stake": 20, "book": "Bet365",
                },
            )
            await c.post(
                f"/api/v1/paper-bets/portfolios/{pid}/bets",
                params={
                    "sport": "nhl", "game": "FILT2", "game_date": "2026-03-22",
                    "bet_type": "moneyline", "selection": "Y",
                    "odds": -110, "stake": 20, "book": "Bet365",
                },
            )
            await c.patch(
                f"/api/v1/paper-bets/portfolios/{pid}/bets/{r1.json()['bet_id']}",
                params={"result": "won"},
            )

            # Filter pending only
            resp = await c.get(f"/api/v1/paper-bets/portfolios/{pid}/bets?status=pending")
            assert resp.status_code == 200
            pending = resp.json()
            assert all(b["status"] == "pending" for b in pending)
            assert any(b["game"] == "FILT2" for b in pending)

            # Filter won only
            resp = await c.get(f"/api/v1/paper-bets/portfolios/{pid}/bets?status=won")
            won = resp.json()
            assert all(b["status"] == "won" for b in won)


# ===========================================================================
# WATCHLIST FLOW TESTS
# ===========================================================================


class TestWatchlistFlow:
    """Bulk add → update prices → summary → remove."""

    @pytest.mark.asyncio
    async def test_bulk_add_items(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/watchlist/portfolios/{pid}/items/bulk",
                json=[
                    {"symbol": "NVDA", "yahoo_ticker": "NVDA", "company_name": "NVIDIA",
                     "sector": "Technology", "source_report": "Test Report"},
                    {"symbol": "MSFT", "yahoo_ticker": "MSFT", "company_name": "Microsoft",
                     "sector": "Technology", "source_report": "Test Report"},
                    {"symbol": "AAPL", "yahoo_ticker": "AAPL", "company_name": "Apple",
                     "sector": "Technology", "source_report": "Test Report"},
                ],
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["added"] == 3
            assert body["skipped"] == 0

    @pytest.mark.asyncio
    async def test_bulk_add_skips_duplicates(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            # Add once
            await c.post(
                f"/api/v1/watchlist/portfolios/{pid}/items/bulk",
                json=[
                    {"symbol": "DUP", "yahoo_ticker": "DUP", "source_report": "R1"},
                ],
            )
            # Add again — should skip
            resp = await c.post(
                f"/api/v1/watchlist/portfolios/{pid}/items/bulk",
                json=[
                    {"symbol": "DUP", "yahoo_ticker": "DUP", "source_report": "R2"},
                    {"symbol": "NEW", "yahoo_ticker": "NEW", "source_report": "R2"},
                ],
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["added"] == 1
            assert body["skipped"] == 1

    @pytest.mark.asyncio
    async def test_add_single_item(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/watchlist/portfolios/{pid}/items",
                params={
                    "symbol": "TSLA", "yahoo_ticker": "TSLA",
                    "company_name": "Tesla", "sector": "Auto",
                    "source_report": "Research Note",
                    "expected_low": 150.0, "expected_high": 300.0,
                },
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["symbol"] == "TSLA"
            assert body["status"] == "watching"

    @pytest.mark.asyncio
    async def test_update_price_and_sentiment(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            # Add item
            resp = await c.post(
                f"/api/v1/watchlist/portfolios/{pid}/items",
                params={"symbol": "UPD", "yahoo_ticker": "UPD", "source_report": "R"},
            )
            item_id = resp.json()["id"]

            # Update price + sentiment
            resp = await c.patch(
                f"/api/v1/watchlist/portfolios/{pid}/items/{item_id}",
                params={
                    "current_price": 42.50, "rsi": 35.0,
                    "volume_ratio": 1.5, "sentiment": "BULLISH",
                    "sentiment_confidence": 8,
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["current_price"] == 42.50
            assert body["rsi"] == 35.0
            assert body["sentiment"] == "BULLISH"

    @pytest.mark.asyncio
    async def test_update_status_to_alerting(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/watchlist/portfolios/{pid}/items",
                params={"symbol": "ALT", "yahoo_ticker": "ALT", "source_report": "R"},
            )
            item_id = resp.json()["id"]

            resp = await c.patch(
                f"/api/v1/watchlist/portfolios/{pid}/items/{item_id}",
                params={"status": "alerting", "alert_reason": "RSI below 30"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "alerting"

    @pytest.mark.asyncio
    async def test_summary_counts(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            # Add 3 items
            await c.post(
                f"/api/v1/watchlist/portfolios/{pid}/items/bulk",
                json=[
                    {"symbol": "S1", "yahoo_ticker": "S1", "source_report": "R"},
                    {"symbol": "S2", "yahoo_ticker": "S2", "source_report": "R"},
                    {"symbol": "S3", "yahoo_ticker": "S3", "source_report": "R"},
                ],
            )
            # Set one to alerting
            items_resp = await c.get(f"/api/v1/watchlist/portfolios/{pid}/items")
            items = items_resp.json()
            s2 = [i for i in items if i["symbol"] == "S2"][0]
            await c.patch(
                f"/api/v1/watchlist/portfolios/{pid}/items/{s2['id']}",
                params={"status": "alerting", "alert_reason": "Volume spike", "rsi": 25.0},
            )

            # Check summary
            resp = await c.get(f"/api/v1/watchlist/portfolios/{pid}/items/summary")
            assert resp.status_code == 200
            s = resp.json()
            assert s["watching"] == 2
            assert s["alerting"] == 1
            assert s["total"] == 3
            # Alerts array should contain the alerting item
            assert len(s["alerts"]) == 1
            assert s["alerts"][0]["symbol"] == "S2"

    @pytest.mark.asyncio
    async def test_remove_item(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/watchlist/portfolios/{pid}/items",
                params={"symbol": "DEL", "yahoo_ticker": "DEL", "source_report": "R"},
            )
            item_id = resp.json()["id"]

            # Delete
            resp = await c.delete(f"/api/v1/watchlist/portfolios/{pid}/items/{item_id}")
            assert resp.status_code == 204

            # Verify gone
            resp = await c.get(f"/api/v1/watchlist/portfolios/{pid}/items?status=all")
            assert not any(i["symbol"] == "DEL" for i in resp.json())

    @pytest.mark.asyncio
    async def test_duplicate_add_rejected(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            await c.post(
                f"/api/v1/watchlist/portfolios/{pid}/items",
                params={"symbol": "DUPE", "yahoo_ticker": "DUPE", "source_report": "R"},
            )
            resp = await c.post(
                f"/api/v1/watchlist/portfolios/{pid}/items",
                params={"symbol": "DUPE", "yahoo_ticker": "DUPE", "source_report": "R"},
            )
            # Should be rejected as duplicate (409 Conflict)
            assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_list_filters_by_status(self, env) -> None:
        pid = env["portfolio_id"]
        async with AsyncClient(transport=ASGITransport(app=env["app"]), base_url="http://test") as c:
            await c.post(
                f"/api/v1/watchlist/portfolios/{pid}/items/bulk",
                json=[
                    {"symbol": "F1", "yahoo_ticker": "F1", "source_report": "R"},
                    {"symbol": "F2", "yahoo_ticker": "F2", "source_report": "R"},
                ],
            )
            # Set F2 to bought
            items_resp = await c.get(f"/api/v1/watchlist/portfolios/{pid}/items?status=all")
            f2 = [i for i in items_resp.json() if i["symbol"] == "F2"][0]
            await c.patch(
                f"/api/v1/watchlist/portfolios/{pid}/items/{f2['id']}",
                params={"status": "bought"},
            )

            # Default filter (watching) should only show F1
            resp = await c.get(f"/api/v1/watchlist/portfolios/{pid}/items")
            symbols = [i["symbol"] for i in resp.json()]
            assert "F1" in symbols
            assert "F2" not in symbols
