"""Add visibility column to email_accounts for per-user email scoping.

Revision ID: p0j1k2l3m4n5
Revises: o9i0j1k2l3m4
Create Date: 2026-03-24 12:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p0j1k2l3m4n5"
down_revision = "o9i0j1k2l3m4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_accounts",
        sa.Column("visibility", sa.String(), nullable=False, server_default="shared"),
    )
    op.create_index("ix_email_accounts_visibility", "email_accounts", ["visibility"])


def downgrade() -> None:
    op.drop_index("ix_email_accounts_visibility", table_name="email_accounts")
    op.drop_column("email_accounts", "visibility")
