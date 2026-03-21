"""Add watchlist_items table for tracking report tickers.

Revision ID: g8a9b0c1d2e3
Revises: f7a8b9c0d1e2
Create Date: 2026-03-20 23:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "g8a9b0c1d2e3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("yahoo_ticker", sa.String(), nullable=False, server_default=""),
        sa.Column("company_name", sa.String(), nullable=True),
        sa.Column("exchange", sa.String(), nullable=True),
        sa.Column("sector", sa.String(), nullable=True),
        sa.Column("source_report", sa.String(), nullable=False, server_default=""),
        sa.Column("report_rating", sa.String(), nullable=True),
        sa.Column("expected_low", sa.Float(), nullable=True),
        sa.Column("expected_high", sa.Float(), nullable=True),
        sa.Column("current_price", sa.Float(), nullable=True),
        sa.Column("rsi", sa.Float(), nullable=True),
        sa.Column("volume_ratio", sa.Float(), nullable=True),
        sa.Column("sentiment", sa.String(), nullable=True),
        sa.Column("sentiment_confidence", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="watching"),
        sa.Column("alert_reason", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("price_updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["paper_portfolios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_watchlist_items_portfolio_id"), "watchlist_items", ["portfolio_id"])
    op.create_index(op.f("ix_watchlist_items_symbol"), "watchlist_items", ["symbol"])


def downgrade() -> None:
    op.drop_index(op.f("ix_watchlist_items_symbol"), table_name="watchlist_items")
    op.drop_index(op.f("ix_watchlist_items_portfolio_id"), table_name="watchlist_items")
    op.drop_table("watchlist_items")
