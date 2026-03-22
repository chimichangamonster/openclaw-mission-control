"""Paper trading API — portfolios, positions, trades, and performance."""

from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, cast, Date
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import ORG_RATE_LIMIT_DEP, PORTFOLIO_DEP, get_session, require_feature, require_org_member
from app.core.logging import get_logger
from app.core.time import utcnow
from app.services.notifications import notify
from app.models.paper_trading import PaperPortfolio, PaperPosition, PaperTrade
from app.services.organizations import OrganizationContext

logger = get_logger(__name__)
router = APIRouter(
    prefix="/paper-trading",
    tags=["paper-trading"],
    dependencies=[Depends(require_feature("paper_trading")), ORG_RATE_LIMIT_DEP],
)


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
            "auto_trade": p.auto_trade,
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
    total_open_fees = 0.0
    positions_value = 0.0
    for pos in positions:
        price = pos.current_price or pos.entry_price
        if pos.side == "long":
            pnl = (price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - price) * pos.quantity
        unrealized_pnl += pnl - pos.total_fees
        total_open_fees += pos.total_fees
        positions_value += price * pos.quantity

    total_value = portfolio.cash_balance + positions_value
    total_return = ((total_value - portfolio.starting_balance) / portfolio.starting_balance) * 100

    return {
        "id": str(portfolio.id),
        "name": portfolio.name,
        "starting_balance": portfolio.starting_balance,
        "cash_balance": portfolio.cash_balance,
        "auto_trade": portfolio.auto_trade,
        "positions_value": round(positions_value, 2),
        "total_value": round(total_value, 2),
        "total_return_pct": round(total_return, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "open_positions": len(positions),
        "created_at": portfolio.created_at.isoformat(),
    }


@router.patch("/portfolios/{portfolio_id}/auto-trade")
async def toggle_auto_trade(
    portfolio_id: UUID,
    enabled: bool = True,
    session: AsyncSession = Depends(get_session),
    org_ctx: OrganizationContext = Depends(require_org_member),
) -> dict:
    """Toggle auto-trade on/off for a portfolio."""
    stmt = select(PaperPortfolio).where(
        PaperPortfolio.id == portfolio_id,
        PaperPortfolio.organization_id == org_ctx.organization.id,
    )
    portfolio = (await session.execute(stmt)).scalar_one_or_none()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    portfolio.auto_trade = enabled
    portfolio.updated_at = utcnow()
    await session.commit()
    return {"id": str(portfolio.id), "auto_trade": portfolio.auto_trade}


@router.get("/portfolios/{portfolio_id}/positions")
async def list_positions(
    session: AsyncSession = Depends(get_session),
    portfolio: PaperPortfolio = PORTFOLIO_DEP,
    status_filter: str = Query("open", alias="status"),
) -> list[dict]:
    stmt = select(PaperPosition).where(
        PaperPosition.portfolio_id == portfolio.id,
    )
    if status_filter != "all":
        stmt = stmt.where(PaperPosition.status == status_filter)
    stmt = stmt.order_by(PaperPosition.entry_date.desc())

    positions = (await session.execute(stmt)).scalars().all()
    out = []
    for pos in positions:
        price = pos.current_price or pos.entry_price
        if pos.side == "long":
            raw_pnl = (price - pos.entry_price) * pos.quantity
        else:
            raw_pnl = (pos.entry_price - price) * pos.quantity
        # Net P&L includes fees for open positions, realized P&L already factored for closed
        pnl = raw_pnl - pos.total_fees if pos.status == "open" else pos.pnl_realized
        cost_basis = pos.entry_price * pos.quantity + pos.total_fees
        pnl_pct = (raw_pnl - pos.total_fees) / cost_basis * 100 if cost_basis > 0 else 0

        out.append({
            "id": str(pos.id),
            "symbol": pos.symbol,
            "company_name": pos.company_name,
            "exchange": pos.exchange,
            "sector": pos.sector,
            "asset_type": pos.asset_type,
            "side": pos.side,
            "quantity": pos.quantity,
            "entry_price": pos.entry_price,
            "current_price": price,
            "unrealized_pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "stop_loss": pos.stop_loss,
            "take_profit": pos.take_profit,
            "source_report": pos.source_report,
            "status": pos.status,
            "entry_date": pos.entry_date.isoformat(),
            "exit_date": pos.exit_date.isoformat() if pos.exit_date else None,
            "exit_price": pos.exit_price,
            "pnl_realized": pos.pnl_realized,
            "total_fees": pos.total_fees,
            "trade_count": pos.trade_count,
            "hold_days": (((pos.exit_date or utcnow()).replace(tzinfo=None) - pos.entry_date.replace(tzinfo=None)).days) if pos.entry_date else 0,
            "price_updated_at": pos.price_updated_at.isoformat() if pos.price_updated_at else None,
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
    stop_loss: float | None = None,
    take_profit: float | None = None,
    company_name: str | None = None,
    exchange: str | None = None,
    sector: str | None = None,
    source_report: str | None = None,
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
    # Flat $9.99 per trade (realistic Canadian brokerage fee)
    fees = 9.99

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
            # Update metadata if provided (don't overwrite with None)
            if stop_loss is not None:
                position.stop_loss = stop_loss
            if take_profit is not None:
                position.take_profit = take_profit
            if company_name is not None:
                position.company_name = company_name
            if exchange is not None:
                position.exchange = exchange
            if sector is not None:
                position.sector = sector
            if source_report is not None:
                position.source_report = source_report
            position.total_fees += fees
            position.trade_count += 1
        else:
            position = PaperPosition(
                portfolio_id=portfolio_id,
                symbol=symbol,
                asset_type=asset_type,
                side="long",
                quantity=quantity,
                entry_price=price,
                current_price=price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                company_name=company_name,
                exchange=exchange,
                sector=sector,
                source_report=source_report,
                total_fees=fees,
                trade_count=1,
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
        position.total_fees += fees
        position.trade_count += 1
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

    # Notify #notifications channel
    emoji = "📈" if trade_type == "buy" else "📉"
    sl_str = f"Stop-loss: ${stop_loss:.2f} | " if stop_loss else ""
    tp_str = f"Take-profit: ${take_profit:.2f}" if take_profit else ""
    await notify(
        session,
        f"{emoji} TRADE EXECUTED\n\n"
        f"{trade_type.upper()} {quantity:.0f} {symbol} @ ${price:.2f}\n"
        f"Total: ${total:.2f} + ${fees:.2f} fee\n"
        f"{sl_str}{tp_str}\n"
        f"Cash remaining: ${portfolio.cash_balance:.2f}",
    )

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
    session: AsyncSession = Depends(get_session),
    portfolio: PaperPortfolio = PORTFOLIO_DEP,
    limit: int = Query(50, le=200),
) -> list[dict]:
    stmt = (
        select(PaperTrade)
        .where(PaperTrade.portfolio_id == portfolio.id)
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
        ((p.current_price or p.entry_price) - p.entry_price) * p.quantity - p.total_fees
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
        "avg_win": round(
            sum(p.pnl_realized for p in winners) / len(winners), 2
        ) if winners else 0,
        "avg_loss": round(
            sum(p.pnl_realized for p in losers) / len(losers), 2
        ) if losers else 0,
        "largest_win": round(best_trade.pnl_realized, 2) if best_trade else 0,
        "largest_loss": round(worst_trade.pnl_realized, 2) if worst_trade else 0,
        "profit_factor": round(
            abs(sum(p.pnl_realized for p in winners)) /
            abs(sum(p.pnl_realized for p in losers)), 2
        ) if losers and sum(p.pnl_realized for p in losers) != 0 else 0,
        "total_fees": round(
            sum(p.total_fees for p in closed) + sum(p.total_fees for p in open_positions), 2
        ),
        "avg_hold_days": round(
            sum((((p.exit_date or utcnow()).replace(tzinfo=None) - p.entry_date.replace(tzinfo=None)).days) for p in closed) / len(closed), 1
        ) if closed else 0,
    }


@router.patch("/portfolios/{portfolio_id}/positions/{position_id}")
async def update_position(
    position_id: UUID,
    session: AsyncSession = Depends(get_session),
    portfolio: PaperPortfolio = PORTFOLIO_DEP,
    current_price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    company_name: str | None = None,
    exchange: str | None = None,
    sector: str | None = None,
    source_report: str | None = None,
) -> dict:
    """Update position metadata — price, risk levels, or ticker info."""
    stmt = select(PaperPosition).where(
        PaperPosition.id == position_id,
        PaperPosition.portfolio_id == portfolio.id,
    )
    position = (await session.execute(stmt)).scalar_one_or_none()
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    if current_price is not None:
        position.current_price = current_price
        position.price_updated_at = utcnow()
    if stop_loss is not None:
        position.stop_loss = stop_loss
    if take_profit is not None:
        position.take_profit = take_profit
    if company_name is not None:
        position.company_name = company_name
    if exchange is not None:
        position.exchange = exchange
    if sector is not None:
        position.sector = sector
    if source_report is not None:
        position.source_report = source_report
    position.updated_at = utcnow()

    await session.commit()
    price = position.current_price or position.entry_price
    pnl = (price - position.entry_price) * position.quantity if position.side == "long" else (position.entry_price - price) * position.quantity
    return {
        "id": str(position.id),
        "symbol": position.symbol,
        "current_price": price,
        "stop_loss": position.stop_loss,
        "take_profit": position.take_profit,
        "unrealized_pnl": round(pnl, 2),
        "status": position.status,
    }


@router.get("/portfolios/{portfolio_id}/equity-curve")
async def equity_curve(
    portfolio_id: UUID,
    session: AsyncSession = Depends(get_session),
    org_ctx: OrganizationContext = Depends(require_org_member),
) -> list[dict]:
    """Daily equity curve: starting balance + cumulative realized P&L from trades."""
    # Verify portfolio
    stmt = select(PaperPortfolio).where(
        PaperPortfolio.id == portfolio_id,
        PaperPortfolio.organization_id == org_ctx.organization.id,
    )
    portfolio = (await session.execute(stmt)).scalar_one_or_none()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # Get all trades ordered by date
    trade_stmt = (
        select(PaperTrade)
        .where(PaperTrade.portfolio_id == portfolio_id)
        .order_by(PaperTrade.executed_at.asc())
    )
    trades = (await session.execute(trade_stmt)).scalars().all()

    if not trades:
        return []

    # Group realized P&L by day
    daily_pnl: dict[str, float] = defaultdict(float)
    for t in trades:
        day = t.executed_at.strftime("%Y-%m-%d")
        if t.trade_type == "sell":
            # Look up the position to get entry price for realized P&L
            pos_stmt = select(PaperPosition).where(PaperPosition.id == t.position_id)
            pos = (await session.execute(pos_stmt)).scalar_one_or_none()
            if pos:
                # Realized P&L for this sell
                daily_pnl[day] += (t.price - pos.entry_price) * t.quantity
        # For buys, no realized P&L

    # Build cumulative equity curve
    cumulative = 0.0
    curve = []
    for day in sorted(daily_pnl.keys()):
        cumulative += daily_pnl[day]
        curve.append({
            "date": day,
            "equity": round(portfolio.starting_balance + cumulative, 2),
            "daily_pnl": round(daily_pnl[day], 2),
            "cumulative_pnl": round(cumulative, 2),
        })

    return curve
