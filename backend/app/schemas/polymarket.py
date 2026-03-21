"""Schemas for Polymarket wallet, trading, and market endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel import SQLModel

from app.schemas.common import NonEmptyStr

RUNTIME_ANNOTATION_TYPES = (datetime, UUID, NonEmptyStr)


# --- Wallet ---


class PolymarketWalletCreate(SQLModel):
    """Payload for connecting a Polymarket wallet."""

    private_key: NonEmptyStr
    label: str = "Main Trading Wallet"


class PolymarketWalletRead(SQLModel):
    """Serialized wallet (no secrets exposed)."""

    id: UUID
    organization_id: UUID
    label: str
    wallet_address: str
    is_active: bool
    api_credentials_derived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# --- Risk Config ---


class PolymarketRiskConfigRead(SQLModel):
    """Serialized risk configuration."""

    id: UUID
    organization_id: UUID
    max_trade_size_usdc: float
    daily_loss_limit_usdc: float | None = None
    weekly_loss_limit_usdc: float | None = None
    max_open_positions: int | None = None
    market_whitelist: list[str] | None = None
    market_blacklist: list[str] | None = None
    require_approval: bool
    auto_execute_max_size_usdc: float = 50.0
    auto_execute_min_confidence: float = 75.0
    created_at: datetime
    updated_at: datetime


class PolymarketRiskConfigUpdate(SQLModel):
    """Payload for updating risk configuration."""

    max_trade_size_usdc: float | None = None
    daily_loss_limit_usdc: float | None = None
    weekly_loss_limit_usdc: float | None = None
    max_open_positions: int | None = None
    market_whitelist: list[str] | None = None
    market_blacklist: list[str] | None = None
    require_approval: bool | None = None
    auto_execute_max_size_usdc: float | None = None
    auto_execute_min_confidence: float | None = None


# --- Markets ---


class MarketSearchResult(SQLModel):
    """Condensed market info for search/browse."""

    condition_id: str
    question: str
    slug: str = ""
    outcomes: list[str] = []
    end_date: str | None = None
    volume: float = 0.0
    liquidity: float = 0.0
    yes_price: float | None = None
    no_price: float | None = None
    active: bool = True


class MarketDetailRead(MarketSearchResult):
    """Extended market detail with token IDs."""

    description: str = ""
    tokens: list[dict[str, str]] = []  # [{"token_id": "...", "outcome": "Yes", "price": "0.65"}]


# --- Trade Proposals ---


class TradeProposalCreate(SQLModel):
    """Payload for an agent to propose a trade."""

    condition_id: NonEmptyStr
    token_id: NonEmptyStr
    side: NonEmptyStr  # BUY or SELL
    size_usdc: float
    price: float
    order_type: str = "GTC"
    reasoning: NonEmptyStr
    confidence: float = 50.0


class TradeProposalRead(SQLModel):
    """Serialized trade proposal."""

    id: UUID
    organization_id: UUID
    board_id: UUID
    agent_id: UUID | None = None
    approval_id: UUID | None = None
    condition_id: str
    token_id: str
    market_slug: str
    market_question: str
    outcome_label: str
    side: str
    size_usdc: float
    price: float
    order_type: str
    reasoning: str
    confidence: float
    status: str
    execution_error: str | None = None
    polymarket_order_id: str | None = None
    executed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# --- Positions ---


class PositionRead(SQLModel):
    """Serialized position with P&L."""

    id: UUID
    organization_id: UUID
    condition_id: str
    token_id: str
    market_slug: str
    market_question: str
    outcome_label: str
    size: float
    avg_price: float
    current_price: float | None = None
    unrealized_pnl: float | None = None
    realized_pnl: float
    last_synced_at: datetime | None = None
    created_at: datetime


# --- Trade History ---


class TradeHistoryRead(SQLModel):
    """Serialized executed trade record."""

    id: UUID
    organization_id: UUID
    trade_proposal_id: UUID | None = None
    condition_id: str
    token_id: str
    market_slug: str
    market_question: str
    outcome_label: str
    side: str
    size_usdc: float
    price: float
    filled_price: float | None = None
    polymarket_order_id: str | None = None
    status: str
    executed_at: datetime
    created_at: datetime
