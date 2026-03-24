"""Add visibility to google_calendar_connections and allow multi-connection per org.

Revision ID: q1k2l3m4n5o6
Revises: p0j1k2l3m4n5
Create Date: 2026-03-24 12:30:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "q1k2l3m4n5o6"
down_revision = "p0j1k2l3m4n5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add visibility column
    op.add_column(
        "google_calendar_connections",
        sa.Column("visibility", sa.String(), nullable=False, server_default="shared"),
    )
    op.create_index(
        "ix_google_calendar_connections_visibility",
        "google_calendar_connections",
        ["visibility"],
    )

    # Replace unique constraint: (org, provider_account) -> (org, user, provider_account)
    op.drop_constraint("uq_gcal_org_account", "google_calendar_connections", type_="unique")
    op.create_unique_constraint(
        "uq_gcal_org_user_account",
        "google_calendar_connections",
        ["organization_id", "user_id", "provider_account_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_gcal_org_user_account", "google_calendar_connections", type_="unique")
    op.create_unique_constraint(
        "uq_gcal_org_account",
        "google_calendar_connections",
        ["organization_id", "provider_account_id"],
    )
    op.drop_index("ix_google_calendar_connections_visibility", table_name="google_calendar_connections")
    op.drop_column("google_calendar_connections", "visibility")
