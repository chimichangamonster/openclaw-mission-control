"""Watchlist model — track tickers from reports for buy-signal monitoring."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped


class WatchlistItem(TenantScoped, table=True):
    """A ticker on the watchlist, sourced from a research report."""

    __tablename__ = "watchlist_items"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    portfolio_id: UUID = Field(foreign_key="paper_portfolios.id", index=True)
    symbol: str = Field(index=True)
    yahoo_ticker: str = ""  # Yahoo Finance ticker (e.g., BDT.TO, BIDU)
    company_name: Optional[str] = None
    exchange: Optional[str] = None  # TSX, NYSE, NASDAQ
    sector: Optional[str] = None
    # Report metadata
    source_report: str = ""  # e.g., "10 Bagger Report - March 15 2026"
    report_rating: Optional[str] = None  # Strong Buy, Buy, Speculative Buy
    expected_low: Optional[float] = None  # Bottom of expected range
    expected_high: Optional[float] = None  # Top of expected range
    # Live data (updated by agent scans)
    current_price: Optional[float] = None
    rsi: Optional[float] = None
    volume_ratio: Optional[float] = None  # Last vol / 20d avg vol
    sentiment: Optional[str] = None  # VERY BULLISH, BULLISH, NEUTRAL, BEARISH, VERY BEARISH
    sentiment_confidence: Optional[int] = None  # 1-10
    # Status
    status: str = "watching"  # watching, alerting, bought, removed
    alert_reason: Optional[str] = None  # e.g., "RSI <30, Volume spike 2.3x"
    notes: Optional[str] = None
    # Timestamps
    price_updated_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
