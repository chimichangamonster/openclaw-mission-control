"""Add organization_id to budget_configs and daily_agent_spends tables.

Revision ID: i3c4d5e6f7g8
Revises: h2b3c4d5e6f7
Create Date: 2026-03-21 18:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "i3c4d5e6f7g8"
down_revision = "h2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- budget_configs ---
    # Add organization_id column (nullable first for existing rows)
    op.add_column(
        "budget_configs",
        sa.Column("organization_id", sa.Uuid(), nullable=True),
    )
    # Backfill: assign existing rows to the first organization
    op.execute(
        "UPDATE budget_configs SET organization_id = (SELECT id FROM organizations LIMIT 1) "
        "WHERE organization_id IS NULL"
    )
    # Make non-nullable
    op.alter_column("budget_configs", "organization_id", nullable=False)
    op.create_foreign_key(
        "fk_budget_configs_org", "budget_configs", "organizations",
        ["organization_id"], ["id"],
    )
    op.create_index("ix_budget_configs_organization_id", "budget_configs", ["organization_id"])
    op.create_unique_constraint("uq_budget_configs_org", "budget_configs", ["organization_id"])

    # --- daily_agent_spends ---
    op.add_column(
        "daily_agent_spends",
        sa.Column("organization_id", sa.Uuid(), nullable=True),
    )
    op.execute(
        "UPDATE daily_agent_spends SET organization_id = (SELECT id FROM organizations LIMIT 1) "
        "WHERE organization_id IS NULL"
    )
    op.alter_column("daily_agent_spends", "organization_id", nullable=False)
    op.create_foreign_key(
        "fk_daily_agent_spends_org", "daily_agent_spends", "organizations",
        ["organization_id"], ["id"],
    )
    op.create_index("ix_daily_agent_spends_organization_id", "daily_agent_spends", ["organization_id"])
    # Replace old unique constraint with org-scoped one
    op.drop_constraint("uq_agent_date", "daily_agent_spends", type_="unique")
    op.create_unique_constraint("uq_org_agent_date", "daily_agent_spends", ["organization_id", "agent_name", "date"])


def downgrade() -> None:
    # daily_agent_spends
    op.drop_constraint("uq_org_agent_date", "daily_agent_spends", type_="unique")
    op.create_unique_constraint("uq_agent_date", "daily_agent_spends", ["agent_name", "date"])
    op.drop_constraint("fk_daily_agent_spends_org", "daily_agent_spends", type_="foreignkey")
    op.drop_index("ix_daily_agent_spends_organization_id", "daily_agent_spends")
    op.drop_column("daily_agent_spends", "organization_id")

    # budget_configs
    op.drop_constraint("uq_budget_configs_org", "budget_configs", type_="unique")
    op.drop_constraint("fk_budget_configs_org", "budget_configs", type_="foreignkey")
    op.drop_index("ix_budget_configs_organization_id", "budget_configs")
    op.drop_column("budget_configs", "organization_id")
