"""Schemas for crypto exchange trading endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel import SQLModel

from app.schemas.common import NonEmptyStr

RUNTIME_ANNOTATION_TYPES = (datetime, UUID, NonEmptyStr)


# --- Exchange Account ---


class ExchangeAccountCreate(SQLModel):
    """Payload for connecting an exchange account."""

    exchange: str = "binance"
    api_key: NonEmptyStr
    api_secret: NonEmptyStr
    label: str = "Binance Trading"


class ExchangeAccountRead(SQLModel):
    """Serialized exchange account (no secrets)."""

    id: UUID
    organization_id: UUID
    exchange: str
    label: str
    is_active: bool
    last_connected_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


# --- Crypto Trade Proposal ---


class CryptoTradeProposalCreate(SQLModel):
    """Payload for an agent to propose a crypto trade."""

    symbol: NonEmptyStr  # e.g., "BTCUSDT"
    side: NonEmptyStr  # BUY or SELL
    order_type: str = "LIMIT"
    quantity: float | None = None
    price: float | None = None
    stop_price: float | None = None
    quote_amount: float | None = None  # for market buys: spend X USDT
    time_in_force: str = "GTC"
    reasoning: NonEmptyStr
    confidence: float = 50.0
    strategy: str = ""
    entry_signal: str = ""
    target_price: float | None = None
    stop_loss_price: float | None = None


class CryptoTradeProposalRead(SQLModel):
    """Serialized crypto trade proposal."""

    id: UUID
    organization_id: UUID
    board_id: UUID
    agent_id: UUID | None = None
    approval_id: UUID | None = None
    exchange: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float | None = None
    stop_price: float | None = None
    quote_amount: float | None = None
    time_in_force: str
    reasoning: str
    confidence: float
    strategy: str
    entry_signal: str
    target_price: float | None = None
    stop_loss_price: float | None = None
    status: str
    execution_error: str | None = None
    exchange_order_id: str | None = None
    filled_price: float | None = None
    filled_quantity: float | None = None
    executed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# --- Position ---


class CryptoPositionRead(SQLModel):
    """Serialized crypto position."""

    id: UUID
    symbol: str
    free: float
    locked: float
    avg_entry_price: float | None = None
    current_price: float | None = None
    unrealized_pnl: float | None = None
    last_synced_at: datetime | None = None
