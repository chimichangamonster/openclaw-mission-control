"""Polymarket wallet, risk config, market, trade, and position endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import ORG_MEMBER_DEP, SESSION_DEP, require_org_admin
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.polymarket_positions import PolymarketPosition
from app.models.polymarket_risk_config import PolymarketRiskConfig
from app.models.polymarket_wallets import PolymarketWallet
from app.models.trade_history import TradeHistory
from app.models.trade_proposals import TradeProposal
from app.schemas.polymarket import (
    MarketDetailRead,
    MarketSearchResult,
    PolymarketRiskConfigRead,
    PolymarketRiskConfigUpdate,
    PolymarketWalletCreate,
    PolymarketWalletRead,
    PositionRead,
    TradeHistoryRead,
    TradeProposalRead,
)
from app.services.organizations import OrganizationContext
from app.services.polymarket.credentials import derive_api_credentials, store_wallet
from app.services.polymarket.markets import get_market_detail, search_markets

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)
router = APIRouter(prefix="/polymarket", tags=["trading"])

ADMIN_DEP = Depends(require_org_admin)


# ---------------------------------------------------------------------------
# Wallet
# ---------------------------------------------------------------------------


@router.post("/wallet", response_model=PolymarketWalletRead, status_code=status.HTTP_201_CREATED)
async def connect_wallet(
    payload: PolymarketWalletCreate,
    ctx: OrganizationContext = ADMIN_DEP,
    session: AsyncSession = SESSION_DEP,
) -> PolymarketWallet:
    """Store an encrypted Polymarket wallet and derive API credentials."""
    wallet = await store_wallet(
        session,
        org_id=str(ctx.organization.id),
        private_key=payload.private_key,
        label=payload.label,
    )
    try:
        await derive_api_credentials(session, wallet)
    except Exception as exc:
        logger.warning("polymarket.wallet.derive_failed", extra={"error": str(exc)})
    await session.commit()
    await session.refresh(wallet)
    return wallet


@router.get("/wallet", response_model=PolymarketWalletRead | None)
async def get_wallet(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> PolymarketWallet | None:
    """Get wallet status (no secrets exposed)."""
    stmt = select(PolymarketWallet).where(
        PolymarketWallet.organization_id == ctx.organization.id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


@router.delete("/wallet", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_wallet(
    ctx: OrganizationContext = ADMIN_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    """Remove the Polymarket wallet."""
    stmt = select(PolymarketWallet).where(
        PolymarketWallet.organization_id == ctx.organization.id
    )
    wallet = (await session.execute(stmt)).scalar_one_or_none()
    if wallet:
        await session.delete(wallet)
        await session.commit()


@router.post("/wallet/derive-credentials", response_model=PolymarketWalletRead)
async def re_derive_credentials(
    ctx: OrganizationContext = ADMIN_DEP,
    session: AsyncSession = SESSION_DEP,
) -> PolymarketWallet:
    """Re-derive Polymarket API credentials from stored private key."""
    stmt = select(PolymarketWallet).where(
        PolymarketWallet.organization_id == ctx.organization.id
    )
    wallet = (await session.execute(stmt)).scalar_one_or_none()
    if wallet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No wallet configured.")
    await derive_api_credentials(session, wallet)
    await session.commit()
    await session.refresh(wallet)
    return wallet


# ---------------------------------------------------------------------------
# Risk Config
# ---------------------------------------------------------------------------


@router.get("/risk-config", response_model=PolymarketRiskConfigRead | None)
async def get_risk_config(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> PolymarketRiskConfig | None:
    """Get current risk configuration."""
    stmt = select(PolymarketRiskConfig).where(
        PolymarketRiskConfig.organization_id == ctx.organization.id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


@router.put("/risk-config", response_model=PolymarketRiskConfigRead)
async def update_risk_config(
    payload: PolymarketRiskConfigUpdate,
    ctx: OrganizationContext = ADMIN_DEP,
    session: AsyncSession = SESSION_DEP,
) -> PolymarketRiskConfig:
    """Update risk configuration including auto-execution settings."""
    from uuid import uuid4

    stmt = select(PolymarketRiskConfig).where(
        PolymarketRiskConfig.organization_id == ctx.organization.id
    )
    config = (await session.execute(stmt)).scalar_one_or_none()
    now = utcnow()

    if config is None:
        config = PolymarketRiskConfig(
            id=uuid4(),
            organization_id=ctx.organization.id,
            created_at=now,
            updated_at=now,
        )

    for field in (
        "max_trade_size_usdc",
        "daily_loss_limit_usdc",
        "weekly_loss_limit_usdc",
        "max_open_positions",
        "market_whitelist",
        "market_blacklist",
        "require_approval",
        "auto_execute_max_size_usdc",
        "auto_execute_min_confidence",
    ):
        value = getattr(payload, field, None)
        if value is not None:
            setattr(config, field, value)
    config.updated_at = now
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return config


# ---------------------------------------------------------------------------
# Markets (public data, proxied through backend)
# ---------------------------------------------------------------------------


@router.get("/markets", response_model=list[MarketSearchResult])
async def list_markets(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    q: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[MarketSearchResult]:
    """Search/browse Polymarket markets."""
    return await search_markets(q, limit=limit, offset=offset)


@router.get("/markets/{condition_id}", response_model=MarketDetailRead)
async def get_market(
    condition_id: str,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> MarketDetailRead:
    """Get market detail with current prices."""
    market = await get_market_detail(condition_id)
    if market is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return market


# ---------------------------------------------------------------------------
# Trade Proposals (read-only for users — agents create via agent endpoint)
# ---------------------------------------------------------------------------


@router.get("/trades", response_model=list[TradeProposalRead])
async def list_trade_proposals(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
    proposal_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[TradeProposal]:
    """List trade proposals for the organization."""
    stmt = (
        select(TradeProposal)
        .where(TradeProposal.organization_id == ctx.organization.id)
        .order_by(TradeProposal.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if proposal_status:
        stmt = stmt.where(TradeProposal.status == proposal_status)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/trades/{trade_id}", response_model=TradeProposalRead)
async def get_trade_proposal(
    trade_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> TradeProposal:
    """Get a single trade proposal."""
    proposal = await session.get(TradeProposal, trade_id)
    if proposal is None or proposal.organization_id != ctx.organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return proposal


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------


@router.get("/positions", response_model=list[PositionRead])
async def list_positions(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[PolymarketPosition]:
    """List current Polymarket positions."""
    stmt = (
        select(PolymarketPosition)
        .where(PolymarketPosition.organization_id == ctx.organization.id)
        .order_by(PolymarketPosition.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Trade History
# ---------------------------------------------------------------------------


@router.get("/history", response_model=list[TradeHistoryRead])
async def list_trade_history(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[TradeHistory]:
    """List executed trade history."""
    stmt = (
        select(TradeHistory)
        .where(TradeHistory.organization_id == ctx.organization.id)
        .order_by(TradeHistory.executed_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
