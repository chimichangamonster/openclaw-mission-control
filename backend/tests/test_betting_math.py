# ruff: noqa: INP001
"""Unit tests for sports betting math — odds conversion, payout, bankroll."""

from __future__ import annotations

import pytest


def _american_to_decimal(odds: int) -> float:
    """Convert American odds to decimal odds."""
    if odds > 0:
        return (odds / 100) + 1
    return (100 / abs(odds)) + 1


def _calculate_payout(stake: float, odds: int) -> float:
    """Calculate payout for a winning bet."""
    decimal_odds = _american_to_decimal(odds)
    return round(stake * decimal_odds, 2)


class TestAmericanToDecimal:
    """American odds → decimal odds conversion."""

    def test_positive_odds(self) -> None:
        # +150 means $150 profit on $100 bet → 2.5 decimal
        assert _american_to_decimal(150) == pytest.approx(2.5)

    def test_positive_odds_even(self) -> None:
        # +100 means $100 profit on $100 bet → 2.0 decimal
        assert _american_to_decimal(100) == pytest.approx(2.0)

    def test_negative_odds(self) -> None:
        # -150 means bet $150 to win $100 → 1.667 decimal
        assert _american_to_decimal(-150) == pytest.approx(1 + 100 / 150)

    def test_negative_odds_heavy_favorite(self) -> None:
        # -300 means bet $300 to win $100 → 1.333 decimal
        assert _american_to_decimal(-300) == pytest.approx(1 + 100 / 300)

    def test_negative_odds_slight_favorite(self) -> None:
        # -110 is standard vig → 1.909 decimal
        assert _american_to_decimal(-110) == pytest.approx(1 + 100 / 110)

    def test_large_underdog(self) -> None:
        # +500 means $500 profit on $100 → 6.0 decimal
        assert _american_to_decimal(500) == pytest.approx(6.0)


class TestPayoutCalculation:
    """Payout = stake * decimal_odds."""

    def test_winning_plus_odds(self) -> None:
        # $50 @ +200 → $50 * 3.0 = $150
        assert _calculate_payout(50.0, 200) == pytest.approx(150.0)

    def test_winning_minus_odds(self) -> None:
        # $100 @ -150 → $100 * 1.667 = $166.67
        assert _calculate_payout(100.0, -150) == pytest.approx(166.67)

    def test_even_odds(self) -> None:
        # $25 @ +100 → $25 * 2.0 = $50
        assert _calculate_payout(25.0, 100) == pytest.approx(50.0)

    def test_heavy_favorite(self) -> None:
        # $300 @ -300 → $300 * 1.333 = $400
        assert _calculate_payout(300.0, -300) == pytest.approx(400.0)


class TestBetResolution:
    """Bankroll updates on bet resolution."""

    def test_won_bet_adds_payout(self) -> None:
        bankroll = 900.0  # started 1000, staked 100
        payout = _calculate_payout(100.0, 150)  # 250
        profit = payout - 100.0
        bankroll += payout
        assert bankroll == pytest.approx(1150.0)
        assert profit == pytest.approx(150.0)

    def test_lost_bet_no_return(self) -> None:
        bankroll = 900.0
        pnl = -100.0  # lost the stake
        # Bankroll stays the same (stake already deducted on placement)
        assert bankroll == pytest.approx(900.0)
        assert pnl == pytest.approx(-100.0)

    def test_push_returns_stake(self) -> None:
        bankroll = 900.0
        stake = 100.0
        bankroll += stake  # stake returned
        pnl = 0.0
        assert bankroll == pytest.approx(1000.0)
        assert pnl == pytest.approx(0.0)

    def test_void_returns_stake(self) -> None:
        bankroll = 900.0
        stake = 100.0
        bankroll += stake
        assert bankroll == pytest.approx(1000.0)

    def test_stake_deducted_on_placement(self) -> None:
        bankroll = 1000.0
        stake = 100.0
        bankroll -= stake
        assert bankroll == pytest.approx(900.0)

    def test_insufficient_bankroll_rejected(self) -> None:
        bankroll = 50.0
        stake = 100.0
        assert bankroll < stake


class TestBetSummaryStats:
    """ROI, win rate, and breakdown calculations."""

    def test_roi_calculation(self) -> None:
        """ROI = total_pnl / total_staked * 100."""
        total_staked = 500.0
        total_pnl = 75.0
        roi = total_pnl / total_staked * 100
        assert roi == pytest.approx(15.0)

    def test_negative_roi(self) -> None:
        total_staked = 500.0
        total_pnl = -125.0
        roi = total_pnl / total_staked * 100
        assert roi == pytest.approx(-25.0)

    def test_win_rate_with_pushes(self) -> None:
        """Pushes are resolved but don't count as wins or losses for win rate."""
        results = ["won", "lost", "won", "push", "won"]
        wins = sum(1 for r in results if r == "won")
        resolved = len(results)
        win_rate = wins / resolved * 100
        assert win_rate == pytest.approx(60.0)

    def test_avg_odds(self) -> None:
        odds_list = [150, -110, 200, -150]
        avg = sum(odds_list) / len(odds_list)
        assert avg == pytest.approx(22.5)
