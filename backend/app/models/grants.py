"""Grant applications tracker — multi-program lifecycle (item 107 v2 Phase 1).

Sibling substrate to ``app.models.regulatory``. Tracks grant/subsidy
applications through the full lifecycle:

    plan → draft → submit → review → award/decline → milestones (draws) → reports → close

Tree shape (per organization):

    Organization
    └── Grant                      (program metadata, money, contacts)
        ├── GrantDrawSchedule      (milestone burn-down: target $ + drawn $ per milestone)
        ├── GrantReportingDeadline (interim/final reports + audits + site visits)
        └── GrantPrerequisiteTask  (M:M to RegulatoryTask — what must be done before submit)

Isolation contract (mirrors regulatory.py):
- Grant is TenantScoped — carries ``organization_id`` directly.
- GrantDrawSchedule, GrantReportingDeadline trace via FK chain (Grant→org).
- GrantPrerequisiteTask is the M2M silent-leak surface — model permits a
  grant in org A linking to a regulatory task in org B. The CREATE
  endpoint MUST verify same-org before insert. Mirrors RegulatoryTaskTag's
  contract; ``test_grants.py`` enforces the post-condition.

Determinism posture per ``feedback_determinism_first_for_high_liability.md``:
zero LLM in path. All amounts, dates, statuses are operator-entered SQL.
Audit trail via created_at/updated_at; mutations are operator+ role.

Trigger to advance Phase 2 (frontend) is real Magnetik usage of Phase 1
backend — grants seeded with the v2.1 funding architecture (ERA, AI
Voucher, Micro Voucher, NRC IRAP planned, Clean Resources planned).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Column, Index, Numeric, Text
from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped

RUNTIME_ANNOTATION_TYPES = (date, datetime, Decimal)


# ---------------------------------------------------------------------------
# Grant — direct ownership (TenantScoped, carries organization_id)
# ---------------------------------------------------------------------------


class Grant(TenantScoped, table=True):
    """A single grant application + award lifecycle.

    application_status ∈ "planned" | "drafting" | "submitted" | "under_review"
                       | "awarded" | "declined" | "withdrawn" | "completed"

    "planned" is the pre-drafting state — scope known, application not yet
    started. Useful for the v2.1 architecture's "Future; activate after
    ERA shortlist" entries (NRC IRAP Clean Tech, AI Clean Resources).
    """

    __tablename__ = "grants"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (Index("ix_grants_org", "organization_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)

    granting_body: str  # "Emissions Reduction Alberta" | "Alberta Innovates" | ...
    program_name: str  # "Industrial Transformation Challenge 2026-27"
    application_template_slug: str | None = None
    # "era-industrial-transformation" | "ai-voucher" | "ai-micro-voucher" | ...

    application_status: str = Field(default="planned", index=True)

    submitted_at: date | None = None
    decision_at: date | None = None
    awarded_amount: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(14, 2), nullable=True)
    )
    matched_funding_amount: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(14, 2), nullable=True)
    )
    total_project_value: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(14, 2), nullable=True)
    )
    currency: str = Field(default="CAD")

    project_start_date: date | None = None
    project_end_date: date | None = None

    incorporation_required_entity: str | None = None
    # e.g. "Magnetik Solutions Inc." — surfaces eligibility prerequisites
    cash_coinvestment_required_pct: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(5, 2), nullable=True)
    )
    # e.g. 25.00 (percent) — Alberta Innovates Voucher hard requirement
    cash_coinvestment_source: str | None = None
    # e.g. "Steve's $300K airport partner cash"

    contact_person: str | None = None
    contact_email: str | None = None
    owner_user_id: UUID | None = Field(default=None, foreign_key="users.id")

    program_url: str | None = None
    # Public landing page for the granting program — operator paste-target
    # for emails, RFPs, partner pitches. Item 118 sub-C, 2026-05-06.

    notes_md: str | None = Field(default=None, sa_column=Column(Text, nullable=True))

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# GrantDrawSchedule — indirect (Grant→org)
# ---------------------------------------------------------------------------


class GrantDrawSchedule(TenantScoped, table=True):
    """Milestone burn-down row: one row per draw target.

    status ∈ "pending" | "submitted" | "approved" | "received"
           | "clawed_back" | "skipped"

    The burn chart on the detail drawer aggregates target_amount vs
    drawn_amount across all rows for a grant.
    """

    __tablename__ = "grant_draw_schedules"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (Index("ix_grant_draws_grant", "grant_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    grant_id: UUID = Field(foreign_key="grants.id", index=True)

    milestone_label: str  # "Project kickoff" | "Equipment commissioning" | ...
    target_date: date | None = None
    target_amount: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))

    drawn_at: date | None = None
    drawn_amount: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(14, 2), nullable=True)
    )

    status: str = Field(default="pending", index=True)
    sort_order: int = Field(default=0)
    notes_md: str | None = Field(default=None, sa_column=Column(Text, nullable=True))

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# GrantReportingDeadline — indirect (Grant→org)
# ---------------------------------------------------------------------------


class GrantReportingDeadline(TenantScoped, table=True):
    """Reporting cadence row: one row per upcoming report or audit.

    deadline_type ∈ "interim_report" | "final_report" | "audit"
                  | "site_visit" | "other"
    status        ∈ "upcoming" | "submitted" | "complete" | "missed" | "waived"

    Drives the "next deadline countdown" widget + agent-token
    /agent/grants/upcoming-deadlines endpoint. Missed deadlines are
    high-liability — claw-back risk per the determinism-first memory.
    """

    __tablename__ = "grant_reporting_deadlines"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        Index("ix_grant_deadlines_grant", "grant_id"),
        Index("ix_grant_deadlines_date", "deadline_date"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    grant_id: UUID = Field(foreign_key="grants.id", index=True)

    deadline_date: date = Field(index=True)
    deadline_type: str = Field(default="interim_report")
    description: str | None = Field(default=None, sa_column=Column(Text, nullable=True))

    status: str = Field(default="upcoming", index=True)
    submitted_at: date | None = None
    submitted_artifact_url: str | None = None

    sort_order: int = Field(default=0)
    notes_md: str | None = Field(default=None, sa_column=Column(Text, nullable=True))

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# GrantPrerequisiteTask — M2M to RegulatoryTask (silent-leak surface)
# ---------------------------------------------------------------------------


class GrantPrerequisiteTask(TenantScoped, table=True):
    """M:M link between Grant and RegulatoryTask.

    THE silent-leak surface (mirrors RegulatoryTaskTag's contract). The
    model permits joining a grant in org A with a regulatory task in
    org B. The CREATE endpoint MUST verify both endpoints belong to the
    same org before insert.

    Composite primary key prevents duplicate links and removes the need
    for a synthetic id column. ``label_override`` lets operators rename
    the task for grant-display purposes without touching the underlying
    regulatory task.
    """

    __tablename__ = "grant_prerequisite_tasks"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        Index("ix_grant_prereqs_grant", "grant_id"),
        Index("ix_grant_prereqs_task", "regulatory_task_id"),
    )

    grant_id: UUID = Field(foreign_key="grants.id", primary_key=True)
    regulatory_task_id: UUID = Field(
        foreign_key="regulatory_tasks.id", primary_key=True
    )

    label_override: str | None = None
    is_critical: bool = Field(default=False)

    created_at: datetime = Field(default_factory=utcnow)
