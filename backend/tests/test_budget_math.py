# ruff: noqa: INP001
"""Unit tests for budget monitoring calculations and threshold alerts."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

# Model tier pricing (from CLAUDE.md)
MODEL_PRICING = {
    "gpt-5-nano": 0.05,  # Tier 1
    "grok-4-fast": 0.20,  # Tier 1
    "deepseek-v3.2": 0.26,  # Tier 2
    "claude-sonnet-4": 3.00,  # Tier 3
    "grok-4": 3.00,  # Tier 3
    "claude-opus-4.6": 15.00,  # Tier 4
}


def estimate_cost(model: str, tokens: int) -> float:
    """Estimate cost based on model and token count (per million tokens)."""
    rate = MODEL_PRICING.get(model, 0.0)
    return round(rate * tokens / 1_000_000, 6)


def check_threshold(current: float, budget: float) -> str | None:
    """Return alert level if threshold crossed."""
    if budget <= 0:
        return None
    pct = current / budget * 100
    if pct >= 95:
        return "critical"
    if pct >= 80:
        return "warning"
    if pct >= 50:
        return "info"
    return None


class TestCostEstimation:
    """Per-model cost calculations."""

    def test_nano_model_cheap(self) -> None:
        # 1M tokens of nano = $0.05
        cost = estimate_cost("gpt-5-nano", 1_000_000)
        assert cost == pytest.approx(0.05)

    def test_sonnet_moderate(self) -> None:
        # 100K tokens of Sonnet = $0.30
        cost = estimate_cost("claude-sonnet-4", 100_000)
        assert cost == pytest.approx(0.30)

    def test_opus_expensive(self) -> None:
        # 100K tokens of Opus = $1.50
        cost = estimate_cost("claude-opus-4.6", 100_000)
        assert cost == pytest.approx(1.50)

    def test_unknown_model_zero(self) -> None:
        cost = estimate_cost("unknown-model", 1_000_000)
        assert cost == 0.0

    def test_zero_tokens(self) -> None:
        cost = estimate_cost("claude-sonnet-4", 0)
        assert cost == 0.0

    def test_deepseek_budget_model(self) -> None:
        # 500K tokens of DeepSeek = $0.13
        cost = estimate_cost("deepseek-v3.2", 500_000)
        assert cost == pytest.approx(0.13)


class TestThresholdAlerts:
    """Budget threshold detection."""

    def test_below_50_no_alert(self) -> None:
        assert check_threshold(4.0, 100.0) is None

    def test_at_50_info(self) -> None:
        assert check_threshold(50.0, 100.0) == "info"

    def test_at_80_warning(self) -> None:
        assert check_threshold(80.0, 100.0) == "warning"

    def test_at_95_critical(self) -> None:
        assert check_threshold(95.0, 100.0) == "critical"

    def test_over_100_critical(self) -> None:
        assert check_threshold(110.0, 100.0) == "critical"

    def test_zero_budget_no_alert(self) -> None:
        assert check_threshold(50.0, 0.0) is None

    def test_exact_boundary_50(self) -> None:
        assert check_threshold(50.0, 100.0) == "info"

    def test_just_below_80(self) -> None:
        assert check_threshold(79.99, 100.0) == "info"


class TestPerAgentSpend:
    """Per-agent daily spend aggregation."""

    def test_aggregate_across_sessions(self) -> None:
        sessions = [
            {"agent": "stock-analyst", "model": "deepseek-v3.2", "tokens": 50_000},
            {"agent": "stock-analyst", "model": "deepseek-v3.2", "tokens": 30_000},
            {"agent": "stock-analyst", "model": "claude-sonnet-4", "tokens": 10_000},
        ]
        total = sum(estimate_cost(s["model"], s["tokens"]) for s in sessions)
        # 80K * 0.26/M + 10K * 3.0/M = 0.0208 + 0.03 = 0.0508
        assert total == pytest.approx(0.0508, abs=0.001)

    def test_daily_limit_exceeded(self) -> None:
        daily_limit = 0.50
        daily_spend = 0.75
        assert daily_spend > daily_limit

    def test_multi_agent_independent(self) -> None:
        """Each agent's spend is tracked independently."""
        agent_spends = {
            "stock-analyst": 0.30,
            "sports-analyst": 0.10,
            "the-claw": 0.50,
        }
        daily_limit = 0.40

        over_limit = [agent for agent, spend in agent_spends.items() if spend > daily_limit]
        assert over_limit == ["the-claw"]


class TestProactiveCompaction:
    """Compaction fallback — reset after repeated compact failures."""

    @pytest.fixture(autouse=True)
    def _clear_fail_counts(self):
        """Reset the module-level fail counter between tests."""
        from app.services.budget_monitor import _compact_fail_counts

        _compact_fail_counts.clear()
        yield
        _compact_fail_counts.clear()

    @staticmethod
    def _make_session(key: str, tokens: int, model: str = "anthropic/claude-sonnet-4") -> dict:
        return {"key": key, "totalTokens": tokens, "model": model, "groupChannel": "#test"}

    @pytest.mark.asyncio
    @patch("app.services.budget_monitor._send_discord_alert", new_callable=AsyncMock)
    @patch("app.services.budget_monitor.track_error", new_callable=AsyncMock)
    @patch("app.services.budget_monitor.reset_session", new_callable=AsyncMock)
    @patch("app.services.budget_monitor.compact_session", new_callable=AsyncMock)
    async def test_compact_success_resets_fail_count(
        self,
        mock_compact,
        mock_reset,
        mock_track,
        mock_alert,
    ):
        from app.services.budget_monitor import (
            GatewayConfig,
            _compact_fail_counts,
            _proactive_compaction,
        )

        mock_compact.return_value = {"compacted": True}
        config = GatewayConfig(url="ws://fake:1234")

        # Pre-seed a fail count
        _compact_fail_counts["agent:test:discord:1"] = 2

        sessions = [self._make_session("agent:test:discord:1", 160_000)]
        await _proactive_compaction(sessions, config)

        mock_compact.assert_called_once()
        mock_reset.assert_not_called()
        assert "agent:test:discord:1" not in _compact_fail_counts

    @pytest.mark.asyncio
    @patch("app.services.budget_monitor._send_discord_alert", new_callable=AsyncMock)
    @patch("app.services.budget_monitor.track_error", new_callable=AsyncMock)
    @patch("app.services.budget_monitor.reset_session", new_callable=AsyncMock)
    @patch("app.services.budget_monitor.compact_session", new_callable=AsyncMock)
    async def test_compact_fail_increments_counter(
        self,
        mock_compact,
        mock_reset,
        mock_track,
        mock_alert,
    ):
        from app.services.budget_monitor import (
            GatewayConfig,
            _compact_fail_counts,
            _proactive_compaction,
        )

        mock_compact.return_value = {"compacted": False}
        config = GatewayConfig(url="ws://fake:1234")

        sessions = [self._make_session("agent:test:discord:1", 160_000)]
        await _proactive_compaction(sessions, config)

        assert _compact_fail_counts["agent:test:discord:1"] == 1
        mock_reset.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.budget_monitor._send_discord_alert", new_callable=AsyncMock)
    @patch("app.services.budget_monitor.track_error", new_callable=AsyncMock)
    @patch("app.services.budget_monitor.reset_session", new_callable=AsyncMock)
    @patch("app.services.budget_monitor.compact_session", new_callable=AsyncMock)
    async def test_reset_after_three_compact_failures(
        self,
        mock_compact,
        mock_reset,
        mock_track,
        mock_alert,
    ):
        from app.services.budget_monitor import (
            GatewayConfig,
            _compact_fail_counts,
            _proactive_compaction,
        )

        mock_compact.return_value = {"compacted": False}
        mock_reset.return_value = {"ok": True}
        config = GatewayConfig(url="ws://fake:1234")

        # Pre-seed 2 failures — next one triggers reset
        _compact_fail_counts["agent:test:discord:1"] = 2

        sessions = [self._make_session("agent:test:discord:1", 160_000)]
        await _proactive_compaction(sessions, config)

        mock_reset.assert_called_once_with("agent:test:discord:1", config=config)
        assert "agent:test:discord:1" not in _compact_fail_counts
        # Should send a Discord alert about the reset
        mock_alert.assert_called()
        alert_text = mock_alert.call_args[0][1]
        assert "SESSION RESET" in alert_text

    @pytest.mark.asyncio
    @patch("app.services.budget_monitor._send_discord_alert", new_callable=AsyncMock)
    @patch("app.services.budget_monitor.track_error", new_callable=AsyncMock)
    @patch("app.services.budget_monitor.reset_session", new_callable=AsyncMock)
    @patch("app.services.budget_monitor.compact_session", new_callable=AsyncMock)
    async def test_below_threshold_no_compact(
        self,
        mock_compact,
        mock_reset,
        mock_track,
        mock_alert,
    ):
        from app.services.budget_monitor import GatewayConfig, _proactive_compaction

        config = GatewayConfig(url="ws://fake:1234")
        # 100K tokens = 50% of 200K window — below 75% threshold
        sessions = [self._make_session("agent:test:discord:1", 100_000)]
        await _proactive_compaction(sessions, config)

        mock_compact.assert_not_called()
        mock_reset.assert_not_called()
