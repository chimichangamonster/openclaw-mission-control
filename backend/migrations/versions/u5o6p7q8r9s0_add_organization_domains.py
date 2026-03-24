"""Add organization_domains table for domain-based auto-assignment.

Revision ID: u5o6p7q8r9s0
Revises: t4n5o6p7q8r9
Create Date: 2026-03-24 23:40:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "u5o6p7q8r9s0"
down_revision = "t4n5o6p7q8r9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_domains",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("default_role", sa.String(), nullable=False, server_default="member"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain", name="uq_org_domains_domain"),
    )
    op.create_index("ix_organization_domains_domain", "organization_domains", ["domain"])
    op.create_index("ix_organization_domains_organization_id", "organization_domains", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_organization_domains_organization_id", table_name="organization_domains")
    op.drop_index("ix_organization_domains_domain", table_name="organization_domains")
    op.drop_table("organization_domains")
