"""Add org_context_files table.

Phase 1 of the Org-Context Files primitive (planning-next-sprint.md item 58).
Stores per-org reference documents with embedding column for Phase 2's
semantic-search endpoint. The pgvector extension is already enabled (used
by ``vector_memories``); this migration only adds the new table.

Revision ID: c1d2e3f4a5b6
Revises: a1b2c7d8e9f0
Create Date: 2026-04-27 19:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]

revision = "c1d2e3f4a5b6"
down_revision = "a1b2c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_context_files",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column(
            "content_type",
            sa.String(),
            nullable=False,
            server_default="application/octet-stream",
        ),
        sa.Column("category", sa.String(), nullable=False, server_default="other"),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("visibility", sa.String(), nullable=False, server_default="shared"),
        sa.Column(
            "is_living_data",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "uploaded_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_updated",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_org_context_files_organization_id",
        "org_context_files",
        ["organization_id"],
    )
    op.create_index(
        "ix_org_context_files_filename",
        "org_context_files",
        ["filename"],
    )
    op.create_index(
        "ix_org_context_files_category",
        "org_context_files",
        ["category"],
    )
    op.create_index(
        "ix_org_context_files_org_category",
        "org_context_files",
        ["organization_id", "category"],
    )


def downgrade() -> None:
    op.drop_index("ix_org_context_files_org_category", table_name="org_context_files")
    op.drop_index("ix_org_context_files_category", table_name="org_context_files")
    op.drop_index("ix_org_context_files_filename", table_name="org_context_files")
    op.drop_index("ix_org_context_files_organization_id", table_name="org_context_files")
    op.drop_table("org_context_files")
