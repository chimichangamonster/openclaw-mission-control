"""Agent-proposed Polymarket trades awaiting human approval."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field

from app.core.time import utcnow
from app.models.base import QueryModel

RUNTIME_ANNOTATION_TYPES = (datetime,)


class TradeProposal(QueryModel, table=True):
    """A proposed Polymarket trade that requires human approval before execution."""

    __tablename__ = "trade_proposals"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    board_id: UUID = Field(foreign_key="boards.id", index=True)
    agent_id: UUID | None = Field(default=None, foreign_key="agents.id", index=True)
    approval_id: UUID | None = Field(default=None, foreign_key="approvals.id", index=True)

    # Market snapshot (captured at proposal time)
    condition_id: str = Field(index=True)
    token_id: str = ""
    market_slug: str = ""
    market_question: str = ""
    outcome_label: str = ""

    # Trade parameters
    side: str = ""  # BUY or SELL
    size_usdc: float = 0.0
    price: float = 0.0
    order_type: str = "GTC"  # GTC, GTD, FOK, FAK

    # Agent reasoning
    reasoning: str = ""
    confidence: float = 0.0  # 0-100

    # Lifecycle
    status: str = Field(default="pending", index=True)
    # pending | approved | rejected | executed | failed | cancelled
    execution_error: str | None = None
    polymarket_order_id: str | None = None
    executed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
