"""Add trade_trace_id to paper_positions for Langfuse trade outcome scoring.

Revision ID: a9c2d7e4f1b3
Revises: z0a1b2c3d4e5
Create Date: 2026-04-15 18:30:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a9c2d7e4f1b3"
down_revision = "z0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "paper_positions",
        sa.Column("trade_trace_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("paper_positions", "trade_trace_id")
