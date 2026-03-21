"""Add total_fees and trade_count to paper_positions.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-03-21 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("paper_positions", sa.Column("total_fees", sa.Float(), nullable=False, server_default="0"))
    op.add_column("paper_positions", sa.Column("trade_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("paper_positions", "trade_count")
    op.drop_column("paper_positions", "total_fees")
