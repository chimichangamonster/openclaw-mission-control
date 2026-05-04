"""Regulatory tracker — multi-stream, multi-country approval workflow.

Item 101 v2 Phase 1a. Mirrors the structure of the standalone
``magnetik-solutions/public/internal/equipment-tracker.html`` so Henry's
working surface on the platform matches the stakeholder-facing tracker
on magnetiksolutions.com (which will SSR-fetch the platform's public
snapshot endpoint).

Tree shape (per organization):

    Organization
    ├── RegulatoryStream  (Corporate, Eboiler, MagnetGas, ...)
    ├── RegulatoryCountry (CA active; IN + KE schemas reserved)
    └── RegulatoryTag     (regulatory bodies, priorities, insurance, grant flags)

    RegulatoryPhase   ─→ FK → Stream + Country
    └── RegulatoryTask  ─→ FK → Phase
        ├── RegulatoryTaskNote   (threaded notes, M:1 author)
        └── RegulatoryTaskTag    (M:M to RegulatoryTag)
    └── RegulatoryPriorityNote   (banner notes per phase, e.g. "BLOCKING ITEM")

Isolation contract (locked by ``tests/test_regulatory_isolation.py``):
- TenantScoped tables (Stream, Country, Tag) carry ``organization_id`` directly.
- Phase / Task / TaskNote / PriorityNote / TaskTag have NO direct
  ``organization_id`` — isolation traces via FK chain (Phase→Stream→org).
  Endpoint code MUST scope queries through the chain. The tests assert
  this contract holds.
- M2M cross-org mixing (TaskTag) is the silent-leak surface. Endpoint
  code MUST validate (task.org == tag.org) before insert. The model
  layer permits the bad write — only API validation prevents it.
- Composite uniqueness: (organization_id, slug) on Stream and Tag means
  two orgs can both have a slug "abca" without collision.

See ``docs/business/magnetik-platform-evolution.md`` for the long-arc
roadmap (Phase 1 → 2 → 3) this substrate underpins.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Column,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped

RUNTIME_ANNOTATION_TYPES = (datetime, Decimal)


# ---------------------------------------------------------------------------
# Direct-ownership tables (TenantScoped, carry organization_id)
# ---------------------------------------------------------------------------


class RegulatoryStream(TenantScoped, table=True):
    """Top-level workflow lane (Corporate / Eboiler / MagnetGas / future).

    Streams group phases and tasks. Each org defines its own streams; slug
    collisions across orgs are allowed (every org may have its own
    "corporate" stream).
    """

    __tablename__ = "regulatory_streams"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_reg_stream_org_slug"),
        Index("ix_reg_streams_org", "organization_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)

    slug: str = Field(index=True)  # "corporate" | "eboiler" | "magnetgas" | ...
    name: str
    description: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    color_token: str = Field(default="navy")  # "navy" | "green" | "orange" | "purple"
    budget_estimate: Decimal | None = Field(
        default=None, sa_column=Column(Numeric(14, 2), nullable=True)
    )
    regulator_label: str | None = None
    timeline_label: str | None = None
    sort_order: int = Field(default=0)
    archived: bool = Field(default=False)

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class RegulatoryCountry(TenantScoped, table=True):
    """Country panel within an org's regulatory tracker.

    Canada is the active panel for v2 ship. India + Kenya schemas reserved
    (status="pipeline") so the UI shows them as disabled tabs without
    needing schema changes when seeded later.
    """

    __tablename__ = "regulatory_countries"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_reg_country_org_code"),
        Index("ix_reg_countries_org", "organization_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)

    code: str = Field(index=True)  # ISO-2: "CA" | "IN" | "KE" | ...
    name: str
    status: str = Field(default="pipeline")  # "active" | "pipeline" | "archived"
    display_label: str  # e.g. "Canada (Alberta Pilot)"
    sort_order: int = Field(default=0)

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class RegulatoryTag(TenantScoped, table=True):
    """Reusable label applied to tasks (regulatory body, priority, insurance, grant).

    Slug collisions across orgs are intentional — both Magnetik and a future
    clean-tech org may have an "abca" tag. Composite (org_id, slug) unique
    constraint enforces uniqueness within an org.
    """

    __tablename__ = "regulatory_tags"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_reg_tag_org_slug"),
        Index("ix_reg_tags_org", "organization_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)

    slug: str = Field(index=True)  # "aep" | "absa" | "csa" | "abca" | "grant" | ...
    label: str  # display label, e.g. "ABCA"
    color_token: str = Field(default="corp")
    kind: str = Field(default="regulatory")
    # kind ∈ "regulatory" | "insurance" | "corporate" | "grant" | "priority" | "legal" | "financial"

    created_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# Indirect-ownership tables (FK chain back to org via Stream + Country)
# ---------------------------------------------------------------------------


class RegulatoryPhase(TenantScoped, table=True):
    """Phase block within a stream + country. Groups related tasks.

    Phase has NO direct organization_id. Isolation traces through both
    stream_id (Stream→org) and country_id (Country→org). The endpoint
    that creates a Phase MUST verify stream.org_id == country.org_id;
    the model layer permits cross-org mixing.

    Maps to the HTML's ``.phase-block`` element.
    """

    __tablename__ = "regulatory_phases"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        Index("ix_reg_phases_stream", "stream_id"),
        Index("ix_reg_phases_country", "country_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    stream_id: UUID = Field(foreign_key="regulatory_streams.id", index=True)
    country_id: UUID = Field(foreign_key="regulatory_countries.id", index=True)

    name: str
    badge_kind: str = Field(default="now")
    # "now" | "pre" | "arrive" | "post" | "concurrent" | "corp" | "insurance"
    timing_label: str | None = None  # e.g. "Days 1-10", "Months 0-2"
    sort_order: int = Field(default=0)
    default_open: bool = Field(default=False)

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class RegulatoryTask(TenantScoped, table=True):
    """Atomic task within a phase. Maps to HTML's ``.task-item`` element.

    Isolation: Task → Phase → Stream → org (two-hop). Always query through
    the chain.
    """

    __tablename__ = "regulatory_tasks"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        Index("ix_reg_tasks_phase", "phase_id"),
        Index("ix_reg_tasks_assignee", "assignee_user_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    phase_id: UUID = Field(foreign_key="regulatory_phases.id", index=True)

    body: str = Field(sa_column=Column(Text, nullable=False))
    # Inline italic note attached to the task in the HTML — distinct from
    # threaded RegulatoryTaskNote rows (which are user-added later).
    note: str | None = Field(default=None, sa_column=Column(Text, nullable=True))

    completed: bool = Field(default=False, index=True)
    completed_at: datetime | None = None
    completed_by_user_id: UUID | None = Field(default=None, foreign_key="users.id")

    assignee_user_id: UUID | None = Field(default=None, foreign_key="users.id")
    due_date: datetime | None = None

    sort_order: int = Field(default=0)

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class RegulatoryTaskNote(TenantScoped, table=True):
    """Threaded note attached to a task. Multi-author, append-only-with-delete.

    Isolation: TaskNote → Task → Phase → Stream → org (three-hop).
    """

    __tablename__ = "regulatory_task_notes"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (Index("ix_reg_task_notes_task", "task_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    task_id: UUID = Field(foreign_key="regulatory_tasks.id", index=True)

    body: str = Field(sa_column=Column(Text, nullable=False))
    author_user_id: UUID = Field(foreign_key="users.id")

    created_at: datetime = Field(default_factory=utcnow)


class RegulatoryPriorityNote(TenantScoped, table=True):
    """Banner note within a phase, e.g. "🚫 BLOCKING ITEM".

    Maps to HTML's ``.priority-note`` element. Isolation: PriorityNote →
    Phase → Stream → org.
    """

    __tablename__ = "regulatory_priority_notes"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (Index("ix_reg_priority_notes_phase", "phase_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    phase_id: UUID = Field(foreign_key="regulatory_phases.id", index=True)

    body: str = Field(sa_column=Column(Text, nullable=False))
    severity: str = Field(default="info")
    # "critical" | "info" | "warn" | "navy-note"
    sort_order: int = Field(default=0)

    created_at: datetime = Field(default_factory=utcnow)


class RegulatoryTaskTag(TenantScoped, table=True):
    """M:M link between RegulatoryTask and RegulatoryTag.

    THE silent-leak surface. The model permits joining a task in org A
    with a tag in org B. The CREATE endpoint MUST verify both endpoints
    belong to the same org before insert (the test
    ``test_tasktag_links_only_within_same_org`` enforces the post-condition).

    Composite primary key prevents duplicate links and removes the need
    for a synthetic id column.
    """

    __tablename__ = "regulatory_task_tags"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        Index("ix_reg_task_tags_task", "task_id"),
        Index("ix_reg_task_tags_tag", "tag_id"),
    )

    task_id: UUID = Field(foreign_key="regulatory_tasks.id", primary_key=True)
    tag_id: UUID = Field(foreign_key="regulatory_tags.id", primary_key=True)

    created_at: datetime = Field(default_factory=utcnow)
