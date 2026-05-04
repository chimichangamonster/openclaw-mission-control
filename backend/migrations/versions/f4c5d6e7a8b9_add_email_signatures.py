"""Add email_signatures table for per-account multi-signature library.

Each EmailAccount can have multiple signatures, exactly one marked default.
Send pipeline appends the resolved signature's HTML to outbound bodies —
provider APIs (Microsoft Graph / Zoho / Gmail) do not auto-append signatures
configured in their web UIs (those are client-side only).

Revision ID: f4c5d6e7a8b9
Revises: e2a3b4c5d6f7
Create Date: 2026-05-04

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f4c5d6e7a8b9"
down_revision = "e2a3b4c5d6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_signatures",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "email_account_id",
            sa.Uuid(),
            sa.ForeignKey("email_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_email_signatures_organization_id",
        "email_signatures",
        ["organization_id"],
    )
    op.create_index(
        "ix_email_signatures_email_account_id",
        "email_signatures",
        ["email_account_id"],
    )
    op.create_index(
        "ix_email_signatures_is_default",
        "email_signatures",
        ["is_default"],
    )


def downgrade() -> None:
    op.drop_index("ix_email_signatures_is_default", table_name="email_signatures")
    op.drop_index("ix_email_signatures_email_account_id", table_name="email_signatures")
    op.drop_index("ix_email_signatures_organization_id", table_name="email_signatures")
    op.drop_table("email_signatures")
