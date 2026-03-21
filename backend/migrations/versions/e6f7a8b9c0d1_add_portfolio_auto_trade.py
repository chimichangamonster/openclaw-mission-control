"""Add auto_trade flag to paper_portfolios.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-03-20 23:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("paper_portfolios", sa.Column("auto_trade", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("paper_portfolios", "auto_trade")
