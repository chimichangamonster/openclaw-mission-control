"""Add exchange accounts, crypto trade proposals, and crypto positions tables.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-03-18 23:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {item["name"] for item in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("exchange_accounts"):
        op.create_table(
            "exchange_accounts",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("organization_id", sa.Uuid(), nullable=False),
            sa.Column("exchange", sa.String(), nullable=False),
            sa.Column("label", sa.String(), nullable=False, server_default=""),
            sa.Column("api_key_encrypted", sa.String(), nullable=False, server_default=""),
            sa.Column("api_secret_encrypted", sa.String(), nullable=False, server_default=""),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("last_connected_at", sa.DateTime(), nullable=True),
            sa.Column("last_error", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("organization_id", "exchange", name="uq_exchange_accounts_org_exchange"),
        )
        for col in ("organization_id", "exchange", "is_active"):
            op.create_index(f"ix_exchange_accounts_{col}", "exchange_accounts", [col])

    inspector = sa.inspect(bind)
    if not inspector.has_table("crypto_trade_proposals"):
        op.create_table(
            "crypto_trade_proposals",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("organization_id", sa.Uuid(), nullable=False),
            sa.Column("board_id", sa.Uuid(), nullable=False),
            sa.Column("agent_id", sa.Uuid(), nullable=True),
            sa.Column("approval_id", sa.Uuid(), nullable=True),
            sa.Column("exchange_account_id", sa.Uuid(), nullable=False),
            sa.Column("exchange", sa.String(), nullable=False, server_default="binance"),
            sa.Column("symbol", sa.String(), nullable=False, server_default=""),
            sa.Column("side", sa.String(), nullable=False, server_default=""),
            sa.Column("order_type", sa.String(), nullable=False, server_default="LIMIT"),
            sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
            sa.Column("price", sa.Float(), nullable=True),
            sa.Column("stop_price", sa.Float(), nullable=True),
            sa.Column("quote_amount", sa.Float(), nullable=True),
            sa.Column("time_in_force", sa.String(), nullable=False, server_default="GTC"),
            sa.Column("reasoning", sa.String(), nullable=False, server_default=""),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
            sa.Column("strategy", sa.String(), nullable=False, server_default=""),
            sa.Column("entry_signal", sa.String(), nullable=False, server_default=""),
            sa.Column("target_price", sa.Float(), nullable=True),
            sa.Column("stop_loss_price", sa.Float(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("execution_error", sa.String(), nullable=True),
            sa.Column("exchange_order_id", sa.String(), nullable=True),
            sa.Column("filled_price", sa.Float(), nullable=True),
            sa.Column("filled_quantity", sa.Float(), nullable=True),
            sa.Column("executed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["board_id"], ["boards.id"]),
            sa.ForeignKeyConstraint(["agent_id"], ["agents.id"]),
            sa.ForeignKeyConstraint(["approval_id"], ["approvals.id"]),
            sa.ForeignKeyConstraint(["exchange_account_id"], ["exchange_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        for col in ("organization_id", "board_id", "agent_id", "approval_id", "exchange_account_id", "status"):
            op.create_index(f"ix_crypto_trade_proposals_{col}", "crypto_trade_proposals", [col])

    inspector = sa.inspect(bind)
    if not inspector.has_table("crypto_positions"):
        op.create_table(
            "crypto_positions",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("organization_id", sa.Uuid(), nullable=False),
            sa.Column("exchange_account_id", sa.Uuid(), nullable=False),
            sa.Column("symbol", sa.String(), nullable=False),
            sa.Column("free", sa.Float(), nullable=False, server_default="0"),
            sa.Column("locked", sa.Float(), nullable=False, server_default="0"),
            sa.Column("avg_entry_price", sa.Float(), nullable=True),
            sa.Column("current_price", sa.Float(), nullable=True),
            sa.Column("unrealized_pnl", sa.Float(), nullable=True),
            sa.Column("last_synced_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["exchange_account_id"], ["exchange_accounts.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        for col in ("organization_id", "exchange_account_id", "symbol"):
            op.create_index(f"ix_crypto_positions_{col}", "crypto_positions", [col])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in ("crypto_positions", "crypto_trade_proposals", "exchange_accounts"):
        if inspector.has_table(table):
            indexes = _index_names(inspector, table)
            for idx in indexes:
                if idx.startswith("ix_"):
                    op.drop_index(idx, table_name=table)
            op.drop_table(table)
            inspector = sa.inspect(bind)
