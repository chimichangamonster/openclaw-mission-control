"""Agent-scoped Polymarket endpoints — propose trades, browse markets, check positions."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.core.agent_auth import AgentAuthContext, get_agent_auth_context
from app.core.logging import get_logger
from app.db.session import get_session
from app.models.polymarket_positions import PolymarketPosition
from app.models.trade_proposals import TradeProposal
from app.schemas.polymarket import (
    MarketDetailRead,
    MarketSearchResult,
    PositionRead,
    TradeProposalCreate,
    TradeProposalRead,
)
from app.services.polymarket.execution import create_trade_proposal
from app.services.polymarket.markets import get_market_detail, search_markets

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)
router = APIRouter(prefix="/agent/polymarket", tags=["agent"])

SESSION_DEP = Depends(get_session)
AGENT_CTX_DEP = Depends(get_agent_auth_context)


async def _get_org_id(agent_ctx: AgentAuthContext, session: AsyncSession) -> UUID:
    """Resolve organization_id from agent's board."""
    agent = agent_ctx.agent
    if agent.board_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent has no board.")
    from app.models.boards import Board

    board = await session.get(Board, agent.board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return board.organization_id


# ---------------------------------------------------------------------------
# Markets (read-only)
# ---------------------------------------------------------------------------


@router.get("/markets", response_model=list[MarketSearchResult])
async def agent_search_markets(
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    q: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[MarketSearchResult]:
    """Agent searches Polymarket markets."""
    return await search_markets(q, limit=limit, offset=offset)


@router.get("/markets/{condition_id}", response_model=MarketDetailRead)
async def agent_get_market(
    condition_id: str,
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
) -> MarketDetailRead:
    """Agent gets market detail."""
    market = await get_market_detail(condition_id)
    if market is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return market


# ---------------------------------------------------------------------------
# Trade Proposals (the ONLY way agents interact with trading)
# ---------------------------------------------------------------------------


@router.post("/trades", response_model=TradeProposalRead, status_code=status.HTTP_201_CREATED)
async def agent_propose_trade(
    payload: TradeProposalCreate,
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
) -> TradeProposal:
    """Agent proposes a trade. This creates a pending approval — NO direct execution.

    A human must approve the trade in Mission Control before it is executed.
    """
    agent = agent_ctx.agent
    org_id = await _get_org_id(agent_ctx, session)

    if agent.board_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    try:
        proposal = await create_trade_proposal(
            session,
            org_id=org_id,
            board_id=agent.board_id,
            agent_id=agent.id,
            params=payload,
        )
        await session.commit()
        await session.refresh(proposal)
        return proposal
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/trades", response_model=list[TradeProposalRead])
async def agent_list_proposals(
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
    proposal_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[TradeProposal]:
    """Agent lists its own trade proposals."""
    agent = agent_ctx.agent
    org_id = await _get_org_id(agent_ctx, session)

    stmt = (
        select(TradeProposal)
        .where(
            TradeProposal.organization_id == org_id,  # type: ignore[arg-type]
            TradeProposal.agent_id == agent.id,  # type: ignore[arg-type]
        )
        .order_by(TradeProposal.created_at.desc())  # type: ignore[attr-defined]
        .limit(limit)
    )
    if proposal_status:
        stmt = stmt.where(TradeProposal.status == proposal_status)  # type: ignore[arg-type]
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Positions (read-only)
# ---------------------------------------------------------------------------


@router.get("/positions", response_model=list[PositionRead])
async def agent_list_positions(
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[PolymarketPosition]:
    """Agent checks current positions."""
    org_id = await _get_org_id(agent_ctx, session)
    stmt = (
        select(PolymarketPosition)
        .where(PolymarketPosition.organization_id == org_id)  # type: ignore[arg-type]
        .order_by(PolymarketPosition.created_at.desc())  # type: ignore[attr-defined]
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
