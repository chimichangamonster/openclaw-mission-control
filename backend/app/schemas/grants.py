"""Schemas for the grants tracker (item 107 v2 Phase 1).

Mirrors the regulatory.py schema split: Read / Create / Update per entity,
plus a GrantReadDetail with nested draws + deadlines + prerequisites for
the detail-drawer endpoint.

Pydantic v1 (SQLModel BaseModel inheritance), matching project convention.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlmodel import SQLModel

from app.schemas.common import NonEmptyStr

RUNTIME_ANNOTATION_TYPES = (date, datetime, Decimal, UUID, NonEmptyStr)


# ---------------------------------------------------------------------------
# Grant
# ---------------------------------------------------------------------------


class GrantRead(SQLModel):
    id: UUID
    organization_id: UUID
    granting_body: str
    program_name: str
    application_template_slug: str | None = None
    application_status: str
    submitted_at: date | None = None
    decision_at: date | None = None
    awarded_amount: Decimal | None = None
    matched_funding_amount: Decimal | None = None
    total_project_value: Decimal | None = None
    currency: str = "CAD"
    project_start_date: date | None = None
    project_end_date: date | None = None
    incorporation_required_entity: str | None = None
    cash_coinvestment_required_pct: Decimal | None = None
    cash_coinvestment_source: str | None = None
    contact_person: str | None = None
    contact_email: str | None = None
    owner_user_id: UUID | None = None
    program_url: str | None = None
    notes_md: str | None = None
    created_at: datetime
    updated_at: datetime


class GrantCreate(SQLModel):
    granting_body: NonEmptyStr
    program_name: NonEmptyStr
    application_template_slug: str | None = None
    application_status: str = "planned"
    submitted_at: date | None = None
    decision_at: date | None = None
    awarded_amount: Decimal | None = None
    matched_funding_amount: Decimal | None = None
    total_project_value: Decimal | None = None
    currency: str = "CAD"
    project_start_date: date | None = None
    project_end_date: date | None = None
    incorporation_required_entity: str | None = None
    cash_coinvestment_required_pct: Decimal | None = None
    cash_coinvestment_source: str | None = None
    contact_person: str | None = None
    contact_email: str | None = None
    owner_user_id: UUID | None = None
    program_url: str | None = None
    notes_md: str | None = None


class GrantUpdate(SQLModel):
    granting_body: str | None = None
    program_name: str | None = None
    application_template_slug: str | None = None
    application_status: str | None = None
    submitted_at: date | None = None
    decision_at: date | None = None
    awarded_amount: Decimal | None = None
    matched_funding_amount: Decimal | None = None
    total_project_value: Decimal | None = None
    currency: str | None = None
    project_start_date: date | None = None
    project_end_date: date | None = None
    incorporation_required_entity: str | None = None
    cash_coinvestment_required_pct: Decimal | None = None
    cash_coinvestment_source: str | None = None
    contact_person: str | None = None
    contact_email: str | None = None
    owner_user_id: UUID | None = None
    program_url: str | None = None
    notes_md: str | None = None


# ---------------------------------------------------------------------------
# Draw schedule
# ---------------------------------------------------------------------------


class GrantDrawRead(SQLModel):
    id: UUID
    grant_id: UUID
    milestone_label: str
    target_date: date | None = None
    target_amount: Decimal
    drawn_at: date | None = None
    drawn_amount: Decimal | None = None
    status: str
    sort_order: int = 0
    notes_md: str | None = None
    created_at: datetime
    updated_at: datetime


class GrantDrawCreate(SQLModel):
    milestone_label: NonEmptyStr
    target_date: date | None = None
    target_amount: Decimal
    drawn_at: date | None = None
    drawn_amount: Decimal | None = None
    status: str = "pending"
    sort_order: int = 0
    notes_md: str | None = None


class GrantDrawUpdate(SQLModel):
    milestone_label: str | None = None
    target_date: date | None = None
    target_amount: Decimal | None = None
    drawn_at: date | None = None
    drawn_amount: Decimal | None = None
    status: str | None = None
    sort_order: int | None = None
    notes_md: str | None = None


# ---------------------------------------------------------------------------
# Reporting deadline
# ---------------------------------------------------------------------------


class GrantDeadlineRead(SQLModel):
    id: UUID
    grant_id: UUID
    deadline_date: date
    deadline_type: str
    description: str | None = None
    status: str
    submitted_at: date | None = None
    submitted_artifact_url: str | None = None
    sort_order: int = 0
    notes_md: str | None = None
    created_at: datetime
    updated_at: datetime


class GrantDeadlineCreate(SQLModel):
    deadline_date: date
    deadline_type: str = "interim_report"
    description: str | None = None
    status: str = "upcoming"
    submitted_at: date | None = None
    submitted_artifact_url: str | None = None
    sort_order: int = 0
    notes_md: str | None = None


class GrantDeadlineUpdate(SQLModel):
    deadline_date: date | None = None
    deadline_type: str | None = None
    description: str | None = None
    status: str | None = None
    submitted_at: date | None = None
    submitted_artifact_url: str | None = None
    sort_order: int | None = None
    notes_md: str | None = None


# ---------------------------------------------------------------------------
# Prerequisite (M2M Grant ↔ RegulatoryTask)
# ---------------------------------------------------------------------------


class GrantPrerequisiteRead(SQLModel):
    grant_id: UUID
    regulatory_task_id: UUID
    label_override: str | None = None
    is_critical: bool = False
    created_at: datetime
    # joined-in fields from RegulatoryTask for display convenience
    task_body: str | None = None
    task_completed: bool | None = None


class GrantPrerequisiteCreate(SQLModel):
    regulatory_task_id: UUID
    label_override: str | None = None
    is_critical: bool = False


class GrantPrerequisiteStatus(SQLModel):
    """Aggregate status for the dashboard widget."""

    total: int
    complete: int
    blocking_critical: int
    percent: float  # 0.0 to 1.0


# ---------------------------------------------------------------------------
# Detail (nested for /grants/{id})
# ---------------------------------------------------------------------------


class GrantReadDetail(GrantRead):
    draws: list[GrantDrawRead] = []
    deadlines: list[GrantDeadlineRead] = []
    prerequisites: list[GrantPrerequisiteRead] = []


# ---------------------------------------------------------------------------
# Agent endpoint shape
# ---------------------------------------------------------------------------


class AgentUpcomingDeadline(SQLModel):
    grant_id: UUID
    grant_program_name: str
    granting_body: str
    deadline_date: date
    deadline_type: str
    description: str | None = None
    days_until: int  # positive = future, negative = past-due
    status: str
