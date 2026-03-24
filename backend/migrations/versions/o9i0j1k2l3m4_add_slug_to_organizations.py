"""Add slug to organizations for per-org gateway workspace naming.

Revision ID: o9i0j1k2l3m4
Revises: n8h9i0j1k2l3
Create Date: 2026-03-23 23:50:00.000000

"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op

revision = "o9i0j1k2l3m4"
down_revision = "n8h9i0j1k2l3"
branch_labels = None
depends_on = None


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def upgrade() -> None:
    op.add_column("organizations", sa.Column("slug", sa.String(), nullable=False, server_default=""))
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    # Backfill slugs from org names
    conn = op.get_bind()
    orgs = conn.execute(sa.text("SELECT id, name FROM organizations")).fetchall()
    for org_id, name in orgs:
        slug = _slugify(name)
        conn.execute(
            sa.text("UPDATE organizations SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": org_id},
        )


def downgrade() -> None:
    op.drop_index("ix_organizations_slug", "organizations")
    op.drop_column("organizations", "slug")
