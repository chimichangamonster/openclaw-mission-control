"""merge heads after ecosystem-intel branch

Revision ID: c2631f58866b
Revises: e1f2a3b4c5d6, d1a2b3c4e5f6
Create Date: 2026-04-30 12:37:11.464005

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c2631f58866b'
down_revision = ('e1f2a3b4c5d6', 'd1a2b3c4e5f6')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
