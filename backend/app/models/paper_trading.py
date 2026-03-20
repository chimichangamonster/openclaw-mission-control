"""Paper trading models — portfolios, positions, and trades."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped

RUNTIME_ANNOTATION_TYPES = (datetime,)


class PaperPortfolio(TenantScoped, table=True):
    """A paper trading portfolio with a starting balance."""

    __tablename__ = "paper_portfolios"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    name: str = "Default Portfolio"
    starting_balance: float = 10000.0
    cash_balance: float = 10000.0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class PaperPosition(TenantScoped, table=True):
    """An open or closed position in a paper portfolio."""

    __tablename__ = "paper_positions"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    portfolio_id: UUID = Field(foreign_key="paper_portfolios.id", index=True)
    symbol: str = Field(index=True)
    asset_type: str = "stock"  # stock, crypto, prediction
    side: str = "long"  # long, short
    quantity: float = 0.0
    entry_price: float = 0.0
    current_price: Optional[float] = None
    entry_date: datetime = Field(default_factory=utcnow)
    exit_date: Optional[datetime] = None
    exit_price: Optional[float] = None
    status: str = "open"  # open, closed
    pnl_realized: float = 0.0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class PaperTrade(TenantScoped, table=True):
    """A single trade execution in a paper portfolio."""

    __tablename__ = "paper_trades"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    portfolio_id: UUID = Field(foreign_key="paper_portfolios.id", index=True)
    position_id: Optional[UUID] = Field(default=None, foreign_key="paper_positions.id")
    trade_type: str = "buy"  # buy, sell
    symbol: str = ""
    asset_type: str = "stock"  # stock, crypto, prediction
    quantity: float = 0.0
    price: float = 0.0
    total: float = 0.0
    fees: float = 0.0
    executed_at: datetime = Field(default_factory=utcnow)
    proposed_by: str = ""  # agent name
    approval_status: str = "auto"  # pending, approved, rejected, auto
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)
