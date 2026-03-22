"""Add organization_settings and audit_logs tables.

Revision ID: j4d5e6f7g8h9
Revises: i3c4d5e6f7g8
Create Date: 2026-03-21 19:30:00.000000

"""

from __future__ import annotations

import json
import sqlalchemy as sa
from alembic import op

revision = "j4d5e6f7g8h9"
down_revision = "i3c4d5e6f7g8"
branch_labels = None
depends_on = None

DEFAULT_FEATURE_FLAGS = json.dumps({
    "paper_trading": True,
    "paper_bets": True,
    "email": True,
    "polymarket": False,
    "crypto_trading": False,
    "watchlist": True,
    "cost_tracker": True,
    "cron_jobs": True,
    "approvals": True,
})


def upgrade() -> None:
    # --- organization_settings ---
    op.create_table(
        "organization_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("openrouter_api_key_encrypted", sa.String(), nullable=True),
        sa.Column("openrouter_management_key_encrypted", sa.String(), nullable=True),
        sa.Column("default_model_tier_max", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("configured_models_json", sa.String(), nullable=False, server_default="[]"),
        sa.Column("feature_flags_json", sa.String(), nullable=False, server_default=DEFAULT_FEATURE_FLAGS),
        sa.Column("agent_defaults_json", sa.String(), nullable=False, server_default="{}"),
        sa.Column("branding_json", sa.String(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_org_settings_org"),
        sa.UniqueConstraint("organization_id", name="uq_org_settings_org"),
    )
    op.create_index("ix_organization_settings_organization_id", "organization_settings", ["organization_id"])

    # Backfill: create default settings for existing orgs
    op.execute(
        "INSERT INTO organization_settings (id, organization_id, created_at, updated_at) "
        "SELECT gen_random_uuid(), id, NOW(), NOW() FROM organizations "
        "WHERE id NOT IN (SELECT organization_id FROM organization_settings)"
    )

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=False, server_default=""),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("details_json", sa.String(), nullable=False, server_default="{}"),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_audit_logs_org"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_audit_logs_user"),
    )
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("organization_settings")
