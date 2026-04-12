"""Budget configuration and daily agent spend tracking."""

from __future__ import annotations

import json
from datetime import date as _date_type
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.core.time import utcnow
from app.models.base import QueryModel


class BudgetConfig(QueryModel, table=True):
    """Per-organization budget configuration."""

    __tablename__ = "budget_configs"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("organization_id", name="uq_budget_configs_org"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    monthly_budget: float = Field(default=25.0)
    alert_thresholds_json: str = Field(default="[50, 80, 95]")
    agent_daily_limits_json: str = Field(default="{}")
    default_agent_daily_limit: float = Field(default=2.0)
    throttle_to_tier1_on_exceed: bool = Field(default=True)
    alerts_enabled: bool = Field(default=True)
    last_alert_month: str = Field(default="")
    last_alert_thresholds_hit_json: str = Field(default="[]")
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def alert_thresholds(self) -> list[int]:
        return json.loads(self.alert_thresholds_json)  # type: ignore[no-any-return]

    @property
    def agent_daily_limits(self) -> dict[str, float]:
        return json.loads(self.agent_daily_limits_json)  # type: ignore[no-any-return]

    @property
    def last_alert_thresholds_hit(self) -> list[int]:
        return json.loads(self.last_alert_thresholds_hit_json)  # type: ignore[no-any-return]


class DailyAgentSpend(QueryModel, table=True):
    """Per-agent daily spend snapshot, scoped to organization."""

    __tablename__ = "daily_agent_spends"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint("organization_id", "agent_name", "date", name="uq_org_agent_date"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    agent_name: str = Field(index=True)
    date: _date_type = Field(index=True)
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    estimated_cost: float = Field(default=0.0)
    model_breakdown_json: str = Field(default="{}")
    session_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=utcnow)

    @property
    def model_breakdown(self) -> dict[str, float]:
        return json.loads(self.model_breakdown_json)  # type: ignore[no-any-return]
