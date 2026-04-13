"""Add triage_trace_id to email_messages for Langfuse quality scoring.

Revision ID: y9z0a1b2c3d4
Revises: x8y9z0a1b2c3
Create Date: 2026-04-12 22:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "y9z0a1b2c3d4"
down_revision = "x8y9z0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_messages",
        sa.Column("triage_trace_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("email_messages", "triage_trace_id")
