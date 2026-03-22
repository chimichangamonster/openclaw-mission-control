"""Add timezone and location to organization_settings.

Revision ID: n8h9i0j1k2l3
Revises: m7g8h9i0j1k2
Create Date: 2026-03-22 23:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "n8h9i0j1k2l3"
down_revision = "m7g8h9i0j1k2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organization_settings", sa.Column("timezone", sa.String(), nullable=False, server_default="America/Edmonton"))
    op.add_column("organization_settings", sa.Column("location", sa.String(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("organization_settings", "location")
    op.drop_column("organization_settings", "timezone")
