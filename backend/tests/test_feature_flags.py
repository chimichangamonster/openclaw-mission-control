# ruff: noqa: INP001
"""Unit tests for feature flag resolution and default merging."""

from __future__ import annotations

import json

from app.models.organization_settings import DEFAULT_FEATURE_FLAGS


class TestDefaultFeatureFlags:
    """Verify default flags are sensible."""

    def test_defaults_exist(self) -> None:
        assert isinstance(DEFAULT_FEATURE_FLAGS, dict)
        assert len(DEFAULT_FEATURE_FLAGS) > 0

    def test_expected_flags_present(self) -> None:
        expected = [
            "paper_trading",
            "paper_bets",
            "email",
            "polymarket",
            "crypto_trading",
            "watchlist",
            "cost_tracker",
            "cron_jobs",
            "approvals",
        ]
        for flag in expected:
            assert flag in DEFAULT_FEATURE_FLAGS, f"Missing default flag: {flag}"

    def test_risky_features_disabled_by_default(self) -> None:
        assert DEFAULT_FEATURE_FLAGS["polymarket"] is False
        assert DEFAULT_FEATURE_FLAGS["crypto_trading"] is False

    def test_safe_features_enabled_by_default(self) -> None:
        assert DEFAULT_FEATURE_FLAGS["paper_trading"] is True
        assert DEFAULT_FEATURE_FLAGS["paper_bets"] is True
        assert DEFAULT_FEATURE_FLAGS["email"] is True
        assert DEFAULT_FEATURE_FLAGS["watchlist"] is True
        assert DEFAULT_FEATURE_FLAGS["cost_tracker"] is True


class TestFeatureFlagMerging:
    """Test feature flag merging logic (same as OrganizationSettings.feature_flags property)."""

    @staticmethod
    def _merge_flags(overrides: dict[str, bool]) -> dict[str, bool]:
        """Replicate the merging logic from OrganizationSettings.feature_flags."""
        base = dict(DEFAULT_FEATURE_FLAGS)
        base.update(overrides)
        return base

    def test_default_flags_returned_when_no_overrides(self) -> None:
        flags = self._merge_flags({})
        assert flags == DEFAULT_FEATURE_FLAGS

    def test_override_disables_default_enabled(self) -> None:
        flags = self._merge_flags({"paper_trading": False})
        assert flags["paper_trading"] is False
        assert flags["email"] is True  # unchanged

    def test_override_enables_default_disabled(self) -> None:
        flags = self._merge_flags({"polymarket": True})
        assert flags["polymarket"] is True
        assert flags["crypto_trading"] is False  # unchanged

    def test_unknown_flags_preserved(self) -> None:
        flags = self._merge_flags({"future_feature": True})
        assert flags["future_feature"] is True
        assert "paper_trading" in flags

    def test_full_override(self) -> None:
        all_off = {k: False for k in DEFAULT_FEATURE_FLAGS}
        flags = self._merge_flags(all_off)
        assert all(v is False for v in flags.values())

    def test_default_json_roundtrip(self) -> None:
        """Serializing and deserializing defaults should be idempotent."""
        serialized = json.dumps(DEFAULT_FEATURE_FLAGS)
        deserialized = json.loads(serialized)
        merged = self._merge_flags(deserialized)
        assert merged == DEFAULT_FEATURE_FLAGS
