"""Executed Polymarket trade log."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped

RUNTIME_ANNOTATION_TYPES = (datetime,)


class TradeHistory(TenantScoped, table=True):
    """Record of an executed Polymarket trade."""

    __tablename__ = "trade_history"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    trade_proposal_id: UUID | None = Field(
        default=None, foreign_key="trade_proposals.id", index=True
    )
    condition_id: str = ""
    token_id: str = ""
    market_slug: str = ""
    market_question: str = ""
    outcome_label: str = ""
    side: str = ""
    size_usdc: float = 0.0
    price: float = 0.0
    filled_price: float | None = None
    polymarket_order_id: str | None = None
    status: str = ""  # filled, partially_filled, cancelled
    executed_at: datetime = Field(default_factory=utcnow)
    created_at: datetime = Field(default_factory=utcnow)
