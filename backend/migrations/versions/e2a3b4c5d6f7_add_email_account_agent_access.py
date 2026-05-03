"""Add agent_access column to email_accounts table.

Splits the conflated visibility flag into two orthogonal controls:
  - visibility:    who in the org can VIEW the inbox in the UI
  - agent_access:  whether agents (triage cron, reply/archive flows) can read it

Conservative migration default — for existing rows:
  - visibility='shared'  → agent_access='enabled'  (matches today's behavior)
  - visibility='private' → agent_access='disabled' (matches today's behavior — private
    accounts have not been agent-accessible since the visibility flag was introduced)

After this migration deploys, owners of private accounts that previously had triage
running (e.g. henry@wastegurus.ca went from shared → private and silently lost
triage) need to manually flip agent_access back to 'enabled' via the email
integrations settings UI or a one-row UPDATE.

Revision ID: e2a3b4c5d6f7
Revises: c2631f58866b
Create Date: 2026-05-03

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e2a3b4c5d6f7"
down_revision = "c2631f58866b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add column with server-side default 'enabled' so any concurrent insert
    # during the migration gets a sensible value. We then immediately backfill
    # existing rows based on visibility, then drop the server default so future
    # inserts use the application-layer default from the SQLModel.
    op.add_column(
        "email_accounts",
        sa.Column(
            "agent_access",
            sa.String(),
            nullable=False,
            server_default="enabled",
        ),
    )
    op.create_index(
        "ix_email_accounts_agent_access",
        "email_accounts",
        ["agent_access"],
    )

    # Backfill: existing private accounts default to disabled (preserves today's
    # behavior). Existing shared accounts stay enabled (no-op — server default
    # already set them). This conservative migration ensures we don't silently
    # start agent-processing accounts that were marked private specifically to
    # exclude agents.
    op.execute(
        "UPDATE email_accounts SET agent_access = 'disabled' "
        "WHERE visibility = 'private'"
    )

    # Drop the server default so future inserts rely on the SQLModel default
    # ('enabled'), keeping the column behavior consistent with the model.
    op.alter_column("email_accounts", "agent_access", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_email_accounts_agent_access", table_name="email_accounts")
    op.drop_column("email_accounts", "agent_access")
