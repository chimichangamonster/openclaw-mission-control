"""Add size_bytes column to org_context_files.

Session 4 of the Org-Context Files primitive (planning-next-sprint.md item 58).
Powers the file-size dashboard — admins need to see total storage used per
org and per category to decide what to prune.

Existing rows get NULL (we don't have the original byte counts to backfill).
The stats endpoint sums over non-NULL values; UI reports "N files (some
sizes unknown)" if any row has NULL bytes.

Revision ID: d1a2b3c4e5f6
Revises: c1d2e3f4a5b6
Create Date: 2026-04-29 17:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d1a2b3c4e5f6"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "org_context_files",
        sa.Column("size_bytes", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("org_context_files", "size_bytes")
