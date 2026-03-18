"""Add email accounts, messages, and attachments tables.

Revision ID: f1a2b3c4d5e6
Revises: e3a1b2c4d5f6
Create Date: 2026-03-18 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = "e3a1b2c4d5f6"
branch_labels = None
depends_on = None


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {item["name"] for item in inspector.get_indexes(table_name)}


def upgrade() -> None:
    """Create email account, message, and attachment tables."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # --- email_accounts ---
    if not inspector.has_table("email_accounts"):
        op.create_table(
            "email_accounts",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("organization_id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("provider", sa.String(), nullable=False),
            sa.Column("email_address", sa.String(), nullable=False),
            sa.Column("display_name", sa.String(), nullable=True),
            sa.Column("access_token_encrypted", sa.String(), nullable=False, server_default=""),
            sa.Column("refresh_token_encrypted", sa.String(), nullable=False, server_default=""),
            sa.Column("token_expires_at", sa.DateTime(), nullable=True),
            sa.Column("scopes", sa.String(), nullable=True),
            sa.Column("provider_account_id", sa.String(), nullable=True),
            sa.Column("sync_enabled", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("last_sync_at", sa.DateTime(), nullable=True),
            sa.Column("last_sync_error", sa.String(), nullable=True),
            sa.Column("sync_cursor", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "organization_id", "provider", "email_address",
                name="uq_email_accounts_org_provider_email",
            ),
        )

    inspector = sa.inspect(bind)
    if inspector.has_table("email_accounts"):
        acct_indexes = _index_names(inspector, "email_accounts")
        for col in ("organization_id", "user_id", "provider", "email_address", "sync_enabled"):
            idx_name = f"ix_email_accounts_{col}"
            if idx_name not in acct_indexes:
                op.create_index(idx_name, "email_accounts", [col])

    # --- email_messages ---
    if not inspector.has_table("email_messages"):
        op.create_table(
            "email_messages",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("organization_id", sa.Uuid(), nullable=False),
            sa.Column("email_account_id", sa.Uuid(), nullable=False),
            sa.Column("provider_message_id", sa.String(), nullable=False),
            sa.Column("thread_id", sa.String(), nullable=True),
            sa.Column("subject", sa.String(), nullable=True),
            sa.Column("sender_email", sa.String(), nullable=False, server_default=""),
            sa.Column("sender_name", sa.String(), nullable=True),
            sa.Column("recipients_to", sa.JSON(), nullable=True),
            sa.Column("recipients_cc", sa.JSON(), nullable=True),
            sa.Column("body_text", sa.Text(), nullable=True),
            sa.Column("body_html", sa.Text(), nullable=True),
            sa.Column("received_at", sa.DateTime(), nullable=False),
            sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("is_starred", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("folder", sa.String(), nullable=False, server_default="inbox"),
            sa.Column("labels", sa.JSON(), nullable=True),
            sa.Column("has_attachments", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("triage_status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("triage_category", sa.String(), nullable=True),
            sa.Column("linked_task_id", sa.Uuid(), nullable=True),
            sa.Column("synced_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["email_account_id"], ["email_accounts.id"]),
            sa.ForeignKeyConstraint(["linked_task_id"], ["tasks.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "email_account_id", "provider_message_id",
                name="uq_email_messages_account_provider_msg",
            ),
        )

    inspector = sa.inspect(bind)
    if inspector.has_table("email_messages"):
        msg_indexes = _index_names(inspector, "email_messages")
        for col in (
            "organization_id",
            "email_account_id",
            "provider_message_id",
            "received_at",
            "folder",
            "triage_status",
            "linked_task_id",
        ):
            idx_name = f"ix_email_messages_{col}"
            if idx_name not in msg_indexes:
                op.create_index(idx_name, "email_messages", [col])
        # composite index for inbox queries
        comp_idx = "ix_email_messages_account_folder_received"
        if comp_idx not in msg_indexes:
            op.create_index(
                comp_idx,
                "email_messages",
                ["email_account_id", "folder", "received_at"],
            )

    # --- email_attachments ---
    if not inspector.has_table("email_attachments"):
        op.create_table(
            "email_attachments",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("email_message_id", sa.Uuid(), nullable=False),
            sa.Column("filename", sa.String(), nullable=False, server_default=""),
            sa.Column("content_type", sa.String(), nullable=True),
            sa.Column("size_bytes", sa.Integer(), nullable=True),
            sa.Column("provider_attachment_id", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["email_message_id"], ["email_messages.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    if inspector.has_table("email_attachments"):
        att_indexes = _index_names(inspector, "email_attachments")
        idx_name = "ix_email_attachments_email_message_id"
        if idx_name not in att_indexes:
            op.create_index(idx_name, "email_attachments", ["email_message_id"])


def downgrade() -> None:
    """Drop email attachment, message, and account tables."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name in ("email_attachments", "email_messages", "email_accounts"):
        if inspector.has_table(table_name):
            indexes = _index_names(inspector, table_name)
            for idx in indexes:
                if idx.startswith("ix_"):
                    op.drop_index(idx, table_name=table_name)
            op.drop_table(table_name)
            inspector = sa.inspect(bind)
