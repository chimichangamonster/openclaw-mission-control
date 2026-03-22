"""Add bookkeeping tables — clients, workers, jobs, placements, timesheets, expenses, invoices, transactions.

Revision ID: k5e6f7g8h9i0
Revises: j4d5e6f7g8h9
Create Date: 2026-03-22 16:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "k5e6f7g8h9i0"
down_revision = "j4d5e6f7g8h9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Clients
    op.create_table(
        "bk_clients",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("contact_name", sa.String(), nullable=True),
        sa.Column("contact_email", sa.String(), nullable=True),
        sa.Column("contact_phone", sa.String(), nullable=True),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("billing_terms", sa.String(), nullable=False, server_default="net30"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Workers
    op.create_table(
        "bk_workers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("hourly_rate", sa.Float(), nullable=True),
        sa.Column("safety_certs_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("csts_expiry", sa.Date(), nullable=True),
        sa.Column("ossa_expiry", sa.Date(), nullable=True),
        sa.Column("first_aid_expiry", sa.Date(), nullable=True),
        sa.Column("h2s_expiry", sa.Date(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="available"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Jobs
    op.create_table(
        "bk_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("bk_clients.id"), nullable=True, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("site_address", sa.String(), nullable=True),
        sa.Column("job_type", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("budget", sa.Float(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Placements
    op.create_table(
        "bk_placements",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("worker_id", sa.Uuid(), sa.ForeignKey("bk_workers.id"), nullable=False, index=True),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("bk_jobs.id"), nullable=False, index=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("bill_rate", sa.Float(), nullable=False),
        sa.Column("pay_rate", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Timesheets
    op.create_table(
        "bk_timesheets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("placement_id", sa.Uuid(), sa.ForeignKey("bk_placements.id"), nullable=True, index=True),
        sa.Column("worker_id", sa.Uuid(), sa.ForeignKey("bk_workers.id"), nullable=False, index=True),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("bk_jobs.id"), nullable=False, index=True),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("regular_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("overtime_hours", sa.Float(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Expenses
    op.create_table(
        "bk_expenses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("worker_id", sa.Uuid(), sa.ForeignKey("bk_workers.id"), nullable=True, index=True),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("bk_jobs.id"), nullable=True, index=True),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("gst_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("vendor", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("receipt_url", sa.String(), nullable=True),
        sa.Column("ocr_data_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("expense_date", sa.Date(), nullable=False, server_default=sa.func.current_date()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Invoices
    op.create_table(
        "bk_invoices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("bk_clients.id"), nullable=False, index=True),
        sa.Column("invoice_number", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("subtotal", sa.Float(), nullable=False, server_default="0"),
        sa.Column("gst_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total", sa.Float(), nullable=False, server_default="0"),
        sa.Column("issued_date", sa.Date(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("paid_date", sa.Date(), nullable=True),
        sa.Column("exported_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Invoice lines
    op.create_table(
        "bk_invoice_lines",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("invoice_id", sa.Uuid(), sa.ForeignKey("bk_invoices.id"), nullable=False, index=True),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unit_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("timesheet_id", sa.Uuid(), sa.ForeignKey("bk_timesheets.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Transactions (general ledger)
    op.create_table(
        "bk_transactions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("gst_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("txn_date", sa.Date(), nullable=False, server_default=sa.func.current_date()),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("bk_jobs.id"), nullable=True, index=True),
        sa.Column("expense_id", sa.Uuid(), sa.ForeignKey("bk_expenses.id"), nullable=True),
        sa.Column("invoice_id", sa.Uuid(), sa.ForeignKey("bk_invoices.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("bk_transactions")
    op.drop_table("bk_invoice_lines")
    op.drop_table("bk_invoices")
    op.drop_table("bk_expenses")
    op.drop_table("bk_timesheets")
    op.drop_table("bk_placements")
    op.drop_table("bk_jobs")
    op.drop_table("bk_workers")
    op.drop_table("bk_clients")
