# ruff: noqa: INP001
"""Trade outcome scoring tests — Phase 3c Step 2.

Verifies the Langfuse tracing flow wired into ``execute_trade()``:
- Non-manual buy creates a Langfuse trace and persists ``trade_trace_id`` on the position.
- Manual buy does NOT create a trace.
- First-proposal-wins: averaging up on an existing traced position does NOT overwrite the trace_id.
- Full sell of a traced position submits an outcome score.
- Partial sell does NOT score — only full closes do.
- Langfuse disabled (``get_langfuse()`` returns None) degrades silently: no trace_id,
  no score call, trade still succeeds.
- Score sign matches P&L direction (positive on win, negative on loss).
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch
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
    check_org_rate_limit,
    get_portfolio_for_org,
    get_session,
    require_org_from_actor,
    require_org_member,
)
from app.api.paper_trading import router as paper_trading_router
from app.models.organization_members import OrganizationMember
from app.models.organization_settings import DEFAULT_FEATURE_FLAGS, OrganizationSettings
from app.models.organizations import Organization
from app.models.paper_trading import PaperPortfolio, PaperPosition
from app.models.users import User
from app.services.organizations import OrganizationContext

ORG_ID = uuid4()
USER_ID = uuid4()
STARTING_BALANCE = 10000.0


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
    from app.core.time import utcnow

    now = utcnow()
    org = Organization(id=ORG_ID, name="Scoring Test Org", created_at=now, updated_at=now)
    session.add(org)

    user = User(
        id=USER_ID,
        clerk_user_id="score-test-clerk",
        email="score@test.com",
        name="Score Tester",
        active_organization_id=ORG_ID,
    )
    session.add(user)

    member = OrganizationMember(
        id=uuid4(),
        organization_id=ORG_ID,
        user_id=USER_ID,
        role="owner",
        all_boards_read=True,
        all_boards_write=True,
        created_at=now,
        updated_at=now,
    )
    session.add(member)

    settings = OrganizationSettings(
        id=uuid4(),
        organization_id=ORG_ID,
        feature_flags_json=json.dumps({k: True for k in DEFAULT_FEATURE_FLAGS}),
    )
    session.add(settings)

    portfolio = PaperPortfolio(
        id=uuid4(),
        organization_id=ORG_ID,
        user_id=USER_ID,
        name="Scoring Portfolio",
        starting_balance=STARTING_BALANCE,
        cash_balance=STARTING_BALANCE,
    )
    session.add(portfolio)

    await session.commit()
    return {"org": org, "user": user, "member": member, "portfolio": portfolio}


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


async def _get_position(maker, symbol: str) -> PaperPosition | None:
    async with maker() as session:
        result = await session.execute(
            select(PaperPosition).where(PaperPosition.symbol == symbol)  # type: ignore[arg-type]
        )
        return result.scalars().first()


class TestTradeOutcomeScoring:
    """Langfuse trace creation on buy, outcome scoring on full close."""

    @pytest.mark.asyncio
    async def test_non_manual_buy_creates_trace_and_persists_id(self, env) -> None:
        pid = env["portfolio_id"]
        with patch(
            "app.api.paper_trading.trace_trade_proposal",
            return_value="trace-abc-123",
        ) as mock_trace:
            async with AsyncClient(
                transport=ASGITransport(app=env["app"]), base_url="http://test"
            ) as c:
                resp = await c.post(
                    f"/api/v1/paper-trading/portfolios/{pid}/trades",
                    params={
                        "symbol": "NVDA",
                        "trade_type": "buy",
                        "quantity": 10,
                        "price": 100.0,
                        "proposed_by": "stock-analyst",
                        "stop_loss": 90.0,
                        "take_profit": 120.0,
                    },
                )
            assert resp.status_code == 200
            mock_trace.assert_called_once()
            call_kwargs = mock_trace.call_args.kwargs
            assert call_kwargs["symbol"] == "NVDA"
            assert call_kwargs["proposed_by"] == "stock-analyst"
            assert call_kwargs["entry_price"] == 100.0

            pos = await _get_position(env["maker"], "NVDA")
            assert pos is not None
            assert pos.trade_trace_id == "trace-abc-123"

    @pytest.mark.asyncio
    async def test_manual_buy_does_not_create_trace(self, env) -> None:
        pid = env["portfolio_id"]
        with patch(
            "app.api.paper_trading.trace_trade_proposal",
            return_value="should-not-be-called",
        ) as mock_trace:
            async with AsyncClient(
                transport=ASGITransport(app=env["app"]), base_url="http://test"
            ) as c:
                resp = await c.post(
                    f"/api/v1/paper-trading/portfolios/{pid}/trades",
                    params={
                        "symbol": "MSFT",
                        "trade_type": "buy",
                        "quantity": 5,
                        "price": 200.0,
                        "proposed_by": "manual",
                    },
                )
            assert resp.status_code == 200
            mock_trace.assert_not_called()
            pos = await _get_position(env["maker"], "MSFT")
            assert pos is not None
            assert pos.trade_trace_id is None

    @pytest.mark.asyncio
    async def test_averaging_up_preserves_original_trace_id(self, env) -> None:
        """First-proposal-wins: later buys on same position don't overwrite trace_id."""
        pid = env["portfolio_id"]
        with patch(
            "app.api.paper_trading.trace_trade_proposal",
            side_effect=["trace-first", "trace-second"],
        ):
            async with AsyncClient(
                transport=ASGITransport(app=env["app"]), base_url="http://test"
            ) as c:
                # First buy creates position with trace-first
                await c.post(
                    f"/api/v1/paper-trading/portfolios/{pid}/trades",
                    params={
                        "symbol": "GOOG",
                        "trade_type": "buy",
                        "quantity": 10,
                        "price": 100.0,
                        "proposed_by": "stock-analyst",
                    },
                )
                # Second buy averages up — must NOT replace trace_id
                await c.post(
                    f"/api/v1/paper-trading/portfolios/{pid}/trades",
                    params={
                        "symbol": "GOOG",
                        "trade_type": "buy",
                        "quantity": 10,
                        "price": 120.0,
                        "proposed_by": "stock-analyst",
                    },
                )
            pos = await _get_position(env["maker"], "GOOG")
            assert pos is not None
            assert pos.trade_trace_id == "trace-first"

    @pytest.mark.asyncio
    async def test_full_sell_winning_position_scores_positive(self, env) -> None:
        pid = env["portfolio_id"]
        with (
            patch(
                "app.api.paper_trading.trace_trade_proposal",
                return_value="trace-win",
            ),
            patch("app.api.paper_trading.score_trace") as mock_score,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=env["app"]), base_url="http://test"
            ) as c:
                await c.post(
                    f"/api/v1/paper-trading/portfolios/{pid}/trades",
                    params={
                        "symbol": "AAPL",
                        "trade_type": "buy",
                        "quantity": 10,
                        "price": 100.0,
                        "proposed_by": "stock-analyst",
                    },
                )
                # Sell all at $120 — +20% win
                await c.post(
                    f"/api/v1/paper-trading/portfolios/{pid}/trades",
                    params={
                        "symbol": "AAPL",
                        "trade_type": "sell",
                        "quantity": 10,
                        "price": 120.0,
                        "proposed_by": "stock-analyst",
                        "notes": "take-profit hit",
                    },
                )
            mock_score.assert_called_once()
            call_kwargs = mock_score.call_args.kwargs
            assert call_kwargs["trace_id"] == "trace-win"
            assert call_kwargs["name"] == "trade_outcome"
            assert call_kwargs["value"] > 0  # winning trade
            assert call_kwargs["value"] == pytest.approx(0.20, abs=0.01)
            assert "take_profit" in (call_kwargs.get("comment") or "").lower()

    @pytest.mark.asyncio
    async def test_full_sell_losing_position_scores_negative(self, env) -> None:
        pid = env["portfolio_id"]
        with (
            patch(
                "app.api.paper_trading.trace_trade_proposal",
                return_value="trace-loss",
            ),
            patch("app.api.paper_trading.score_trace") as mock_score,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=env["app"]), base_url="http://test"
            ) as c:
                await c.post(
                    f"/api/v1/paper-trading/portfolios/{pid}/trades",
                    params={
                        "symbol": "TSLA",
                        "trade_type": "buy",
                        "quantity": 10,
                        "price": 100.0,
                        "proposed_by": "stock-analyst",
                        "stop_loss": 90.0,
                    },
                )
                # Sell all at $85 — -15% loss, stop triggered
                await c.post(
                    f"/api/v1/paper-trading/portfolios/{pid}/trades",
                    params={
                        "symbol": "TSLA",
                        "trade_type": "sell",
                        "quantity": 10,
                        "price": 85.0,
                        "proposed_by": "stock-analyst",
                        "notes": "stop-loss triggered",
                    },
                )
            mock_score.assert_called_once()
            call_kwargs = mock_score.call_args.kwargs
            assert call_kwargs["trace_id"] == "trace-loss"
            assert call_kwargs["value"] < 0
            assert call_kwargs["value"] == pytest.approx(-0.15, abs=0.01)
            assert "stop_loss" in (call_kwargs.get("comment") or "").lower()

    @pytest.mark.asyncio
    async def test_partial_sell_does_not_score(self, env) -> None:
        """Only full closes fire the outcome score — partial sells don't."""
        pid = env["portfolio_id"]
        with (
            patch(
                "app.api.paper_trading.trace_trade_proposal",
                return_value="trace-partial",
            ),
            patch("app.api.paper_trading.score_trace") as mock_score,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=env["app"]), base_url="http://test"
            ) as c:
                await c.post(
                    f"/api/v1/paper-trading/portfolios/{pid}/trades",
                    params={
                        "symbol": "AMZN",
                        "trade_type": "buy",
                        "quantity": 10,
                        "price": 100.0,
                        "proposed_by": "stock-analyst",
                    },
                )
                # Sell half — position stays open, no score yet
                await c.post(
                    f"/api/v1/paper-trading/portfolios/{pid}/trades",
                    params={
                        "symbol": "AMZN",
                        "trade_type": "sell",
                        "quantity": 5,
                        "price": 120.0,
                        "proposed_by": "stock-analyst",
                    },
                )
            mock_score.assert_not_called()

    @pytest.mark.asyncio
    async def test_sell_untraced_position_does_not_score(self, env) -> None:
        """Manual buys without a trace_id must not trigger a score on close."""
        pid = env["portfolio_id"]
        with patch("app.api.paper_trading.score_trace") as mock_score:
            async with AsyncClient(
                transport=ASGITransport(app=env["app"]), base_url="http://test"
            ) as c:
                # Manual buy — no trace_id
                await c.post(
                    f"/api/v1/paper-trading/portfolios/{pid}/trades",
                    params={
                        "symbol": "META",
                        "trade_type": "buy",
                        "quantity": 10,
                        "price": 100.0,
                        "proposed_by": "manual",
                    },
                )
                # Full close — nothing to score against
                await c.post(
                    f"/api/v1/paper-trading/portfolios/{pid}/trades",
                    params={
                        "symbol": "META",
                        "trade_type": "sell",
                        "quantity": 10,
                        "price": 110.0,
                        "proposed_by": "manual",
                    },
                )
            mock_score.assert_not_called()

    @pytest.mark.asyncio
    async def test_langfuse_disabled_degrades_silently(self, env) -> None:
        """When trace_trade_proposal returns None, trade succeeds and no score happens."""
        pid = env["portfolio_id"]
        with (
            patch(
                "app.api.paper_trading.trace_trade_proposal",
                return_value=None,
            ),
            patch("app.api.paper_trading.score_trace") as mock_score,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=env["app"]), base_url="http://test"
            ) as c:
                resp_buy = await c.post(
                    f"/api/v1/paper-trading/portfolios/{pid}/trades",
                    params={
                        "symbol": "AMD",
                        "trade_type": "buy",
                        "quantity": 10,
                        "price": 100.0,
                        "proposed_by": "stock-analyst",
                    },
                )
                assert resp_buy.status_code == 200
                resp_sell = await c.post(
                    f"/api/v1/paper-trading/portfolios/{pid}/trades",
                    params={
                        "symbol": "AMD",
                        "trade_type": "sell",
                        "quantity": 10,
                        "price": 110.0,
                        "proposed_by": "stock-analyst",
                    },
                )
                assert resp_sell.status_code == 200
            mock_score.assert_not_called()
            pos = await _get_position(env["maker"], "AMD")
            assert pos is not None
            assert pos.trade_trace_id is None


class TestTraceTradeProposalHelper:
    """Unit tests for the langfuse_client.trace_trade_proposal helper."""

    def test_returns_none_when_langfuse_disabled(self) -> None:
        from app.services.langfuse_client import trace_trade_proposal

        with patch("app.services.langfuse_client.get_langfuse", return_value=None):
            result = trace_trade_proposal(
                org_id="org-x",
                symbol="NVDA",
                side="long",
                quantity=10,
                entry_price=100.0,
                proposed_by="stock-analyst",
                asset_type="stock",
                stop_loss=90.0,
                take_profit=120.0,
                source_report="10 Bagger Report",
            )
        assert result is None

    def test_returns_trace_id_when_langfuse_active(self) -> None:
        from app.services.langfuse_client import trace_trade_proposal

        mock_span = MagicMock()
        mock_span.trace_id = "trace-xyz-789"
        mock_span.start_observation.return_value = MagicMock()
        mock_client = MagicMock()
        mock_client.start_observation.return_value = mock_span

        with patch(
            "app.services.langfuse_client.get_langfuse",
            return_value=mock_client,
        ):
            result = trace_trade_proposal(
                org_id="org-x",
                symbol="NVDA",
                side="long",
                quantity=10,
                entry_price=100.0,
                proposed_by="stock-analyst",
                asset_type="stock",
                stop_loss=None,
                take_profit=None,
                source_report=None,
            )
        assert result == "trace-xyz-789"
        mock_client.start_observation.assert_called_once()
        # Confirm key metadata made it into the observation
        call_kwargs = mock_client.start_observation.call_args.kwargs
        metadata = call_kwargs.get("metadata", {})
        assert metadata.get("org_id") == "org-x"
        assert metadata.get("symbol") == "NVDA"
        assert metadata.get("proposed_by") == "stock-analyst"
        assert metadata.get("entry_price") == 100.0

    def test_swallows_langfuse_exceptions(self) -> None:
        """Helper must never propagate Langfuse errors to the caller."""
        from app.services.langfuse_client import trace_trade_proposal

        mock_client = MagicMock()
        mock_client.start_observation.side_effect = RuntimeError("langfuse down")
        with patch(
            "app.services.langfuse_client.get_langfuse",
            return_value=mock_client,
        ):
            result = trace_trade_proposal(
                org_id="org-x",
                symbol="NVDA",
                side="long",
                quantity=10,
                entry_price=100.0,
                proposed_by="stock-analyst",
                asset_type="stock",
                stop_loss=None,
                take_profit=None,
                source_report=None,
            )
        assert result is None
