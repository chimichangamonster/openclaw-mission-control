"""Agent-proposed crypto trades awaiting human approval."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field

from app.core.time import utcnow
from app.models.base import QueryModel

RUNTIME_ANNOTATION_TYPES = (datetime,)


class CryptoTradeProposal(QueryModel, table=True):
    """A proposed crypto spot trade that requires human approval before execution."""

    __tablename__ = "crypto_trade_proposals"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    board_id: UUID = Field(foreign_key="boards.id", index=True)
    agent_id: UUID | None = Field(default=None, foreign_key="agents.id", index=True)
    approval_id: UUID | None = Field(default=None, foreign_key="approvals.id", index=True)
    exchange_account_id: UUID = Field(foreign_key="exchange_accounts.id", index=True)

    # Trade params
    exchange: str = "binance"  # for display
    symbol: str = ""  # e.g., "BTCUSDT"
    side: str = ""  # BUY or SELL
    order_type: str = "LIMIT"  # LIMIT, MARKET, STOP_LOSS_LIMIT, TAKE_PROFIT_LIMIT
    quantity: float = 0.0  # amount of base asset
    price: float | None = None  # limit price (null for market orders)
    stop_price: float | None = None  # for stop-loss / take-profit
    quote_amount: float | None = None  # spend this much quote asset (for market buys)
    time_in_force: str = "GTC"  # GTC, IOC, FOK

    # Agent reasoning
    reasoning: str = ""
    confidence: float = 0.0  # 0-100
    strategy: str = ""  # "swing", "momentum", "dip_buy", "take_profit", etc.

    # Technical analysis snapshot
    entry_signal: str = ""  # brief description of signal
    target_price: float | None = None  # take-profit target
    stop_loss_price: float | None = None  # stop-loss level

    # Lifecycle
    status: str = Field(default="pending", index=True)
    # pending | approved | rejected | executed | failed | cancelled
    execution_error: str | None = None
    exchange_order_id: str | None = None
    filled_price: float | None = None
    filled_quantity: float | None = None
    executed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
