"""Add personal (sole-prop) bookkeeping tables.

Creates the four tables that power the ``/bookkeeping`` page on the
Personal org. Deliberately separate from ``bk_*`` tables. See the
docstring in ``app/models/personal_bookkeeping.py`` for rationale.

Revision ID: a1b2c7d8e9f0
Revises: a9c2d7e4f1b3
Create Date: 2026-04-21 15:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b2c7d8e9f0"
down_revision = "a9c2d7e4f1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "personal_reconciliation_months",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("period", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("td_line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amex_line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("business_income", sa.Float(), nullable=False, server_default="0"),
        sa.Column("business_expenses", sa.Float(), nullable=False, server_default="0"),
        sa.Column("vehicle_expenses", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "gst_collected_informational",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "gst_paid_informational",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "flagged_line_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column(
            "locked_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "organization_id", "period", name="uq_personal_recon_org_period"
        ),
    )
    op.create_index(
        "ix_personal_reconciliation_months_organization_id",
        "personal_reconciliation_months",
        ["organization_id"],
    )
    op.create_index(
        "ix_personal_reconciliation_months_period",
        "personal_reconciliation_months",
        ["period"],
    )
    op.create_index(
        "ix_personal_recon_org_status",
        "personal_reconciliation_months",
        ["organization_id", "status"],
    )

    op.create_table(
        "personal_statement_files",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "reconciliation_month_id",
            sa.Uuid(),
            sa.ForeignKey("personal_reconciliation_months.id"),
            nullable=True,
        ),
        sa.Column("period", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("local_path", sa.Text(), nullable=True),
        sa.Column("retention_until", sa.Date(), nullable=False),
        sa.Column(
            "replaced_by_id",
            sa.Uuid(),
            sa.ForeignKey("personal_statement_files.id"),
            nullable=True,
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "uploaded_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "organization_id", "sha256", name="uq_personal_statement_org_sha256"
        ),
    )
    op.create_index(
        "ix_personal_statement_files_organization_id",
        "personal_statement_files",
        ["organization_id"],
    )
    op.create_index(
        "ix_personal_statement_files_sha256",
        "personal_statement_files",
        ["sha256"],
    )
    op.create_index(
        "ix_personal_statement_org_period",
        "personal_statement_files",
        ["organization_id", "period"],
    )

    op.create_table(
        "personal_transactions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "reconciliation_month_id",
            sa.Uuid(),
            sa.ForeignKey("personal_reconciliation_months.id"),
            nullable=False,
        ),
        sa.Column(
            "statement_file_id",
            sa.Uuid(),
            sa.ForeignKey("personal_statement_files.id"),
            nullable=True,
        ),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("txn_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("incoming", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("bucket", sa.String(), nullable=False, server_default="ambiguous"),
        sa.Column("t2125_line", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column(
            "needs_receipt", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "receipt_filed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("receipt_asset_id", sa.Uuid(), nullable=True),
        sa.Column("user_note", sa.Text(), nullable=True),
        sa.Column("classified_by", sa.String(), nullable=False, server_default="auto"),
        sa.Column(
            "classified_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("original_row_hash", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_personal_transactions_organization_id",
        "personal_transactions",
        ["organization_id"],
    )
    op.create_index(
        "ix_personal_transactions_original_row_hash",
        "personal_transactions",
        ["original_row_hash"],
    )
    op.create_index(
        "ix_personal_transactions_bucket",
        "personal_transactions",
        ["bucket"],
    )
    op.create_index(
        "ix_personal_txn_month",
        "personal_transactions",
        ["reconciliation_month_id"],
    )
    op.create_index(
        "ix_personal_txn_org_bucket",
        "personal_transactions",
        ["organization_id", "bucket"],
    )
    op.create_index(
        "ix_personal_txn_hash",
        "personal_transactions",
        ["organization_id", "original_row_hash"],
    )

    op.create_table(
        "personal_vendor_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("bucket", sa.String(), nullable=False),
        sa.Column("t2125_line", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column(
            "needs_receipt", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("applies_to_source", sa.String(), nullable=True),
        sa.Column("source_month", sa.String(), nullable=False, server_default="seed"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_personal_vendor_rules_organization_id",
        "personal_vendor_rules",
        ["organization_id"],
    )
    op.create_index(
        "ix_personal_vendor_rule_org_active",
        "personal_vendor_rules",
        ["organization_id", "active"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_personal_vendor_rule_org_active",
        table_name="personal_vendor_rules",
    )
    op.drop_index(
        "ix_personal_vendor_rules_organization_id",
        table_name="personal_vendor_rules",
    )
    op.drop_table("personal_vendor_rules")

    op.drop_index("ix_personal_txn_hash", table_name="personal_transactions")
    op.drop_index("ix_personal_txn_org_bucket", table_name="personal_transactions")
    op.drop_index("ix_personal_txn_month", table_name="personal_transactions")
    op.drop_index(
        "ix_personal_transactions_bucket", table_name="personal_transactions"
    )
    op.drop_index(
        "ix_personal_transactions_original_row_hash",
        table_name="personal_transactions",
    )
    op.drop_index(
        "ix_personal_transactions_organization_id",
        table_name="personal_transactions",
    )
    op.drop_table("personal_transactions")

    op.drop_index(
        "ix_personal_statement_org_period",
        table_name="personal_statement_files",
    )
    op.drop_index(
        "ix_personal_statement_files_sha256",
        table_name="personal_statement_files",
    )
    op.drop_index(
        "ix_personal_statement_files_organization_id",
        table_name="personal_statement_files",
    )
    op.drop_table("personal_statement_files")

    op.drop_index(
        "ix_personal_recon_org_status",
        table_name="personal_reconciliation_months",
    )
    op.drop_index(
        "ix_personal_reconciliation_months_period",
        table_name="personal_reconciliation_months",
    )
    op.drop_index(
        "ix_personal_reconciliation_months_organization_id",
        table_name="personal_reconciliation_months",
    )
    op.drop_table("personal_reconciliation_months")
