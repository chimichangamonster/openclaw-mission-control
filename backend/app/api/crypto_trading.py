"""Crypto exchange account, trade proposal, and position endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import (
    ORG_MEMBER_DEP,
    ORG_RATE_LIMIT_DEP,
    SESSION_DEP,
    require_feature,
    require_org_admin,
)
from app.core.logging import get_logger
from app.models.crypto_positions import CryptoPosition
from app.models.crypto_trade_proposals import CryptoTradeProposal
from app.models.exchange_accounts import ExchangeAccount
from app.schemas.crypto_trading import (
    CryptoPositionRead,
    CryptoTradeProposalRead,
    ExchangeAccountCreate,
    ExchangeAccountRead,
)
from app.services.binance.credentials import store_exchange_account
from app.services.organizations import OrganizationContext

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)
router = APIRouter(
    prefix="/crypto",
    tags=["trading"],
    dependencies=[Depends(require_feature("crypto_trading")), ORG_RATE_LIMIT_DEP],
)

ADMIN_DEP = Depends(require_org_admin)


# --- Exchange Account ---


@router.post("/accounts", response_model=ExchangeAccountRead, status_code=status.HTTP_201_CREATED)
async def connect_exchange(
    payload: ExchangeAccountCreate,
    ctx: OrganizationContext = ADMIN_DEP,
    session: AsyncSession = SESSION_DEP,
) -> ExchangeAccount:
    """Connect an exchange account with encrypted API credentials."""
    account = await store_exchange_account(
        session,
        org_id=str(ctx.organization.id),
        exchange=payload.exchange,
        api_key=payload.api_key,
        api_secret=payload.api_secret,
        label=payload.label,
    )
    await session.commit()
    await session.refresh(account)
    return account


@router.get("/accounts", response_model=list[ExchangeAccountRead])
async def list_exchange_accounts(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[ExchangeAccount]:
    """List connected exchange accounts."""
    stmt = (
        select(ExchangeAccount)
        .where(ExchangeAccount.organization_id == ctx.organization.id)  # type: ignore[arg-type]
        .order_by(ExchangeAccount.created_at.desc())  # type: ignore[attr-defined]
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_exchange(
    account_id: UUID,
    ctx: OrganizationContext = ADMIN_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    """Disconnect an exchange account."""
    account = await session.get(ExchangeAccount, account_id)
    if account is None or account.organization_id != ctx.organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await session.delete(account)
    await session.commit()


# --- Trade Proposals ---


@router.get("/trades", response_model=list[CryptoTradeProposalRead])
async def list_crypto_trades(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
    proposal_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[CryptoTradeProposal]:
    """List crypto trade proposals."""
    stmt = (
        select(CryptoTradeProposal)
        .where(CryptoTradeProposal.organization_id == ctx.organization.id)  # type: ignore[arg-type]
        .order_by(CryptoTradeProposal.created_at.desc())  # type: ignore[attr-defined]
        .offset(offset)
        .limit(limit)
    )
    if proposal_status:
        stmt = stmt.where(CryptoTradeProposal.status == proposal_status)  # type: ignore[arg-type]
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/trades/{trade_id}", response_model=CryptoTradeProposalRead)
async def get_crypto_trade(
    trade_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> CryptoTradeProposal:
    """Get a single crypto trade proposal."""
    proposal = await session.get(CryptoTradeProposal, trade_id)
    if proposal is None or proposal.organization_id != ctx.organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return proposal


# --- Positions ---


@router.get("/positions", response_model=list[CryptoPositionRead])
async def list_crypto_positions(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[CryptoPosition]:
    """List crypto positions from connected exchanges."""
    stmt = (
        select(CryptoPosition)
        .where(CryptoPosition.organization_id == ctx.organization.id)  # type: ignore[arg-type]
        .order_by(CryptoPosition.symbol)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
