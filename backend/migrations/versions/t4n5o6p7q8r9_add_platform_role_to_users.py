"""Add platform_role column to users table.

Revision ID: t4n5o6p7q8r9
Revises: s3m4n5o6p7q8
Create Date: 2026-03-24 20:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "t4n5o6p7q8r9"
down_revision = "s3m4n5o6p7q8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("platform_role", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "platform_role")
