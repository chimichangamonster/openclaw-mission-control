"""Add risk management and ticker metadata fields to paper_positions.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-03-20 22:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("paper_positions", sa.Column("company_name", sa.String(), nullable=True))
    op.add_column("paper_positions", sa.Column("exchange", sa.String(), nullable=True))
    op.add_column("paper_positions", sa.Column("sector", sa.String(), nullable=True))
    op.add_column("paper_positions", sa.Column("stop_loss", sa.Float(), nullable=True))
    op.add_column("paper_positions", sa.Column("take_profit", sa.Float(), nullable=True))
    op.add_column("paper_positions", sa.Column("source_report", sa.String(), nullable=True))
    op.add_column("paper_positions", sa.Column("price_updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("paper_positions", "price_updated_at")
    op.drop_column("paper_positions", "source_report")
    op.drop_column("paper_positions", "take_profit")
    op.drop_column("paper_positions", "stop_loss")
    op.drop_column("paper_positions", "sector")
    op.drop_column("paper_positions", "exchange")
    op.drop_column("paper_positions", "company_name")
