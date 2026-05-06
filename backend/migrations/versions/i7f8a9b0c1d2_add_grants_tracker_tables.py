"""Add grants tracker tables (item 107 v2 Phase 1).

Four tables for the grant-application lifecycle substrate:

  Direct ownership (TenantScoped):
    - grants                       (program metadata, money, contacts)

  Indirect ownership (FK chain to org via Grant):
    - grant_draw_schedules         FK→Grant (milestone burn-down)
    - grant_reporting_deadlines    FK→Grant (interim/final reports + audits)
    - grant_prerequisite_tasks     M2M Grant↔RegulatoryTask (the silent-leak surface)

The M2M to regulatory_tasks lets a grant point at the regulatory tasks
that block its submission (e.g. "Magnetik Solutions Inc. incorporation"
blocks ERA submission). Same cross-org-leak posture as
``regulatory_task_tags``: the model permits the bad write; API code
must validate same-org before insert.

Determinism posture per ``feedback_determinism_first_for_high_liability.md``:
all amounts/dates/statuses are operator-entered SQL. Zero LLM in path.

Revision ID: i7f8a9b0c1d2
Revises: h6e7f8a9b0c1
Create Date: 2026-05-06

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "i7f8a9b0c1d2"
down_revision = "h6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # grants
    # ------------------------------------------------------------------
    op.create_table(
        "grants",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("granting_body", sa.String(), nullable=False),
        sa.Column("program_name", sa.String(), nullable=False),
        sa.Column("application_template_slug", sa.String(), nullable=True),
        sa.Column(
            "application_status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'planned'"),
        ),
        sa.Column("submitted_at", sa.Date(), nullable=True),
        sa.Column("decision_at", sa.Date(), nullable=True),
        sa.Column("awarded_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("matched_funding_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("total_project_value", sa.Numeric(14, 2), nullable=True),
        sa.Column(
            "currency",
            sa.String(),
            nullable=False,
            server_default=sa.text("'CAD'"),
        ),
        sa.Column("project_start_date", sa.Date(), nullable=True),
        sa.Column("project_end_date", sa.Date(), nullable=True),
        sa.Column("incorporation_required_entity", sa.String(), nullable=True),
        sa.Column("cash_coinvestment_required_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("cash_coinvestment_source", sa.String(), nullable=True),
        sa.Column("contact_person", sa.String(), nullable=True),
        sa.Column("contact_email", sa.String(), nullable=True),
        sa.Column(
            "owner_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("notes_md", sa.Text(), nullable=True),
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
    op.create_index("ix_grants_organization_id", "grants", ["organization_id"])
    op.create_index("ix_grants_org", "grants", ["organization_id"])
    op.create_index(
        "ix_grants_application_status", "grants", ["application_status"]
    )

    # ------------------------------------------------------------------
    # grant_draw_schedules
    # ------------------------------------------------------------------
    op.create_table(
        "grant_draw_schedules",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "grant_id",
            sa.Uuid(),
            sa.ForeignKey("grants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("milestone_label", sa.String(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("target_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("drawn_at", sa.Date(), nullable=True),
        sa.Column("drawn_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("notes_md", sa.Text(), nullable=True),
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
    op.create_index(
        "ix_grant_draw_schedules_grant_id", "grant_draw_schedules", ["grant_id"]
    )
    op.create_index("ix_grant_draws_grant", "grant_draw_schedules", ["grant_id"])
    op.create_index(
        "ix_grant_draw_schedules_status", "grant_draw_schedules", ["status"]
    )

    # ------------------------------------------------------------------
    # grant_reporting_deadlines
    # ------------------------------------------------------------------
    op.create_table(
        "grant_reporting_deadlines",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "grant_id",
            sa.Uuid(),
            sa.ForeignKey("grants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("deadline_date", sa.Date(), nullable=False),
        sa.Column(
            "deadline_type",
            sa.String(),
            nullable=False,
            server_default=sa.text("'interim_report'"),
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'upcoming'"),
        ),
        sa.Column("submitted_at", sa.Date(), nullable=True),
        sa.Column("submitted_artifact_url", sa.String(), nullable=True),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("notes_md", sa.Text(), nullable=True),
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
    op.create_index(
        "ix_grant_reporting_deadlines_grant_id",
        "grant_reporting_deadlines",
        ["grant_id"],
    )
    op.create_index(
        "ix_grant_deadlines_grant", "grant_reporting_deadlines", ["grant_id"]
    )
    op.create_index(
        "ix_grant_deadlines_date", "grant_reporting_deadlines", ["deadline_date"]
    )
    op.create_index(
        "ix_grant_reporting_deadlines_status",
        "grant_reporting_deadlines",
        ["status"],
    )

    # ------------------------------------------------------------------
    # grant_prerequisite_tasks (M2M Grant ↔ RegulatoryTask)
    # ------------------------------------------------------------------
    op.create_table(
        "grant_prerequisite_tasks",
        sa.Column(
            "grant_id",
            sa.Uuid(),
            sa.ForeignKey("grants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "regulatory_task_id",
            sa.Uuid(),
            sa.ForeignKey("regulatory_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label_override", sa.String(), nullable=True),
        sa.Column(
            "is_critical",
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
        sa.PrimaryKeyConstraint(
            "grant_id", "regulatory_task_id", name="pk_grant_prerequisite_tasks"
        ),
    )
    op.create_index(
        "ix_grant_prereqs_grant", "grant_prerequisite_tasks", ["grant_id"]
    )
    op.create_index(
        "ix_grant_prereqs_task",
        "grant_prerequisite_tasks",
        ["regulatory_task_id"],
    )


def downgrade() -> None:
    # Reverse FK order: children before parents.
    op.drop_index("ix_grant_prereqs_task", table_name="grant_prerequisite_tasks")
    op.drop_index("ix_grant_prereqs_grant", table_name="grant_prerequisite_tasks")
    op.drop_table("grant_prerequisite_tasks")

    op.drop_index(
        "ix_grant_reporting_deadlines_status", table_name="grant_reporting_deadlines"
    )
    op.drop_index(
        "ix_grant_deadlines_date", table_name="grant_reporting_deadlines"
    )
    op.drop_index(
        "ix_grant_deadlines_grant", table_name="grant_reporting_deadlines"
    )
    op.drop_index(
        "ix_grant_reporting_deadlines_grant_id",
        table_name="grant_reporting_deadlines",
    )
    op.drop_table("grant_reporting_deadlines")

    op.drop_index("ix_grant_draw_schedules_status", table_name="grant_draw_schedules")
    op.drop_index("ix_grant_draws_grant", table_name="grant_draw_schedules")
    op.drop_index(
        "ix_grant_draw_schedules_grant_id", table_name="grant_draw_schedules"
    )
    op.drop_table("grant_draw_schedules")

    op.drop_index("ix_grants_application_status", table_name="grants")
    op.drop_index("ix_grants_org", table_name="grants")
    op.drop_index("ix_grants_organization_id", table_name="grants")
    op.drop_table("grants")
