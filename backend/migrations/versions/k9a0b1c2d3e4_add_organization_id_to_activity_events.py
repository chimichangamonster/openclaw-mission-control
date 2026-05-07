"""Add organization_id to activity_events for per-org error scoping.

Closes the multi-tenancy gap on /cost-tracker/errors — previously every org
could see every other org's error log because activity_events was a flat,
orgless table. Existing rows stay NULL (treated as platform-wide unscoped,
which is correct for circuit_breaker / http / pre-fix bulk-tracked errors).

New track_error() calls thread org_id where available (budget, cron_watchdog
when board_id resolves to an org). Wrapper-level callers (circuit_breaker,
http middleware) deliberately stay NULL — those errors are genuinely
platform-wide.

Index added because the read query is `WHERE event_type LIKE 'system.error%'
AND (organization_id = :org_id OR organization_id IS NULL)`.

Revision ID: k9a0b1c2d3e4
Revises: j8a9b0c1d2e3
Create Date: 2026-05-07

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "k9a0b1c2d3e4"
down_revision = "j8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "activity_events",
        sa.Column("organization_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_activity_events_organization_id",
        "activity_events",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_activity_events_organization_id",
        "activity_events",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_activity_events_organization_id", table_name="activity_events")
    op.drop_constraint(
        "fk_activity_events_organization_id", "activity_events", type_="foreignkey"
    )
    op.drop_column("activity_events", "organization_id")
