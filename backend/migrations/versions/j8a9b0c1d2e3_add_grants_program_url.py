"""Add program_url to grants (item 118 sub-C).

Operator-paste-target field for the public landing page of each granting
program (e.g. ERA Industrial Transformation Challenge URL, Alberta
Innovates Voucher Program URL). Surfaced on table row + drawer header
as an external-link icon when populated.

Nullable, no default. Existing rows stay null until backfilled by seed
update or operator edit. No data migration; pure column add.

Revision ID: j8a9b0c1d2e3
Revises: i7f8a9b0c1d2
Create Date: 2026-05-06

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "j8a9b0c1d2e3"
down_revision = "i7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "grants",
        sa.Column("program_url", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("grants", "program_url")
