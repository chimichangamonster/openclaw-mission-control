"""Add model_call_log table for LLM reliability tracking.

Revision ID: a1b2c3d4e5f6
Revises: z0a1b2c3d4e5
Create Date: 2026-04-15 20:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "z0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_call_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("model", sa.String(), nullable=False, index=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("provider_name", sa.String(), nullable=True),
        sa.Column("skill_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, index=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(), nullable=True),
        sa.Column("error_body", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, index=True),
    )

    op.create_index(
        "ix_model_call_log_model_created",
        "model_call_log",
        ["model", "created_at"],
    )
    op.create_index(
        "ix_model_call_log_status_created",
        "model_call_log",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_model_call_log_org_created",
        "model_call_log",
        ["organization_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_model_call_log_org_created", table_name="model_call_log")
    op.drop_index("ix_model_call_log_status_created", table_name="model_call_log")
    op.drop_index("ix_model_call_log_model_created", table_name="model_call_log")
    op.drop_table("model_call_log")
