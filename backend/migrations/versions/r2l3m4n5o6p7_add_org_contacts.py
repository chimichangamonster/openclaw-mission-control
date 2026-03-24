"""Add org_contacts table for external contact directory.

Revision ID: r2l3m4n5o6p7
Revises: q1k2l3m4n5o6
Create Date: 2026-03-24 13:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "r2l3m4n5o6p7"
down_revision = "q1k2l3m4n5o6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("company", sa.String(), nullable=False, server_default=""),
        sa.Column("phone", sa.String(), nullable=False, server_default=""),
        sa.Column("role", sa.String(), nullable=False, server_default=""),
        sa.Column("notes", sa.String(), nullable=False, server_default=""),
        sa.Column("source", sa.String(), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "email", name="uq_org_contacts_org_email"),
    )
    op.create_index("ix_org_contacts_organization_id", "org_contacts", ["organization_id"])
    op.create_index("ix_org_contacts_email", "org_contacts", ["email"])
    op.create_index("ix_org_contacts_source", "org_contacts", ["source"])


def downgrade() -> None:
    op.drop_index("ix_org_contacts_source", table_name="org_contacts")
    op.drop_index("ix_org_contacts_email", table_name="org_contacts")
    op.drop_index("ix_org_contacts_organization_id", table_name="org_contacts")
    op.drop_table("org_contacts")
