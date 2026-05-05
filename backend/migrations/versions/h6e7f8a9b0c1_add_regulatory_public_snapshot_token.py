"""Add regulatory_public_snapshot_token to organization_settings.

Item 101 v2 Phase 1b.2 — supports the unauthenticated public snapshot
endpoint that the magnetik-solutions marketing site SSR-fetches. Token
is per-org and rotatable via the rotate-token endpoint.

Nullable: an org without a published snapshot has no token, and the
public endpoint returns 404 for any unknown token (token-as-only-credential
pattern).

Revision ID: h6e7f8a9b0c1
Revises: g5d6e7f8a9b0
Create Date: 2026-05-04

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "h6e7f8a9b0c1"
down_revision = "g5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organization_settings",
        sa.Column("regulatory_public_snapshot_token", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_organization_settings_regulatory_public_snapshot_token",
        "organization_settings",
        ["regulatory_public_snapshot_token"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_organization_settings_regulatory_public_snapshot_token",
        table_name="organization_settings",
    )
    op.drop_column("organization_settings", "regulatory_public_snapshot_token")
