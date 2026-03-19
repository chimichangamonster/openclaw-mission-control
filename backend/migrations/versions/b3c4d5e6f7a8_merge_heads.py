"""Merge migration heads.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7, a9b1c2d3e4f7
Create Date: 2026-03-18 22:00:00.000000

"""

from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "b3c4d5e6f7a8"
down_revision = ("a2b3c4d5e6f7", "a9b1c2d3e4f7")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Merge two parallel migration heads."""
    pass


def downgrade() -> None:
    """No-op downgrade for merge."""
    pass
