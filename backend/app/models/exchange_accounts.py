"""Exchange account credentials model (Binance, Kraken, etc.)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped

RUNTIME_ANNOTATION_TYPES = (datetime,)


class ExchangeAccount(TenantScoped, table=True):
    """Encrypted API credentials for a crypto exchange."""

    __tablename__ = "exchange_accounts"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "exchange", name="uq_exchange_accounts_org_exchange"
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    exchange: str = Field(index=True)  # "binance", "kraken", etc.
    label: str = ""
    api_key_encrypted: str = ""
    api_secret_encrypted: str = ""
    is_active: bool = Field(default=True, index=True)
    last_connected_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
