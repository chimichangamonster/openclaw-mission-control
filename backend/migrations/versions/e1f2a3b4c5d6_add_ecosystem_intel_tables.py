"""Add ecosystem_repos + ecosystem_snapshots tables.

Tracks trending GitHub repos in the agent/AI ecosystem for the
`/ecosystem-intel` page (Vantage Solutions org). Refresh runs daily.

Revision ID: e1f2a3b4c5d6
Revises: z0a1b2c3d4e5
Create Date: 2026-04-30 12:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "z0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ecosystem_repos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("full_name", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("owner", sa.String(), nullable=False, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("html_url", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=True, index=True),
        sa.Column("category", sa.String(), nullable=False, server_default="other", index=True),
        sa.Column("stars", sa.Integer(), nullable=False, server_default="0", index=True),
        sa.Column("forks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("open_issues", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("topics_json", sa.String(), nullable=False, server_default="[]"),
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("repo_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
    )

    op.create_table(
        "ecosystem_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repo_id",
            sa.Uuid(),
            sa.ForeignKey("ecosystem_repos.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
        sa.Column("stars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("forks", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("ecosystem_snapshots")
    op.drop_table("ecosystem_repos")
