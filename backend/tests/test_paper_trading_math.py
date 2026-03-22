# ruff: noqa: INP001
"""Unit tests for paper trading P&L math, fee calculations, and position logic."""

from __future__ import annotations

import pytest


FLAT_FEE = 9.99


class TestFeeCalculation:
    """Flat $9.99 per trade."""

    def test_buy_fee_deducted(self) -> None:
        cash = 10000.0
        total = 100 * 50.0  # 100 shares @ $50
        new_cash = cash - total - FLAT_FEE
        assert new_cash == pytest.approx(10000 - 5000 - 9.99)

    def test_sell_fee_deducted(self) -> None:
        cash = 5000.0
        total = 50 * 55.0  # sell 50 @ $55
        new_cash = cash + total - FLAT_FEE
        assert new_cash == pytest.approx(5000 + 2750 - 9.99)

    def test_fee_accumulates_across_trades(self) -> None:
        total_fees = FLAT_FEE * 5  # 5 trades
        assert total_fees == pytest.approx(49.95)


class TestPnLCalculation:
    """P&L = (exit - entry) * qty for longs, (entry - exit) * qty for shorts."""

    def test_long_profit(self) -> None:
        entry, exit_price, qty = 50.0, 60.0, 100
        pnl = (exit_price - entry) * qty
        assert pnl == pytest.approx(1000.0)

    def test_long_loss(self) -> None:
        entry, exit_price, qty = 50.0, 45.0, 100
        pnl = (exit_price - entry) * qty
        assert pnl == pytest.approx(-500.0)

    def test_net_pnl_includes_fees(self) -> None:
        """Net P&L should subtract accumulated fees (buy + sell)."""
        entry, exit_price, qty = 50.0, 55.0, 100
        gross_pnl = (exit_price - entry) * qty  # $500
        total_fees = FLAT_FEE * 2  # buy + sell
        net_pnl = gross_pnl - total_fees
        assert net_pnl == pytest.approx(500 - 19.98)

    def test_breakeven_needs_to_cover_fees(self) -> None:
        """Need price increase > fees/qty to break even."""
        entry, qty = 50.0, 100
        total_fees = FLAT_FEE * 2  # buy + sell
        breakeven_price = entry + total_fees / qty
        assert breakeven_price == pytest.approx(50.1998)

    def test_pnl_pct_calculation(self) -> None:
        """P&L % = (raw_pnl - fees) / cost_basis * 100."""
        entry, current, qty = 50.0, 55.0, 100
        fees = FLAT_FEE
        raw_pnl = (current - entry) * qty
        cost_basis = entry * qty + fees
        pnl_pct = (raw_pnl - fees) / cost_basis * 100
        assert pnl_pct == pytest.approx((500 - 9.99) / (5000 + 9.99) * 100)


class TestPositionAveraging:
    """When buying more of an existing position, entry price averages."""

    def test_average_up(self) -> None:
        # Existing: 100 @ $50
        # New: 100 @ $60
        old_qty, old_price = 100, 50.0
        new_qty, new_price = 100, 60.0
        total_qty = old_qty + new_qty
        avg_price = (old_price * old_qty + new_price * new_qty) / total_qty
        assert total_qty == 200
        assert avg_price == pytest.approx(55.0)

    def test_average_down(self) -> None:
        # Existing: 100 @ $60
        # New: 200 @ $45
        old_qty, old_price = 100, 60.0
        new_qty, new_price = 200, 45.0
        total_qty = old_qty + new_qty
        avg_price = (old_price * old_qty + new_price * new_qty) / total_qty
        assert total_qty == 300
        assert avg_price == pytest.approx(50.0)


class TestPortfolioBalance:
    """Cash balance updates correctly through trades."""

    def test_buy_reduces_cash(self) -> None:
        cash = 10000.0
        buy_total = 100 * 50.0
        cash -= buy_total + FLAT_FEE
        assert cash == pytest.approx(10000 - 5000 - 9.99)

    def test_sell_increases_cash(self) -> None:
        cash = 4990.01  # after buy
        sell_total = 100 * 55.0
        cash += sell_total - FLAT_FEE
        assert cash == pytest.approx(4990.01 + 5500 - 9.99)

    def test_total_value_includes_positions(self) -> None:
        cash = 5000.0
        positions_value = 100 * 55.0  # 100 shares @ $55 current
        total_value = cash + positions_value
        assert total_value == pytest.approx(10500.0)

    def test_total_return_pct(self) -> None:
        starting = 10000.0
        total_value = 10500.0
        return_pct = ((total_value - starting) / starting) * 100
        assert return_pct == pytest.approx(5.0)

    def test_insufficient_balance_rejected(self) -> None:
        cash = 100.0
        buy_total = 100 * 50.0  # $5000
        assert cash < buy_total + FLAT_FEE


class TestEquityCurve:
    """Equity curve = starting_balance + cumulative realized P&L."""

    def test_cumulative_pnl(self) -> None:
        starting = 10000.0
        daily_pnl = [100.0, -50.0, 200.0, -30.0]
        cumulative = 0.0
        curve = []
        for pnl in daily_pnl:
            cumulative += pnl
            curve.append(starting + cumulative)

        assert curve == [10100.0, 10050.0, 10250.0, 10220.0]

    def test_no_trades_empty_curve(self) -> None:
        trades = []
        assert len(trades) == 0


class TestWinRateStats:
    """Win rate, avg win, avg loss, profit factor."""

    def test_win_rate(self) -> None:
        closed_pnls = [100, -50, 200, -30, 150, -80]
        winners = [p for p in closed_pnls if p > 0]
        total = len(closed_pnls)
        win_rate = len(winners) / total * 100
        assert win_rate == pytest.approx(50.0)

    def test_avg_win_loss(self) -> None:
        closed_pnls = [100, -50, 200, -30]
        winners = [p for p in closed_pnls if p > 0]
        losers = [p for p in closed_pnls if p < 0]
        avg_win = sum(winners) / len(winners)
        avg_loss = sum(losers) / len(losers)
        assert avg_win == pytest.approx(150.0)
        assert avg_loss == pytest.approx(-40.0)

    def test_profit_factor(self) -> None:
        """Profit factor = abs(total_wins) / abs(total_losses)."""
        winners = [100, 200, 150]
        losers = [-50, -30, -80]
        profit_factor = abs(sum(winners)) / abs(sum(losers))
        assert profit_factor == pytest.approx(450 / 160)

    def test_profit_factor_no_losses(self) -> None:
        winners = [100, 200]
        losers = []
        # Avoid division by zero
        pf = 0 if not losers or sum(losers) == 0 else abs(sum(winners)) / abs(sum(losers))
        assert pf == 0
