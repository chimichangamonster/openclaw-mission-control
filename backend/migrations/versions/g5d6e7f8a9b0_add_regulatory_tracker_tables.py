"""Add regulatory tracker tables (item 101 v2 Phase 1a).

Eight tables that mirror the structure of magnetik-solutions'
``equipment-tracker.html``:

  Direct ownership (TenantScoped):
    - regulatory_streams    (Corporate / Eboiler / MagnetGas / future)
    - regulatory_countries  (CA active; IN + KE schemas reserved)
    - regulatory_tags       (regulatory bodies, priorities, insurance, grants)

  Indirect ownership (FK chain to org via parent):
    - regulatory_phases         FK→Stream + Country
    - regulatory_tasks          FK→Phase
    - regulatory_task_notes     FK→Task (threaded notes)
    - regulatory_priority_notes FK→Phase (banner notes)
    - regulatory_task_tags      M2M Task↔Tag (the silent-leak surface)

Isolation contract is locked by tests/test_regulatory_isolation.py.
Endpoint code (Phase 1b) MUST scope queries through the FK chain and
validate same-org-membership when creating M2M links.

See docs/business/magnetik-platform-evolution.md for the long arc.

Revision ID: g5d6e7f8a9b0
Revises: f4c5d6e7a8b9
Create Date: 2026-05-04

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "g5d6e7f8a9b0"
down_revision = "f4c5d6e7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # regulatory_streams
    # ------------------------------------------------------------------
    op.create_table(
        "regulatory_streams",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "color_token",
            sa.String(),
            nullable=False,
            server_default=sa.text("'navy'"),
        ),
        sa.Column("budget_estimate", sa.Numeric(14, 2), nullable=True),
        sa.Column("regulator_label", sa.String(), nullable=True),
        sa.Column("timeline_label", sa.String(), nullable=True),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("organization_id", "slug", name="uq_reg_stream_org_slug"),
    )
    op.create_index(
        "ix_regulatory_streams_organization_id",
        "regulatory_streams",
        ["organization_id"],
    )
    op.create_index("ix_reg_streams_org", "regulatory_streams", ["organization_id"])
    op.create_index("ix_regulatory_streams_slug", "regulatory_streams", ["slug"])

    # ------------------------------------------------------------------
    # regulatory_countries
    # ------------------------------------------------------------------
    op.create_table(
        "regulatory_countries",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'pipeline'"),
        ),
        sa.Column("display_label", sa.String(), nullable=False),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("organization_id", "code", name="uq_reg_country_org_code"),
    )
    op.create_index(
        "ix_regulatory_countries_organization_id",
        "regulatory_countries",
        ["organization_id"],
    )
    op.create_index("ix_reg_countries_org", "regulatory_countries", ["organization_id"])
    op.create_index("ix_regulatory_countries_code", "regulatory_countries", ["code"])

    # ------------------------------------------------------------------
    # regulatory_tags
    # ------------------------------------------------------------------
    op.create_table(
        "regulatory_tags",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column(
            "color_token",
            sa.String(),
            nullable=False,
            server_default=sa.text("'corp'"),
        ),
        sa.Column(
            "kind",
            sa.String(),
            nullable=False,
            server_default=sa.text("'regulatory'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("organization_id", "slug", name="uq_reg_tag_org_slug"),
    )
    op.create_index(
        "ix_regulatory_tags_organization_id",
        "regulatory_tags",
        ["organization_id"],
    )
    op.create_index("ix_reg_tags_org", "regulatory_tags", ["organization_id"])
    op.create_index("ix_regulatory_tags_slug", "regulatory_tags", ["slug"])

    # ------------------------------------------------------------------
    # regulatory_phases
    # ------------------------------------------------------------------
    op.create_table(
        "regulatory_phases",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "stream_id",
            sa.Uuid(),
            sa.ForeignKey("regulatory_streams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "country_id",
            sa.Uuid(),
            sa.ForeignKey("regulatory_countries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "badge_kind",
            sa.String(),
            nullable=False,
            server_default=sa.text("'now'"),
        ),
        sa.Column("timing_label", sa.String(), nullable=True),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "default_open",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_reg_phases_stream", "regulatory_phases", ["stream_id"])
    op.create_index("ix_reg_phases_country", "regulatory_phases", ["country_id"])
    op.create_index("ix_regulatory_phases_stream_id", "regulatory_phases", ["stream_id"])
    op.create_index(
        "ix_regulatory_phases_country_id", "regulatory_phases", ["country_id"]
    )

    # ------------------------------------------------------------------
    # regulatory_tasks
    # ------------------------------------------------------------------
    op.create_table(
        "regulatory_tasks",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "phase_id",
            sa.Uuid(),
            sa.ForeignKey("regulatory_phases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "completed_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "assignee_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_reg_tasks_phase", "regulatory_tasks", ["phase_id"])
    op.create_index("ix_reg_tasks_assignee", "regulatory_tasks", ["assignee_user_id"])
    op.create_index("ix_regulatory_tasks_phase_id", "regulatory_tasks", ["phase_id"])
    op.create_index("ix_regulatory_tasks_completed", "regulatory_tasks", ["completed"])

    # ------------------------------------------------------------------
    # regulatory_task_notes
    # ------------------------------------------------------------------
    op.create_table(
        "regulatory_task_notes",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "task_id",
            sa.Uuid(),
            sa.ForeignKey("regulatory_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "author_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_reg_task_notes_task", "regulatory_task_notes", ["task_id"])
    op.create_index(
        "ix_regulatory_task_notes_task_id", "regulatory_task_notes", ["task_id"]
    )

    # ------------------------------------------------------------------
    # regulatory_priority_notes
    # ------------------------------------------------------------------
    op.create_table(
        "regulatory_priority_notes",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "phase_id",
            sa.Uuid(),
            sa.ForeignKey("regulatory_phases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "severity",
            sa.String(),
            nullable=False,
            server_default=sa.text("'info'"),
        ),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_reg_priority_notes_phase", "regulatory_priority_notes", ["phase_id"]
    )
    op.create_index(
        "ix_regulatory_priority_notes_phase_id",
        "regulatory_priority_notes",
        ["phase_id"],
    )

    # ------------------------------------------------------------------
    # regulatory_task_tags  (M2M, composite primary key)
    # ------------------------------------------------------------------
    op.create_table(
        "regulatory_task_tags",
        sa.Column(
            "task_id",
            sa.Uuid(),
            sa.ForeignKey("regulatory_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tag_id",
            sa.Uuid(),
            sa.ForeignKey("regulatory_tags.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("task_id", "tag_id"),
    )
    op.create_index("ix_reg_task_tags_task", "regulatory_task_tags", ["task_id"])
    op.create_index("ix_reg_task_tags_tag", "regulatory_task_tags", ["tag_id"])


def downgrade() -> None:
    # Drop in reverse FK-dependency order so children go before parents.
    op.drop_index("ix_reg_task_tags_tag", table_name="regulatory_task_tags")
    op.drop_index("ix_reg_task_tags_task", table_name="regulatory_task_tags")
    op.drop_table("regulatory_task_tags")

    op.drop_index(
        "ix_regulatory_priority_notes_phase_id", table_name="regulatory_priority_notes"
    )
    op.drop_index("ix_reg_priority_notes_phase", table_name="regulatory_priority_notes")
    op.drop_table("regulatory_priority_notes")

    op.drop_index(
        "ix_regulatory_task_notes_task_id", table_name="regulatory_task_notes"
    )
    op.drop_index("ix_reg_task_notes_task", table_name="regulatory_task_notes")
    op.drop_table("regulatory_task_notes")

    op.drop_index("ix_regulatory_tasks_completed", table_name="regulatory_tasks")
    op.drop_index("ix_regulatory_tasks_phase_id", table_name="regulatory_tasks")
    op.drop_index("ix_reg_tasks_assignee", table_name="regulatory_tasks")
    op.drop_index("ix_reg_tasks_phase", table_name="regulatory_tasks")
    op.drop_table("regulatory_tasks")

    op.drop_index("ix_regulatory_phases_country_id", table_name="regulatory_phases")
    op.drop_index("ix_regulatory_phases_stream_id", table_name="regulatory_phases")
    op.drop_index("ix_reg_phases_country", table_name="regulatory_phases")
    op.drop_index("ix_reg_phases_stream", table_name="regulatory_phases")
    op.drop_table("regulatory_phases")

    op.drop_index("ix_regulatory_tags_slug", table_name="regulatory_tags")
    op.drop_index("ix_reg_tags_org", table_name="regulatory_tags")
    op.drop_index("ix_regulatory_tags_organization_id", table_name="regulatory_tags")
    op.drop_table("regulatory_tags")

    op.drop_index("ix_regulatory_countries_code", table_name="regulatory_countries")
    op.drop_index("ix_reg_countries_org", table_name="regulatory_countries")
    op.drop_index(
        "ix_regulatory_countries_organization_id", table_name="regulatory_countries"
    )
    op.drop_table("regulatory_countries")

    op.drop_index("ix_regulatory_streams_slug", table_name="regulatory_streams")
    op.drop_index("ix_reg_streams_org", table_name="regulatory_streams")
    op.drop_index(
        "ix_regulatory_streams_organization_id", table_name="regulatory_streams"
    )
    op.drop_table("regulatory_streams")
