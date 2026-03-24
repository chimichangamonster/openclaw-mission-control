"""Add wecom_connections table for WeCom integration.

Revision ID: s3m4n5o6p7q8
Revises: r2l3m4n5o6p7
Create Date: 2026-03-24 16:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "s3m4n5o6p7q8"
down_revision = "r2l3m4n5o6p7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wecom_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("corp_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False, server_default=""),
        sa.Column("callback_token", sa.String(), nullable=False, server_default=""),
        sa.Column("encoding_aes_key", sa.String(), nullable=False, server_default=""),
        sa.Column("corp_secret_encrypted", sa.String(), nullable=True),
        sa.Column("access_token_encrypted", sa.String(), nullable=True),
        sa.Column("access_token_expires_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("target_agent_id", sa.String(), nullable=False, server_default="the-claw"),
        sa.Column("target_channel", sa.String(), nullable=False, server_default="general"),
        sa.Column("label", sa.String(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "corp_id", name="uq_wecom_org_corp"),
    )
    op.create_index("ix_wecom_connections_organization_id", "wecom_connections", ["organization_id"])
    op.create_index("ix_wecom_connections_corp_id", "wecom_connections", ["corp_id"])


def downgrade() -> None:
    op.drop_index("ix_wecom_connections_corp_id", table_name="wecom_connections")
    op.drop_index("ix_wecom_connections_organization_id", table_name="wecom_connections")
    op.drop_table("wecom_connections")
