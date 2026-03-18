"""Synced Polymarket positions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped

RUNTIME_ANNOTATION_TYPES = (datetime,)


class PolymarketPosition(TenantScoped, table=True):
    """A position held in a Polymarket outcome token."""

    __tablename__ = "polymarket_positions"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    condition_id: str = Field(index=True)
    token_id: str = ""
    market_slug: str = ""
    market_question: str = ""
    outcome_label: str = ""
    size: float = 0.0
    avg_price: float = 0.0
    current_price: float | None = None
    unrealized_pnl: float | None = None
    realized_pnl: float = 0.0
    last_synced_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
