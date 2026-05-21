"""Add partner_api_keys table for the Partner API v1 namespace.

Revision ID: p1a2b3c4d5e6
Revises: k9a0b1c2d3e4
Create Date: 2026-05-21 18:00:00.000000

See `docs/business/partner-api-v1-scope.md` (Auth model section) for design.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p1a2b3c4d5e6"
down_revision = "k9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partner_api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("key_id", sa.String(), nullable=False, unique=True, index=True),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column(
            "scopes",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("rate_limit_override", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            index=True,
        ),
        sa.Column("revoked_reason", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("partner_api_keys")
