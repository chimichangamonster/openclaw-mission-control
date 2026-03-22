"""Add google_calendar_connections table.

Revision ID: m7g8h9i0j1k2
Revises: l6f7g8h9i0j1
Create Date: 2026-03-22 22:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "m7g8h9i0j1k2"
down_revision = "l6f7g8h9i0j1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_calendar_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider_account_id", sa.String(), nullable=False, server_default=""),
        sa.Column("email_address", sa.String(), nullable=False, server_default=""),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("access_token_encrypted", sa.String(), nullable=False, server_default=""),
        sa.Column("refresh_token_encrypted", sa.String(), nullable=False, server_default=""),
        sa.Column("token_expires_at", sa.DateTime(), nullable=True),
        sa.Column("scopes", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("default_calendar_id", sa.String(), nullable=False, server_default="primary"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "provider_account_id", name="uq_gcal_org_account"),
    )
    op.create_index("ix_google_calendar_connections_organization_id", "google_calendar_connections", ["organization_id"])
    op.create_index("ix_google_calendar_connections_user_id", "google_calendar_connections", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_google_calendar_connections_user_id")
    op.drop_index("ix_google_calendar_connections_organization_id")
    op.drop_table("google_calendar_connections")
