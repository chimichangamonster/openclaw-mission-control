"""Add Polymarket wallet, risk config, trade proposal, position, and history tables.

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-18 12:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {item["name"] for item in inspector.get_indexes(table_name)}


def upgrade() -> None:
    """Create Polymarket trading tables."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # --- polymarket_wallets ---
    if not inspector.has_table("polymarket_wallets"):
        op.create_table(
            "polymarket_wallets",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("organization_id", sa.Uuid(), nullable=False),
            sa.Column("label", sa.String(), nullable=False, server_default=""),
            sa.Column("wallet_address", sa.String(), nullable=False, server_default=""),
            sa.Column("private_key_encrypted", sa.String(), nullable=False, server_default=""),
            sa.Column("api_key_encrypted", sa.String(), nullable=False, server_default=""),
            sa.Column("api_secret_encrypted", sa.String(), nullable=False, server_default=""),
            sa.Column("api_passphrase_encrypted", sa.String(), nullable=False, server_default=""),
            sa.Column("api_credentials_derived_at", sa.DateTime(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", name="uq_polymarket_wallets_org"),
        )
        op.create_index("ix_polymarket_wallets_organization_id", "polymarket_wallets", ["organization_id"])
        op.create_index("ix_polymarket_wallets_is_active", "polymarket_wallets", ["is_active"])

    # --- polymarket_risk_configs ---
    inspector = sa.inspect(bind)
    if not inspector.has_table("polymarket_risk_configs"):
        op.create_table(
            "polymarket_risk_configs",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("organization_id", sa.Uuid(), nullable=False),
            sa.Column("max_trade_size_usdc", sa.Float(), nullable=False, server_default="100.0"),
            sa.Column("daily_loss_limit_usdc", sa.Float(), nullable=True),
            sa.Column("weekly_loss_limit_usdc", sa.Float(), nullable=True),
            sa.Column("max_open_positions", sa.Integer(), nullable=True),
            sa.Column("market_whitelist", sa.JSON(), nullable=True),
            sa.Column("market_blacklist", sa.JSON(), nullable=True),
            sa.Column("require_approval", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", name="uq_polymarket_risk_configs_org"),
        )
        op.create_index("ix_polymarket_risk_configs_organization_id", "polymarket_risk_configs", ["organization_id"])

    # --- trade_proposals ---
    inspector = sa.inspect(bind)
    if not inspector.has_table("trade_proposals"):
        op.create_table(
            "trade_proposals",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("organization_id", sa.Uuid(), nullable=False),
            sa.Column("board_id", sa.Uuid(), nullable=False),
            sa.Column("agent_id", sa.Uuid(), nullable=True),
            sa.Column("approval_id", sa.Uuid(), nullable=True),
            sa.Column("condition_id", sa.String(), nullable=False),
            sa.Column("token_id", sa.String(), nullable=False, server_default=""),
            sa.Column("market_slug", sa.String(), nullable=False, server_default=""),
            sa.Column("market_question", sa.String(), nullable=False, server_default=""),
            sa.Column("outcome_label", sa.String(), nullable=False, server_default=""),
            sa.Column("side", sa.String(), nullable=False, server_default=""),
            sa.Column("size_usdc", sa.Float(), nullable=False, server_default="0"),
            sa.Column("price", sa.Float(), nullable=False, server_default="0"),
            sa.Column("order_type", sa.String(), nullable=False, server_default="GTC"),
            sa.Column("reasoning", sa.String(), nullable=False, server_default=""),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("execution_error", sa.String(), nullable=True),
            sa.Column("polymarket_order_id", sa.String(), nullable=True),
            sa.Column("executed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["board_id"], ["boards.id"]),
            sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
            sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        for col in ("organization_id", "board_id", "agent_id", "approval_id", "condition_id", "status"):
            op.create_index(f"ix_trade_proposals_{col}", "trade_proposals", [col])

    # --- polymarket_positions ---
    inspector = sa.inspect(bind)
    if not inspector.has_table("polymarket_positions"):
        op.create_table(
            "polymarket_positions",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("organization_id", sa.Uuid(), nullable=False),
            sa.Column("condition_id", sa.String(), nullable=False),
            sa.Column("token_id", sa.String(), nullable=False, server_default=""),
            sa.Column("market_slug", sa.String(), nullable=False, server_default=""),
            sa.Column("market_question", sa.String(), nullable=False, server_default=""),
            sa.Column("outcome_label", sa.String(), nullable=False, server_default=""),
            sa.Column("size", sa.Float(), nullable=False, server_default="0"),
            sa.Column("avg_price", sa.Float(), nullable=False, server_default="0"),
            sa.Column("current_price", sa.Float(), nullable=True),
            sa.Column("unrealized_pnl", sa.Float(), nullable=True),
            sa.Column("realized_pnl", sa.Float(), nullable=False, server_default="0"),
            sa.Column("last_synced_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_polymarket_positions_organization_id", "polymarket_positions", ["organization_id"])
        op.create_index("ix_polymarket_positions_condition_id", "polymarket_positions", ["condition_id"])

    # --- trade_history ---
    inspector = sa.inspect(bind)
    if not inspector.has_table("trade_history"):
        op.create_table(
            "trade_history",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("organization_id", sa.Uuid(), nullable=False),
            sa.Column("trade_proposal_id", sa.Uuid(), nullable=True),
            sa.Column("condition_id", sa.String(), nullable=False, server_default=""),
            sa.Column("token_id", sa.String(), nullable=False, server_default=""),
            sa.Column("market_slug", sa.String(), nullable=False, server_default=""),
            sa.Column("market_question", sa.String(), nullable=False, server_default=""),
            sa.Column("outcome_label", sa.String(), nullable=False, server_default=""),
            sa.Column("side", sa.String(), nullable=False, server_default=""),
            sa.Column("size_usdc", sa.Float(), nullable=False, server_default="0"),
            sa.Column("price", sa.Float(), nullable=False, server_default="0"),
            sa.Column("filled_price", sa.Float(), nullable=True),
            sa.Column("polymarket_order_id", sa.String(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default=""),
            sa.Column("executed_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["trade_proposal_id"], ["trade_proposals.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_trade_history_organization_id", "trade_history", ["organization_id"])
        op.create_index("ix_trade_history_trade_proposal_id", "trade_history", ["trade_proposal_id"])


def downgrade() -> None:
    """Drop Polymarket trading tables."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in ("trade_history", "polymarket_positions", "trade_proposals", "polymarket_risk_configs", "polymarket_wallets"):
        if inspector.has_table(table):
            indexes = _index_names(inspector, table)
            for idx in indexes:
                if idx.startswith("ix_"):
                    op.drop_index(idx, table_name=table)
            op.drop_table(table)
            inspector = sa.inspect(bind)
