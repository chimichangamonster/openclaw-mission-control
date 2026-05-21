"""Add partner_webhook_deliveries dead-letter / failure audit table.

Revision ID: r3c4d5e6f7g8
Revises: q2b3c4d5e6f7
Create Date: 2026-05-21 20:00:00.000000

See `docs/business/partner-api-v1-scope.md` (Webhook security → Retry schedule
+ Failures audit endpoint sections) for design.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "r3c4d5e6f7g8"
down_revision = "q2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partner_webhook_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "subscription_id",
            sa.Uuid(),
            sa.ForeignKey("partner_webhook_subscriptions.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            index=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("partner_webhook_deliveries")
