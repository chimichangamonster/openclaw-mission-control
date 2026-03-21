"""Add budget_configs and daily_agent_spends tables.

Revision ID: h2b3c4d5e6f7
Revises: g8a9b0c1d2e3
Create Date: 2026-03-21 12:30:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "h2b3c4d5e6f7"
down_revision = "g8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "budget_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("monthly_budget", sa.Float(), nullable=False, server_default="25.0"),
        sa.Column("alert_thresholds_json", sa.String(), nullable=False, server_default="[50, 80, 95]"),
        sa.Column(
            "agent_daily_limits_json",
            sa.String(),
            nullable=False,
            server_default='{"the-claw": 2.0, "market-scout": 1.0, "sports-analyst": 2.0, "stock-analyst": 1.5}',
        ),
        sa.Column("throttle_to_tier1_on_exceed", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("alerts_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_alert_month", sa.String(), nullable=False, server_default=""),
        sa.Column("last_alert_thresholds_hit_json", sa.String(), nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "daily_agent_spends",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_name", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("model_breakdown_json", sa.String(), nullable=False, server_default="{}"),
        sa.Column("session_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_name", "date", name="uq_agent_date"),
    )
    op.create_index("ix_daily_agent_spends_agent_name", "daily_agent_spends", ["agent_name"])
    op.create_index("ix_daily_agent_spends_date", "daily_agent_spends", ["date"])


def downgrade() -> None:
    op.drop_table("daily_agent_spends")
    op.drop_table("budget_configs")
