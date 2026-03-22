"""Per-org configuration data — cost codes, rate tables, equipment, service catalogs.

Generic key-value store scoped to organization + category. Skills query this
at runtime to get org-specific parameters instead of hardcoded values.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped


class OrgConfigData(TenantScoped, table=True):
    """Per-org configuration item (cost code, rate, role, equipment, etc.)."""

    __tablename__ = "org_config_data"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint("organization_id", "category", "key", name="uq_org_config_cat_key"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    category: str = Field(index=True)  # cost_codes, crew_roles, equipment, service_catalog, etc.
    key: str  # unique within category+org: "labourer", "CC-100", "40yd_bin"
    label: str  # human display: "General Labourer", "40 Yard Bin"
    value_json: str = Field(default="{}")  # flexible payload
    sort_order: int = 0
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def value(self) -> dict:
        return json.loads(self.value_json)


class OrgOnboardingStep(TenantScoped, table=True):
    """Onboarding checklist step for an organization."""

    __tablename__ = "org_onboarding_steps"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    template_id: str  # "construction", "staffing", etc.
    step_key: str  # "add_cost_codes", "add_first_worker"
    label: str
    description: Optional[str] = None
    sort_order: int = 0
    completed: bool = False
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)
