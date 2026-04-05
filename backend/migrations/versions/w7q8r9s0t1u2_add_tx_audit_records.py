"""Add tx_audit_records table for pentest TX audit trail.

Revision ID: w7q8r9s0t1u2
Revises: v6p7q8r9s0t1
Create Date: 2026-04-02 12:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "w7q8r9s0t1u2"
down_revision = "v6p7q8r9s0t1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tx_audit_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("tx_mode", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("endpoint", sa.String(), nullable=False, server_default=""),
        sa.Column("parameters_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("rf_details_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("target_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column("justification", sa.String(), nullable=True),
        sa.Column("profile_key", sa.String(), nullable=True),
        sa.Column("roe_reference", sa.String(), nullable=True),
        sa.Column("result_status", sa.String(), nullable=False, server_default=""),
        sa.Column("result_detail", sa.String(), nullable=False, server_default=""),
        sa.Column("bridge_tx_id", sa.String(), nullable=True),
        sa.Column("agent_id", sa.String(), nullable=True),
        sa.Column("mac_real", sa.String(), nullable=True),
        sa.Column("mac_spoofed", sa.String(), nullable=True),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_tx_audit_records_org",
        ),
    )
    op.create_index("ix_tx_audit_records_organization_id", "tx_audit_records", ["organization_id"])
    op.create_index("ix_tx_audit_records_tx_mode", "tx_audit_records", ["tx_mode"])
    op.create_index("ix_tx_audit_records_action", "tx_audit_records", ["action"])
    op.create_index("ix_tx_audit_records_profile_key", "tx_audit_records", ["profile_key"])
    op.create_index("ix_tx_audit_records_result_status", "tx_audit_records", ["result_status"])
    op.create_index("ix_tx_audit_records_bridge_tx_id", "tx_audit_records", ["bridge_tx_id"])
    op.create_index("ix_tx_audit_records_approval_id", "tx_audit_records", ["approval_id"])
    op.create_index("ix_tx_audit_records_captured_at", "tx_audit_records", ["captured_at"])


def downgrade() -> None:
    op.drop_index("ix_tx_audit_records_captured_at", table_name="tx_audit_records")
    op.drop_index("ix_tx_audit_records_approval_id", table_name="tx_audit_records")
    op.drop_index("ix_tx_audit_records_bridge_tx_id", table_name="tx_audit_records")
    op.drop_index("ix_tx_audit_records_result_status", table_name="tx_audit_records")
    op.drop_index("ix_tx_audit_records_profile_key", table_name="tx_audit_records")
    op.drop_index("ix_tx_audit_records_action", table_name="tx_audit_records")
    op.drop_index("ix_tx_audit_records_tx_mode", table_name="tx_audit_records")
    op.drop_index("ix_tx_audit_records_organization_id", table_name="tx_audit_records")
    op.drop_table("tx_audit_records")
