"""Add model_pins_json to organization_settings for model version pinning.

Revision ID: v6p7q8r9s0t1
Revises: u5o6p7q8r9s0
Create Date: 2026-03-30 12:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v6p7q8r9s0t1"
down_revision = "u5o6p7q8r9s0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organization_settings",
        sa.Column("model_pins_json", sa.String(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("organization_settings", "model_pins_json")
