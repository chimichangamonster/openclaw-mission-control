"""Paper sports betting API — place, list, resolve, and summarize bets."""


from __future__ import annotations

from typing import Any

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import (
    ORG_RATE_LIMIT_DEP,
    PORTFOLIO_DEP,
    get_session,
    require_feature,
    require_org_member,
)
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.paper_bets import PaperBet
from app.models.paper_trading import PaperPortfolio
from app.services.notifications import notify
from app.services.organizations import OrganizationContext

logger = get_logger(__name__)
router = APIRouter(
    prefix="/paper-bets",
    tags=["paper-bets"],
    dependencies=[Depends(require_feature("paper_bets")), ORG_RATE_LIMIT_DEP],
)


def _american_to_decimal(odds: int) -> float:
    """Convert American odds to decimal odds."""
    if odds > 0:
        return (odds / 100) + 1
    return (100 / abs(odds)) + 1


def _calculate_payout(stake: float, odds: int) -> float:
    """Calculate payout for a winning bet."""
    decimal_odds = _american_to_decimal(odds)
    return round(stake * decimal_odds, 2)


@router.post("/portfolios/{portfolio_id}/bets", status_code=status.HTTP_201_CREATED)
async def place_bet(
    portfolio_id: UUID,
    session: AsyncSession = Depends(get_session),
    org_ctx: OrganizationContext = Depends(require_org_member),
    sport: str = "nhl",
    game: str = "",
    game_date: str = "",
    bet_type: str = "moneyline",
    selection: str = "",
    player: str | None = None,
    prop_type: str | None = None,
    line: float | None = None,
    odds: int = 0,
    stake: float = 0.0,
    kelly_pct: float | None = None,
    confidence: float | None = None,
    proposed_by: str = "manual",
    reasoning: str = "",
    book: str = "",
) -> dict[str, Any]:
    """Place a paper sports bet. Deducts stake from portfolio cash balance."""
    # Verify portfolio
    stmt = select(PaperPortfolio).where(
        PaperPortfolio.id == portfolio_id,  # type: ignore[arg-type]
        PaperPortfolio.organization_id == org_ctx.organization.id,  # type: ignore[arg-type]
    )
    portfolio = (await session.execute(stmt)).scalar_one_or_none()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    if stake <= 0:
        raise HTTPException(status_code=400, detail="Stake must be positive")
    if portfolio.cash_balance < stake:
        raise HTTPException(status_code=400, detail="Insufficient bankroll")
    if odds == 0:
        raise HTTPException(status_code=400, detail="Odds required")

    now = utcnow()
    # Parse game_date if provided, otherwise default to now
    parsed_game_date = now
    if game_date:
        try:
            from datetime import datetime as _dt

            parsed_game_date = _dt.fromisoformat(game_date.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            parsed_game_date = now

    bet = PaperBet(
        portfolio_id=portfolio_id,
        sport=sport.lower(),
        game=game,
        game_date=parsed_game_date,
        bet_type=bet_type.lower(),
        selection=selection,
        player=player,
        prop_type=prop_type,
        line=line,
        odds=odds,
        stake=stake,
        kelly_pct=kelly_pct,
        confidence=confidence,
        status="pending",
        proposed_by=proposed_by,
        reasoning=reasoning,
        book=book,
        created_at=now,
        updated_at=now,
    )
    session.add(bet)

    # Deduct stake from bankroll
    portfolio.cash_balance -= stake
    portfolio.updated_at = now
    session.add(portfolio)

    await session.commit()
    await session.refresh(bet)

    potential_payout = _calculate_payout(stake, odds)

    return {
        "bet_id": str(bet.id),
        "sport": bet.sport,
        "game": bet.game,
        "selection": bet.selection,
        "odds": bet.odds,
        "stake": bet.stake,
        "potential_payout": potential_payout,
        "potential_profit": round(potential_payout - stake, 2),
        "bankroll_remaining": round(portfolio.cash_balance, 2),
    }


@router.get("/portfolios/{portfolio_id}/bets")
async def list_bets(
    session: AsyncSession = Depends(get_session),
    portfolio: PaperPortfolio = PORTFOLIO_DEP,
    status_filter: str = Query("all", alias="status"),
    limit: int = Query(50, le=200),
) -> list[dict[str, Any]]:
    """List paper bets for a portfolio."""
    stmt = select(PaperBet).where(PaperBet.portfolio_id == portfolio.id)  # type: ignore[arg-type]
    if status_filter != "all":
        stmt = stmt.where(PaperBet.status == status_filter)  # type: ignore[arg-type]
    stmt = stmt.order_by(PaperBet.created_at.desc()).limit(limit)  # type: ignore[attr-defined]

    bets = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(b.id),
            "sport": b.sport,
            "game": b.game,
            "game_date": b.game_date.isoformat() if b.game_date else None,
            "bet_type": b.bet_type,
            "selection": b.selection,
            "player": b.player,
            "prop_type": b.prop_type,
            "line": b.line,
            "odds": b.odds,
            "stake": b.stake,
            "kelly_pct": b.kelly_pct,
            "confidence": b.confidence,
            "status": b.status,
            "payout": b.payout,
            "pnl": b.pnl,
            "settled_at": b.settled_at.isoformat() if b.settled_at else None,
            "proposed_by": b.proposed_by,
            "reasoning": b.reasoning,
            "book": b.book,
            "created_at": b.created_at.isoformat(),
        }
        for b in bets
    ]


@router.patch("/portfolios/{portfolio_id}/bets/{bet_id}")
async def resolve_bet(
    bet_id: UUID,
    session: AsyncSession = Depends(get_session),
    portfolio: PaperPortfolio = PORTFOLIO_DEP,
    result: str = "won",  # won, lost, push, void
) -> dict[str, Any]:
    """Resolve a pending bet. Updates bankroll accordingly."""
    stmt = select(PaperBet).where(
        PaperBet.id == bet_id,  # type: ignore[arg-type]
        PaperBet.portfolio_id == portfolio.id,  # type: ignore[arg-type]
    )
    bet = (await session.execute(stmt)).scalar_one_or_none()
    if not bet:
        raise HTTPException(status_code=404, detail="Bet not found")
    if bet.status != "pending":
        raise HTTPException(status_code=400, detail=f"Bet already resolved: {bet.status}")
    if result not in ("won", "lost", "push", "void"):
        raise HTTPException(status_code=400, detail="Result must be won, lost, push, or void")

    now = utcnow()
    bet.status = result
    bet.settled_at = now
    bet.updated_at = now

    if result == "won":
        bet.payout = _calculate_payout(bet.stake, bet.odds)
        bet.pnl = round(bet.payout - bet.stake, 2)
        portfolio.cash_balance += bet.payout
    elif result == "lost":
        bet.payout = 0.0
        bet.pnl = -bet.stake
    elif result in ("push", "void"):
        bet.payout = bet.stake
        bet.pnl = 0.0
        portfolio.cash_balance += bet.stake

    portfolio.updated_at = now
    session.add(bet)
    session.add(portfolio)
    await session.commit()

    # Notify #notifications channel
    emoji = {"won": "✅", "lost": "❌", "push": "↩️", "void": "🚫"}.get(result, "🎲")
    pnl_str = f"+${bet.pnl:.2f}" if bet.pnl >= 0 else f"-${abs(bet.pnl):.2f}"
    await notify(
        session,
        f"{emoji} BET RESOLVED\n\n"
        f"{bet.game}: {bet.selection} — {result.upper()}\n"
        f"Odds: {bet.odds:+d} | Stake: ${bet.stake:.2f} | P&L: {pnl_str}\n"
        f"Bankroll: ${portfolio.cash_balance:.2f}",
    )

    return {
        "bet_id": str(bet.id),
        "status": bet.status,
        "payout": bet.payout,
        "pnl": bet.pnl,
        "bankroll": round(portfolio.cash_balance, 2),
    }


@router.get("/portfolios/{portfolio_id}/bets/summary")
async def bet_summary(
    session: AsyncSession = Depends(get_session),
    portfolio: PaperPortfolio = PORTFOLIO_DEP,
) -> dict[str, Any]:
    """Performance summary for sports betting."""
    # All resolved bets
    stmt = select(PaperBet).where(
        PaperBet.portfolio_id == portfolio.id,  # type: ignore[arg-type]
        PaperBet.status.in_(["won", "lost", "push"]),  # type: ignore[attr-defined]
    )
    resolved = (await session.execute(stmt)).scalars().all()

    # Pending bets
    pending_stmt = select(PaperBet).where(
        PaperBet.portfolio_id == portfolio.id,  # type: ignore[arg-type]
        PaperBet.status == "pending",  # type: ignore[arg-type]
    )
    pending = (await session.execute(pending_stmt)).scalars().all()

    wins = [b for b in resolved if b.status == "won"]
    losses = [b for b in resolved if b.status == "lost"]
    pushes = [b for b in resolved if b.status == "push"]

    total_staked = sum(b.stake for b in resolved)
    total_pnl = sum(b.pnl for b in resolved)
    total_won = sum(b.pnl for b in wins)
    total_lost = sum(b.pnl for b in losses)

    win_rate = round(len(wins) / len(resolved) * 100, 1) if resolved else 0

    # ROI = total P&L / total staked
    roi = round(total_pnl / total_staked * 100, 2) if total_staked > 0 else 0

    # By sport breakdown
    by_sport: dict[str, dict[str, Any]] = {}
    for b in resolved:
        if b.sport not in by_sport:
            by_sport[b.sport] = {"wins": 0, "losses": 0, "pushes": 0, "pnl": 0.0, "staked": 0.0}
        s = by_sport[b.sport]
        s["staked"] += b.stake
        s["pnl"] += b.pnl
        if b.status == "won":
            s["wins"] += 1
        elif b.status == "lost":
            s["losses"] += 1
        else:
            s["pushes"] += 1

    # By bet type breakdown
    by_type: dict[str, dict[str, Any]] = {}
    for b in resolved:
        if b.bet_type not in by_type:
            by_type[b.bet_type] = {"wins": 0, "losses": 0, "pnl": 0.0}
        t = by_type[b.bet_type]
        t["pnl"] += b.pnl
        if b.status == "won":
            t["wins"] += 1
        elif b.status == "lost":
            t["losses"] += 1

    # Best and worst bets
    best = max(resolved, key=lambda b: b.pnl) if resolved else None
    worst = min(resolved, key=lambda b: b.pnl) if resolved else None

    return {
        "total_bets": len(resolved),
        "pending_bets": len(pending),
        "pending_exposure": round(sum(b.stake for b in pending), 2),
        "wins": len(wins),
        "losses": len(losses),
        "pushes": len(pushes),
        "win_rate": win_rate,
        "total_staked": round(total_staked, 2),
        "total_pnl": round(total_pnl, 2),
        "total_won": round(total_won, 2),
        "total_lost": round(total_lost, 2),
        "roi": roi,
        "avg_odds": round(sum(b.odds for b in resolved) / len(resolved)) if resolved else 0,
        "avg_stake": round(total_staked / len(resolved), 2) if resolved else 0,
        "best_bet": (
            {
                "selection": best.selection,
                "game": best.game,
                "pnl": round(best.pnl, 2),
                "odds": best.odds,
            }
            if best
            else None
        ),
        "worst_bet": (
            {
                "selection": worst.selection,
                "game": worst.game,
                "pnl": round(worst.pnl, 2),
                "odds": worst.odds,
            }
            if worst
            else None
        ),
        "by_sport": {
            sport: {
                "record": f"{s['wins']}-{s['losses']}-{s['pushes']}",
                "pnl": round(s["pnl"], 2),
                "roi": round(s["pnl"] / s["staked"] * 100, 2) if s["staked"] > 0 else 0,
            }
            for sport, s in by_sport.items()
        },
        "by_type": {
            btype: {
                "record": f"{t['wins']}-{t['losses']}",
                "pnl": round(t["pnl"], 2),
            }
            for btype, t in by_type.items()
        },
    }
