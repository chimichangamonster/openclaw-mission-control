"""Watchlist API — CRUD for tracked tickers from research reports."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import (  # type: ignore[attr-defined]
    ORG_RATE_LIMIT_DEP,
    PORTFOLIO_DEP,
    get_session,
    require_feature,
    require_org_from_actor,
)
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.paper_trading import PaperPortfolio
from app.models.watchlist import WatchlistItem
from app.services.organizations import OrganizationContext

logger = get_logger(__name__)
router = APIRouter(
    prefix="/watchlist",
    tags=["watchlist"],
    dependencies=[Depends(require_feature("watchlist")), ORG_RATE_LIMIT_DEP],
)


def _item_to_dict(item: WatchlistItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "portfolio_id": str(item.portfolio_id),
        "symbol": item.symbol,
        "yahoo_ticker": item.yahoo_ticker,
        "company_name": item.company_name,
        "exchange": item.exchange,
        "sector": item.sector,
        "source_report": item.source_report,
        "report_rating": item.report_rating,
        "expected_low": item.expected_low,
        "expected_high": item.expected_high,
        "current_price": item.current_price,
        "rsi": item.rsi,
        "volume_ratio": item.volume_ratio,
        "sentiment": item.sentiment,
        "sentiment_confidence": item.sentiment_confidence,
        "status": item.status,
        "alert_reason": item.alert_reason,
        "notes": item.notes,
        "price_updated_at": item.price_updated_at.isoformat() if item.price_updated_at else None,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


@router.get("/portfolios/{portfolio_id}/items")
async def list_watchlist(
    session: AsyncSession = Depends(get_session),
    portfolio: PaperPortfolio = PORTFOLIO_DEP,
    status_filter: str = Query("watching", alias="status"),
) -> list[dict[str, Any]]:
    stmt = select(WatchlistItem).where(
        WatchlistItem.portfolio_id == portfolio.id,  # type: ignore[arg-type]
    )
    if status_filter != "all":
        stmt = stmt.where(WatchlistItem.status == status_filter)  # type: ignore[arg-type]
    stmt = stmt.order_by(WatchlistItem.symbol.asc())  # type: ignore[attr-defined]

    items = (await session.execute(stmt)).scalars().all()
    return [_item_to_dict(i) for i in items]


@router.post("/portfolios/{portfolio_id}/items", status_code=201)
async def add_watchlist_item(
    portfolio_id: UUID,
    session: AsyncSession = Depends(get_session),
    org_ctx: OrganizationContext = Depends(require_org_from_actor),
    symbol: str = "",
    yahoo_ticker: str = "",
    company_name: str | None = None,
    exchange: str | None = None,
    sector: str | None = None,
    source_report: str = "",
    report_rating: str | None = None,
    expected_low: float | None = None,
    expected_high: float | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    # Verify portfolio exists
    portfolio = (
        await session.execute(
            select(PaperPortfolio).where(
                PaperPortfolio.id == portfolio_id,  # type: ignore[arg-type]
                PaperPortfolio.organization_id == org_ctx.organization.id,  # type: ignore[arg-type]
            )
        )
    ).scalar_one_or_none()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    # Check for duplicate
    existing = (
        await session.execute(
            select(WatchlistItem).where(
                WatchlistItem.portfolio_id == portfolio_id,  # type: ignore[arg-type]
                WatchlistItem.symbol == symbol,  # type: ignore[arg-type]
                WatchlistItem.status.in_(["watching", "alerting"]),  # type: ignore[attr-defined]
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"{symbol} is already on the watchlist")

    item = WatchlistItem(
        portfolio_id=portfolio_id,
        symbol=symbol,
        yahoo_ticker=yahoo_ticker,
        company_name=company_name,
        exchange=exchange,
        sector=sector,
        source_report=source_report,
        report_rating=report_rating,
        expected_low=expected_low,
        expected_high=expected_high,
        notes=notes,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return _item_to_dict(item)


@router.patch("/portfolios/{portfolio_id}/items/{item_id}")
async def update_watchlist_item(
    item_id: UUID,
    session: AsyncSession = Depends(get_session),
    portfolio: PaperPortfolio = PORTFOLIO_DEP,
    current_price: float | None = None,
    rsi: float | None = None,
    volume_ratio: float | None = None,
    sentiment: str | None = None,
    sentiment_confidence: int | None = None,
    status: str | None = None,
    alert_reason: str | None = None,
    notes: str | None = None,
    report_rating: str | None = None,
    expected_low: float | None = None,
    expected_high: float | None = None,
) -> dict[str, Any]:
    stmt = select(WatchlistItem).where(
        WatchlistItem.id == item_id,  # type: ignore[arg-type]
        WatchlistItem.portfolio_id == portfolio.id,  # type: ignore[arg-type]
    )
    item = (await session.execute(stmt)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Watchlist item not found")

    if current_price is not None:
        item.current_price = current_price
        item.price_updated_at = utcnow()
    if rsi is not None:
        item.rsi = rsi
    if volume_ratio is not None:
        item.volume_ratio = volume_ratio
    if sentiment is not None:
        item.sentiment = sentiment
    if sentiment_confidence is not None:
        item.sentiment_confidence = sentiment_confidence
    if status is not None:
        item.status = status
    if alert_reason is not None:
        item.alert_reason = alert_reason
    if notes is not None:
        item.notes = notes
    if report_rating is not None:
        item.report_rating = report_rating
    if expected_low is not None:
        item.expected_low = expected_low
    if expected_high is not None:
        item.expected_high = expected_high
    item.updated_at = utcnow()

    await session.commit()
    return _item_to_dict(item)


@router.delete("/portfolios/{portfolio_id}/items/{item_id}", status_code=204)
async def remove_watchlist_item(
    item_id: UUID,
    session: AsyncSession = Depends(get_session),
    portfolio: PaperPortfolio = PORTFOLIO_DEP,
) -> None:
    stmt = select(WatchlistItem).where(
        WatchlistItem.id == item_id,  # type: ignore[arg-type]
        WatchlistItem.portfolio_id == portfolio.id,  # type: ignore[arg-type]
    )
    item = (await session.execute(stmt)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Watchlist item not found")

    await session.delete(item)
    await session.commit()


@router.get("/portfolios/{portfolio_id}/items/summary")
async def watchlist_summary(
    session: AsyncSession = Depends(get_session),
    portfolio: PaperPortfolio = PORTFOLIO_DEP,
) -> dict[str, Any]:
    """Quick summary: counts by status, any active alerts."""
    watching = (
        await session.execute(
            select(func.count()).where(
                WatchlistItem.portfolio_id == portfolio.id,  # type: ignore[arg-type]
                WatchlistItem.status == "watching",  # type: ignore[arg-type]
            )
        )
    ).scalar() or 0

    alerting = (
        await session.execute(
            select(func.count()).where(
                WatchlistItem.portfolio_id == portfolio.id,  # type: ignore[arg-type]
                WatchlistItem.status == "alerting",  # type: ignore[arg-type]
            )
        )
    ).scalar() or 0

    bought = (
        await session.execute(
            select(func.count()).where(
                WatchlistItem.portfolio_id == portfolio.id,  # type: ignore[arg-type]
                WatchlistItem.status == "bought",  # type: ignore[arg-type]
            )
        )
    ).scalar() or 0

    # Get alerting items for quick view
    alert_stmt = (
        select(WatchlistItem)
        .where(
            WatchlistItem.portfolio_id == portfolio.id,  # type: ignore[arg-type]
            WatchlistItem.status == "alerting",  # type: ignore[arg-type]
        )
        .order_by(WatchlistItem.rsi.asc())  # type: ignore[union-attr]
    )
    alerts = (await session.execute(alert_stmt)).scalars().all()

    return {
        "watching": watching,
        "alerting": alerting,
        "bought": bought,
        "total": watching + alerting + bought,
        "alerts": [_item_to_dict(a) for a in alerts],
    }


@router.post("/portfolios/{portfolio_id}/items/bulk", status_code=201)
async def bulk_add_watchlist(
    portfolio_id: UUID,
    items: list[dict[str, Any]],
    session: AsyncSession = Depends(get_session),
    org_ctx: OrganizationContext = Depends(require_org_from_actor),
) -> dict[str, Any]:
    """Bulk add watchlist items from a report scan."""
    # Verify portfolio
    portfolio = (
        await session.execute(
            select(PaperPortfolio).where(
                PaperPortfolio.id == portfolio_id,  # type: ignore[arg-type]
                PaperPortfolio.organization_id == org_ctx.organization.id,  # type: ignore[arg-type]
            )
        )
    ).scalar_one_or_none()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    added = 0
    skipped = 0
    for data in items:
        symbol = data.get("symbol", "")
        # Skip duplicates
        existing = (
            await session.execute(
                select(WatchlistItem).where(
                    WatchlistItem.portfolio_id == portfolio_id,  # type: ignore[arg-type]
                    WatchlistItem.symbol == symbol,
                    WatchlistItem.status.in_(["watching", "alerting"]),  # type: ignore[attr-defined]
                )
            )
        ).scalar_one_or_none()
        if existing:
            skipped += 1
            continue

        item = WatchlistItem(
            portfolio_id=portfolio_id,
            symbol=symbol,
            yahoo_ticker=data.get("yahoo_ticker", ""),
            company_name=data.get("company_name"),
            exchange=data.get("exchange"),
            sector=data.get("sector"),
            source_report=data.get("source_report", ""),
            report_rating=data.get("report_rating"),
            expected_low=data.get("expected_low"),
            expected_high=data.get("expected_high"),
            notes=data.get("notes"),
        )
        session.add(item)
        added += 1

    await session.commit()
    return {"added": added, "skipped": skipped}
