"""Polymarket risk controls per organization."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped

RUNTIME_ANNOTATION_TYPES = (datetime,)


class PolymarketRiskConfig(TenantScoped, table=True):
    """Risk limits and controls for Polymarket trading."""

    __tablename__ = "polymarket_risk_configs"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_polymarket_risk_configs_org"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    max_trade_size_usdc: float = 100.0
    daily_loss_limit_usdc: float | None = None
    weekly_loss_limit_usdc: float | None = None
    max_open_positions: int | None = None
    market_whitelist: list[str] | None = Field(default=None, sa_column=Column(JSON))
    market_blacklist: list[str] | None = Field(default=None, sa_column=Column(JSON))
    require_approval: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
