"""Schemas for the regulatory tracker (item 101 v2 Phase 1b).

Each model maps 1:1 to a table in `app.models.regulatory`. Keep field names
identical so the API layer can `RegulatoryStreamRead.model_validate(stream)`
directly against the SQLModel row without translation.

Read-vs-Create-vs-Update split mirrors the contacts.py pattern:
- Read: full row including id + timestamps + organization_id
- Create: required fields only, server fills id/org/timestamps
- Update: every field optional (partial update)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlmodel import SQLModel

from app.schemas.common import NonEmptyStr

RUNTIME_ANNOTATION_TYPES = (datetime, Decimal, UUID, NonEmptyStr)


# ---------------------------------------------------------------------------
# Stream
# ---------------------------------------------------------------------------


class RegulatoryStreamRead(SQLModel):
    id: UUID
    organization_id: UUID
    slug: str
    name: str
    description: str | None = None
    color_token: str = "navy"
    budget_estimate: Decimal | None = None
    regulator_label: str | None = None
    timeline_label: str | None = None
    sort_order: int = 0
    archived: bool = False
    created_at: datetime
    updated_at: datetime


class RegulatoryStreamCreate(SQLModel):
    slug: NonEmptyStr
    name: NonEmptyStr
    description: str | None = None
    color_token: str = "navy"
    budget_estimate: Decimal | None = None
    regulator_label: str | None = None
    timeline_label: str | None = None
    sort_order: int = 0


class RegulatoryStreamUpdate(SQLModel):
    name: str | None = None
    description: str | None = None
    color_token: str | None = None
    budget_estimate: Decimal | None = None
    regulator_label: str | None = None
    timeline_label: str | None = None
    sort_order: int | None = None
    archived: bool | None = None


# ---------------------------------------------------------------------------
# Country
# ---------------------------------------------------------------------------


class RegulatoryCountryRead(SQLModel):
    id: UUID
    organization_id: UUID
    code: str
    name: str
    status: str = "pipeline"
    display_label: str
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime


class RegulatoryCountryCreate(SQLModel):
    code: NonEmptyStr  # ISO-2
    name: NonEmptyStr
    status: str = "pipeline"  # "active" | "pipeline" | "archived"
    display_label: NonEmptyStr
    sort_order: int = 0


class RegulatoryCountryUpdate(SQLModel):
    name: str | None = None
    status: str | None = None
    display_label: str | None = None
    sort_order: int | None = None


# ---------------------------------------------------------------------------
# Tag
# ---------------------------------------------------------------------------


class RegulatoryTagRead(SQLModel):
    id: UUID
    organization_id: UUID
    slug: str
    label: str
    color_token: str = "corp"
    kind: str = "regulatory"
    created_at: datetime


class RegulatoryTagCreate(SQLModel):
    slug: NonEmptyStr
    label: NonEmptyStr
    color_token: str = "corp"
    kind: str = "regulatory"
    # kind ∈ "regulatory" | "insurance" | "corporate" | "grant" | "priority" | "legal" | "financial"


class RegulatoryTagUpdate(SQLModel):
    label: str | None = None
    color_token: str | None = None
    kind: str | None = None


# ---------------------------------------------------------------------------
# Phase
# ---------------------------------------------------------------------------


class RegulatoryPhaseRead(SQLModel):
    id: UUID
    stream_id: UUID
    country_id: UUID
    name: str
    badge_kind: str = "now"
    timing_label: str | None = None
    sort_order: int = 0
    default_open: bool = False
    created_at: datetime
    updated_at: datetime


class RegulatoryPhaseCreate(SQLModel):
    stream_id: UUID
    country_id: UUID
    name: NonEmptyStr
    badge_kind: str = "now"
    # badge_kind ∈ "now" | "pre" | "arrive" | "post" | "concurrent" | "corp" | "insurance"
    timing_label: str | None = None
    sort_order: int = 0
    default_open: bool = False


class RegulatoryPhaseUpdate(SQLModel):
    name: str | None = None
    badge_kind: str | None = None
    timing_label: str | None = None
    sort_order: int | None = None
    default_open: bool | None = None


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------


class RegulatoryTaskRead(SQLModel):
    id: UUID
    phase_id: UUID
    body: str
    note: str | None = None
    completed: bool = False
    completed_at: datetime | None = None
    completed_by_user_id: UUID | None = None
    assignee_user_id: UUID | None = None
    due_date: datetime | None = None
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime


class RegulatoryTaskCreate(SQLModel):
    phase_id: UUID
    body: NonEmptyStr
    note: str | None = None
    assignee_user_id: UUID | None = None
    due_date: datetime | None = None
    sort_order: int = 0


class RegulatoryTaskUpdate(SQLModel):
    body: str | None = None
    note: str | None = None
    assignee_user_id: UUID | None = None
    due_date: datetime | None = None
    sort_order: int | None = None


# ---------------------------------------------------------------------------
# TaskNote (threaded notes attached to tasks)
# ---------------------------------------------------------------------------


class RegulatoryTaskNoteRead(SQLModel):
    id: UUID
    task_id: UUID
    body: str
    author_user_id: UUID
    created_at: datetime


class RegulatoryTaskNoteCreate(SQLModel):
    body: NonEmptyStr


# ---------------------------------------------------------------------------
# PriorityNote (banner notes within a phase, e.g. "🚫 BLOCKING ITEM")
# ---------------------------------------------------------------------------


class RegulatoryPriorityNoteRead(SQLModel):
    id: UUID
    phase_id: UUID
    body: str
    severity: str = "info"
    sort_order: int = 0
    created_at: datetime


class RegulatoryPriorityNoteCreate(SQLModel):
    phase_id: UUID
    body: NonEmptyStr
    severity: str = "info"  # "critical" | "info" | "warn" | "navy-note"
    sort_order: int = 0


class RegulatoryPriorityNoteUpdate(SQLModel):
    body: str | None = None
    severity: str | None = None
    sort_order: int | None = None


# ---------------------------------------------------------------------------
# TaskTag (M2M link)
# ---------------------------------------------------------------------------


class RegulatoryTaskTagRead(SQLModel):
    task_id: UUID
    tag_id: UUID
    created_at: datetime


class RegulatoryTaskTagCreate(SQLModel):
    task_id: UUID
    tag_id: UUID
