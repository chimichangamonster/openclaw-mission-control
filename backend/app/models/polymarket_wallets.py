"""Polymarket wallet credentials model."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped

RUNTIME_ANNOTATION_TYPES = (datetime,)


class PolymarketWallet(TenantScoped, table=True):
    """Encrypted Polymarket wallet and API credentials for an organization."""

    __tablename__ = "polymarket_wallets"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_polymarket_wallets_org"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    label: str = ""
    wallet_address: str = ""
    private_key_encrypted: str = ""
    api_key_encrypted: str = ""
    api_secret_encrypted: str = ""
    api_passphrase_encrypted: str = ""
    api_credentials_derived_at: datetime | None = None
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
