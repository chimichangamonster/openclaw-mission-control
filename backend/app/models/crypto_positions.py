"""Tracked crypto positions from exchange accounts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped

RUNTIME_ANNOTATION_TYPES = (datetime,)


class CryptoPosition(TenantScoped, table=True):
    """A crypto asset position synced from an exchange account."""

    __tablename__ = "crypto_positions"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    exchange_account_id: UUID = Field(foreign_key="exchange_accounts.id", index=True)
    symbol: str = Field(index=True)  # e.g., "BTC", "ETH"
    free: float = 0.0  # available balance
    locked: float = 0.0  # in open orders
    avg_entry_price: float | None = None
    current_price: float | None = None
    unrealized_pnl: float | None = None
    last_synced_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
