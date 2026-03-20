"""Paper trading API — portfolios, positions, trades, and performance."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import get_session, require_org_member
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.paper_trading import PaperPortfolio, PaperPosition, PaperTrade
from app.services.organizations import OrganizationContext

logger = get_logger(__name__)
router = APIRouter(prefix="/paper-trading", tags=["paper-trading"])


@router.get("/portfolios")
async def list_portfolios(
    session: AsyncSession = Depends(get_session),
    org_ctx: OrganizationContext = Depends(require_org_member),
) -> list[dict]:
    stmt = select(PaperPortfolio).where(
        PaperPortfolio.organization_id == org_ctx.organization.id
    )
    result = await session.execute(stmt)
    portfolios = result.scalars().all()
    out = []
    for p in portfolios:
        # Count open positions
        pos_stmt = select(func.count()).where(
            PaperPosition.portfolio_id == p.id,
            PaperPosition.status == "open",
        )
        pos_count = (await session.execute(pos_stmt)).scalar() or 0
        out.append({
            "id": str(p.id),
            "name": p.name,
            "starting_balance": p.starting_balance,
            "cash_balance": p.cash_balance,
            "open_positions": pos_count,
            "created_at": p.created_at.isoformat(),
        })
    return out


@router.post("/portfolios", status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    session: AsyncSession = Depends(get_session),
    org_ctx: OrganizationContext = Depends(require_org_member),
    name: str = "Default Portfolio",
    starting_balance: float = 10000.0,
) -> dict:
    portfolio = PaperPortfolio(
        organization_id=org_ctx.organization.id,
        user_id=org_ctx.member.user_id,
        name=name,
        starting_balance=starting_balance,
        cash_balance=starting_balance,
    )
    session.add(portfolio)
    await session.commit()
    await session.refresh(portfolio)
    return {
        "id": str(portfolio.id),
        "name": portfolio.name,
        "starting_balance": portfolio.starting_balance,
        "cash_balance": portfolio.cash_balance,
    }


@router.get("/portfolios/{portfolio_id}")
async def get_portfolio(
    portfolio_id: UUID,
    session: AsyncSession = Depends(get_session),
    org_ctx: OrganizationContext = Depends(require_org_member),
) -> dict:
    stmt = select(PaperPortfolio).where(
        PaperPortfolio.id == portfolio_id,
        PaperPortfolio.organization_id == org_ctx.organization.id,
    )
    portfolio = (await session.execute(stmt)).scalar_one_or_none()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # Get open positions
    pos_stmt = select(PaperPosition).where(
        PaperPosition.portfolio_id == portfolio_id,
        PaperPosition.status == "open",
    )
    positions = (await session.execute(pos_stmt)).scalars().all()

    unrealized_pnl = 0.0
    positions_value = 0.0
    for pos in positions:
        price = pos.current_price or pos.entry_price
        if pos.side == "long":
            pnl = (price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - price) * pos.quantity
        unrealized_pnl += pnl
        positions_value += price * pos.quantity

    total_value = portfolio.cash_balance + positions_value
    total_return = ((total_value - portfolio.starting_balance) / portfolio.starting_balance) * 100

    return {
        "id": str(portfolio.id),
        "name": portfolio.name,
        "starting_balance": portfolio.starting_balance,
        "cash_balance": portfolio.cash_balance,
        "positions_value": round(positions_value, 2),
        "total_value": round(total_value, 2),
        "total_return_pct": round(total_return, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "open_positions": len(positions),
        "created_at": portfolio.created_at.isoformat(),
    }


@router.get("/portfolios/{portfolio_id}/positions")
async def list_positions(
    portfolio_id: UUID,
    session: AsyncSession = Depends(get_session),
    org_ctx: OrganizationContext = Depends(require_org_member),
    status_filter: str = Query("open", alias="status"),
) -> list[dict]:
    stmt = select(PaperPosition).where(
        PaperPosition.portfolio_id == portfolio_id,
    )
    if status_filter != "all":
        stmt = stmt.where(PaperPosition.status == status_filter)
    stmt = stmt.order_by(PaperPosition.entry_date.desc())

    positions = (await session.execute(stmt)).scalars().all()
    out = []
    for pos in positions:
        price = pos.current_price or pos.entry_price
        if pos.side == "long":
            pnl = (price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - price) * pos.quantity
        pnl_pct = ((price - pos.entry_price) / pos.entry_price * 100) if pos.entry_price else 0

        out.append({
            "id": str(pos.id),
            "symbol": pos.symbol,
            "asset_type": pos.asset_type,
            "side": pos.side,
            "quantity": pos.quantity,
            "entry_price": pos.entry_price,
            "current_price": price,
            "unrealized_pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "status": pos.status,
            "entry_date": pos.entry_date.isoformat(),
            "exit_date": pos.exit_date.isoformat() if pos.exit_date else None,
            "exit_price": pos.exit_price,
            "pnl_realized": pos.pnl_realized,
        })
    return out


@router.post("/portfolios/{portfolio_id}/trades")
async def execute_trade(
    portfolio_id: UUID,
    session: AsyncSession = Depends(get_session),
    org_ctx: OrganizationContext = Depends(require_org_member),
    symbol: str = "",
    asset_type: str = "stock",
    trade_type: str = "buy",
    quantity: float = 0.0,
    price: float = 0.0,
    proposed_by: str = "manual",
    notes: str = "",
) -> dict:
    # Get portfolio
    stmt = select(PaperPortfolio).where(
        PaperPortfolio.id == portfolio_id,
        PaperPortfolio.organization_id == org_ctx.organization.id,
    )
    portfolio = (await session.execute(stmt)).scalar_one_or_none()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    total = quantity * price
    fees = total * 0.001  # 0.1% simulated commission

    if trade_type == "buy":
        if portfolio.cash_balance < total + fees:
            raise HTTPException(status_code=400, detail="Insufficient cash balance")

        # Find existing open position or create new
        pos_stmt = select(PaperPosition).where(
            PaperPosition.portfolio_id == portfolio_id,
            PaperPosition.symbol == symbol,
            PaperPosition.asset_type == asset_type,
            PaperPosition.side == "long",
            PaperPosition.status == "open",
        )
        position = (await session.execute(pos_stmt)).scalar_one_or_none()

        if position:
            # Average up/down
            new_total_qty = position.quantity + quantity
            position.entry_price = (
                (position.entry_price * position.quantity + price * quantity) / new_total_qty
            )
            position.quantity = new_total_qty
            position.current_price = price
            position.updated_at = utcnow()
        else:
            position = PaperPosition(
                portfolio_id=portfolio_id,
                symbol=symbol,
                asset_type=asset_type,
                side="long",
                quantity=quantity,
                entry_price=price,
                current_price=price,
            )
            session.add(position)

        portfolio.cash_balance -= total + fees

    elif trade_type == "sell":
        # Find open long position
        pos_stmt = select(PaperPosition).where(
            PaperPosition.portfolio_id == portfolio_id,
            PaperPosition.symbol == symbol,
            PaperPosition.asset_type == asset_type,
            PaperPosition.side == "long",
            PaperPosition.status == "open",
        )
        position = (await session.execute(pos_stmt)).scalar_one_or_none()
        if not position:
            raise HTTPException(status_code=400, detail=f"No open position for {symbol}")
        if quantity > position.quantity:
            raise HTTPException(status_code=400, detail="Sell quantity exceeds position size")

        realized_pnl = (price - position.entry_price) * quantity
        position.quantity -= quantity
        position.pnl_realized += realized_pnl
        position.current_price = price
        position.updated_at = utcnow()

        if position.quantity <= 0:
            position.status = "closed"
            position.exit_date = utcnow()
            position.exit_price = price

        portfolio.cash_balance += total - fees

    else:
        raise HTTPException(status_code=400, detail="trade_type must be 'buy' or 'sell'")

    # Record the trade
    await session.flush()
    trade = PaperTrade(
        portfolio_id=portfolio_id,
        position_id=position.id if position else None,
        trade_type=trade_type,
        symbol=symbol,
        asset_type=asset_type,
        quantity=quantity,
        price=price,
        total=total,
        fees=fees,
        proposed_by=proposed_by,
        approval_status="auto",
        notes=notes,
    )
    session.add(trade)
    portfolio.updated_at = utcnow()

    await session.commit()
    return {
        "trade_id": str(trade.id),
        "symbol": symbol,
        "trade_type": trade_type,
        "quantity": quantity,
        "price": price,
        "total": total,
        "fees": round(fees, 2),
        "cash_remaining": round(portfolio.cash_balance, 2),
    }


@router.get("/portfolios/{portfolio_id}/trades")
async def list_trades(
    portfolio_id: UUID,
    session: AsyncSession = Depends(get_session),
    org_ctx: OrganizationContext = Depends(require_org_member),
    limit: int = Query(50, le=200),
) -> list[dict]:
    stmt = (
        select(PaperTrade)
        .where(PaperTrade.portfolio_id == portfolio_id)
        .order_by(PaperTrade.executed_at.desc())
        .limit(limit)
    )
    trades = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(t.id),
            "symbol": t.symbol,
            "asset_type": t.asset_type,
            "trade_type": t.trade_type,
            "quantity": t.quantity,
            "price": t.price,
            "total": t.total,
            "fees": t.fees,
            "proposed_by": t.proposed_by,
            "approval_status": t.approval_status,
            "notes": t.notes,
            "executed_at": t.executed_at.isoformat(),
        }
        for t in trades
    ]


@router.get("/portfolios/{portfolio_id}/summary")
async def portfolio_summary(
    portfolio_id: UUID,
    session: AsyncSession = Depends(get_session),
    org_ctx: OrganizationContext = Depends(require_org_member),
) -> dict:
    # Get portfolio
    stmt = select(PaperPortfolio).where(
        PaperPortfolio.id == portfolio_id,
        PaperPortfolio.organization_id == org_ctx.organization.id,
    )
    portfolio = (await session.execute(stmt)).scalar_one_or_none()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # Closed positions for win rate
    closed_stmt = select(PaperPosition).where(
        PaperPosition.portfolio_id == portfolio_id,
        PaperPosition.status == "closed",
    )
    closed = (await session.execute(closed_stmt)).scalars().all()

    winners = [p for p in closed if p.pnl_realized > 0]
    losers = [p for p in closed if p.pnl_realized < 0]
    total_realized = sum(p.pnl_realized for p in closed)
    best_trade = max(closed, key=lambda p: p.pnl_realized) if closed else None
    worst_trade = min(closed, key=lambda p: p.pnl_realized) if closed else None

    # Trade count
    trade_count = (await session.execute(
        select(func.count()).where(PaperTrade.portfolio_id == portfolio_id)
    )).scalar() or 0

    # Open positions unrealized
    open_stmt = select(PaperPosition).where(
        PaperPosition.portfolio_id == portfolio_id,
        PaperPosition.status == "open",
    )
    open_positions = (await session.execute(open_stmt)).scalars().all()
    positions_value = sum((p.current_price or p.entry_price) * p.quantity for p in open_positions)
    unrealized_pnl = sum(
        ((p.current_price or p.entry_price) - p.entry_price) * p.quantity
        for p in open_positions
    )

    total_value = portfolio.cash_balance + positions_value
    total_return_pct = ((total_value - portfolio.starting_balance) / portfolio.starting_balance) * 100

    return {
        "portfolio_id": str(portfolio.id),
        "name": portfolio.name,
        "starting_balance": portfolio.starting_balance,
        "cash_balance": round(portfolio.cash_balance, 2),
        "positions_value": round(positions_value, 2),
        "total_value": round(total_value, 2),
        "total_return_pct": round(total_return_pct, 2),
        "realized_pnl": round(total_realized, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "total_trades": trade_count,
        "closed_positions": len(closed),
        "winning_trades": len(winners),
        "losing_trades": len(losers),
        "win_rate_pct": round(len(winners) / len(closed) * 100, 1) if closed else 0,
        "best_trade": {
            "symbol": best_trade.symbol,
            "pnl": round(best_trade.pnl_realized, 2),
        } if best_trade else None,
        "worst_trade": {
            "symbol": worst_trade.symbol,
            "pnl": round(worst_trade.pnl_realized, 2),
        } if worst_trade else None,
    }
