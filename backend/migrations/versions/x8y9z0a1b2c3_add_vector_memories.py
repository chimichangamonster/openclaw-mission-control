"""Add vector_memories table for agent semantic memory (pgvector).

Revision ID: x8y9z0a1b2c3
Revises: w7q8r9s0t1u2
Create Date: 2026-04-12 16:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "x8y9z0a1b2c3"
down_revision = "w7q8r9s0t1u2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "vector_memories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", sa.text("vector(1536)").type, nullable=False),
        sa.Column("source", sa.String(), nullable=False, index=True),
        sa.Column("agent_id", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.String(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )

    # Composite index for org-scoped source filtering
    op.create_index(
        "ix_vector_memories_org_source",
        "vector_memories",
        ["organization_id", "source"],
    )

    # HNSW index for fast approximate nearest-neighbor cosine similarity search
    op.execute(
        "CREATE INDEX ix_vector_memories_embedding "
        "ON vector_memories "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_vector_memories_embedding", table_name="vector_memories")
    op.drop_index("ix_vector_memories_org_source", table_name="vector_memories")
    op.drop_table("vector_memories")
    op.execute("DROP EXTENSION IF EXISTS vector")
