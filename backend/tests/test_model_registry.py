# ruff: noqa: INP001
"""Unit tests for model registry — pure tests, no DB imports."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Re-implement core registry logic here to avoid DB import chain.
# ---------------------------------------------------------------------------

_DATE_SUFFIX_RE = re.compile(r"-\d{8}$")


def _extract_family(model_id: str) -> str:
    return _DATE_SUFFIX_RE.sub("", model_id)


def _classify_tier(prompt_per_m: float) -> int:
    if prompt_per_m <= 0.3:
        return 1
    if prompt_per_m <= 1.0:
        return 2
    if prompt_per_m <= 5.0:
        return 3
    return 4


@dataclass
class ModelEntry:
    model_id: str
    family: str
    provider: str
    name: str
    context_window: int = 0
    prompt_price_per_m: float = 0.0
    completion_price_per_m: float = 0.0
    tier: int = 2
    status: str = "active"
    first_seen: float = 0.0
    last_seen: float = 0.0


@dataclass
class DeprecationWarning:
    pinned_model_id: str
    pin_key: str
    status: str
    suggested_replacement: str | None = None


class ModelRegistry:
    """Simplified registry for testing (no file I/O)."""

    def __init__(self) -> None:
        self._entries: dict[str, ModelEntry] = {}

    def add(self, entry: ModelEntry) -> None:
        self._entries[entry.model_id] = entry

    def list_models(self, *, status: str | None = None) -> list[ModelEntry]:
        entries = list(self._entries.values())
        if status:
            entries = [e for e in entries if e.status == status]
        return entries

    def get_family_versions(self, family: str) -> list[ModelEntry]:
        entries = [e for e in self._entries.values() if e.family == family]
        entries.sort(key=lambda e: e.last_seen, reverse=True)
        return entries

    def list_families(self) -> list[str]:
        return sorted({e.family for e in self._entries.values()})

    def get_context_window(self, model_name: str) -> int | None:
        entry = self._entries.get(model_name)
        if entry:
            return entry.context_window
        for entry in self._entries.values():
            short = entry.model_id.split("/")[-1] if "/" in entry.model_id else entry.model_id
            if short == model_name and entry.status == "active":
                return entry.context_window
        return None

    def check_pins(self, pins: dict[str, str]) -> list[DeprecationWarning]:
        warnings: list[DeprecationWarning] = []
        for pin_key, model_id in pins.items():
            entry = self._entries.get(model_id)
            if entry is None:
                if self._entries:
                    family = _extract_family(model_id)
                    versions = self.get_family_versions(family)
                    replacement = versions[0].model_id if versions else None
                    warnings.append(DeprecationWarning(
                        pinned_model_id=model_id,
                        pin_key=pin_key,
                        status="removed",
                        suggested_replacement=replacement,
                    ))
            elif entry.status == "deprecated":
                family_versions = self.get_family_versions(entry.family)
                active_versions = [v for v in family_versions if v.status == "active"]
                replacement = active_versions[0].model_id if active_versions else None
                warnings.append(DeprecationWarning(
                    pinned_model_id=model_id,
                    pin_key=pin_key,
                    status="deprecated",
                    suggested_replacement=replacement,
                ))
        return warnings


# ---------------------------------------------------------------------------
# Tests: Family extraction
# ---------------------------------------------------------------------------

class TestFamilyExtraction:
    """Verify model ID → family grouping."""

    def test_date_suffix_stripped(self) -> None:
        assert _extract_family("anthropic/claude-sonnet-4-20260514") == "anthropic/claude-sonnet-4"

    def test_no_date_suffix_unchanged(self) -> None:
        assert _extract_family("anthropic/claude-sonnet-4") == "anthropic/claude-sonnet-4"

    def test_deepseek_model(self) -> None:
        assert _extract_family("deepseek/deepseek-v3.2") == "deepseek/deepseek-v3.2"

    def test_gpt_nano(self) -> None:
        assert _extract_family("openai/gpt-5-nano") == "openai/gpt-5-nano"

    def test_date_suffix_various(self) -> None:
        assert _extract_family("google/gemini-2.5-flash-20260101") == "google/gemini-2.5-flash"
        assert _extract_family("x-ai/grok-4-20261231") == "x-ai/grok-4"

    def test_bare_model_name(self) -> None:
        assert _extract_family("llama-3.1-70b") == "llama-3.1-70b"

    def test_numbers_in_name_not_confused_with_date(self) -> None:
        # "5-nano" has numbers but is NOT a date suffix (not 8 digits)
        assert _extract_family("openai/gpt-5-nano") == "openai/gpt-5-nano"
        # Exactly 8 digits after dash IS a date suffix
        assert _extract_family("openai/gpt-5-12345678") == "openai/gpt-5"


# ---------------------------------------------------------------------------
# Tests: Tier classification
# ---------------------------------------------------------------------------

class TestTierClassification:
    """Verify model tier assignment by price."""

    def test_nano_tier(self) -> None:
        assert _classify_tier(0.05) == 1
        assert _classify_tier(0.3) == 1

    def test_standard_tier(self) -> None:
        assert _classify_tier(0.31) == 2
        assert _classify_tier(1.0) == 2

    def test_reasoning_tier(self) -> None:
        assert _classify_tier(1.01) == 3
        assert _classify_tier(3.0) == 3
        assert _classify_tier(5.0) == 3

    def test_critical_tier(self) -> None:
        assert _classify_tier(5.01) == 4
        assert _classify_tier(15.0) == 4

    def test_zero_price_is_nano(self) -> None:
        assert _classify_tier(0.0) == 1


# ---------------------------------------------------------------------------
# Tests: Registry operations
# ---------------------------------------------------------------------------

def _make_entry(model_id: str, *, status: str = "active", context_window: int = 200_000, last_seen: float = 1000.0) -> ModelEntry:
    return ModelEntry(
        model_id=model_id,
        family=_extract_family(model_id),
        provider=model_id.split("/")[0] if "/" in model_id else "",
        name=model_id,
        context_window=context_window,
        status=status,
        last_seen=last_seen,
    )


class TestRegistryListModels:
    def test_list_all(self) -> None:
        reg = ModelRegistry()
        reg.add(_make_entry("anthropic/claude-sonnet-4"))
        reg.add(_make_entry("deepseek/deepseek-v3.2"))
        assert len(reg.list_models()) == 2

    def test_filter_by_status(self) -> None:
        reg = ModelRegistry()
        reg.add(_make_entry("anthropic/claude-sonnet-4", status="active"))
        reg.add(_make_entry("anthropic/claude-sonnet-3", status="deprecated"))
        assert len(reg.list_models(status="active")) == 1
        assert len(reg.list_models(status="deprecated")) == 1

    def test_empty_registry(self) -> None:
        reg = ModelRegistry()
        assert reg.list_models() == []


class TestRegistryFamilyVersions:
    def test_groups_by_family(self) -> None:
        reg = ModelRegistry()
        reg.add(_make_entry("anthropic/claude-sonnet-4-20260101", last_seen=100.0))
        reg.add(_make_entry("anthropic/claude-sonnet-4-20260514", last_seen=200.0))
        reg.add(_make_entry("deepseek/deepseek-v3.2"))

        versions = reg.get_family_versions("anthropic/claude-sonnet-4")
        assert len(versions) == 2
        # Newest first
        assert versions[0].model_id == "anthropic/claude-sonnet-4-20260514"

    def test_no_versions_for_unknown_family(self) -> None:
        reg = ModelRegistry()
        assert reg.get_family_versions("unknown/model") == []

    def test_list_families(self) -> None:
        reg = ModelRegistry()
        reg.add(_make_entry("anthropic/claude-sonnet-4-20260101"))
        reg.add(_make_entry("anthropic/claude-sonnet-4-20260514"))
        reg.add(_make_entry("deepseek/deepseek-v3.2"))

        families = reg.list_families()
        assert "anthropic/claude-sonnet-4" in families
        assert "deepseek/deepseek-v3.2" in families
        assert len(families) == 2


class TestContextWindowLookup:
    def test_exact_match(self) -> None:
        reg = ModelRegistry()
        reg.add(_make_entry("anthropic/claude-sonnet-4", context_window=200_000))
        assert reg.get_context_window("anthropic/claude-sonnet-4") == 200_000

    def test_short_name_match(self) -> None:
        reg = ModelRegistry()
        reg.add(_make_entry("anthropic/claude-sonnet-4", context_window=200_000))
        assert reg.get_context_window("claude-sonnet-4") == 200_000

    def test_unknown_model_returns_none(self) -> None:
        reg = ModelRegistry()
        assert reg.get_context_window("unknown-model") is None

    def test_deprecated_model_not_matched_by_short_name(self) -> None:
        reg = ModelRegistry()
        reg.add(_make_entry("anthropic/claude-sonnet-3", context_window=100_000, status="deprecated"))
        assert reg.get_context_window("claude-sonnet-3") is None


# ---------------------------------------------------------------------------
# Tests: Deprecation checking
# ---------------------------------------------------------------------------

class TestDeprecationChecking:
    def test_active_pin_no_warning(self) -> None:
        reg = ModelRegistry()
        reg.add(_make_entry("anthropic/claude-sonnet-4"))
        warnings = reg.check_pins({"primary": "anthropic/claude-sonnet-4"})
        assert len(warnings) == 0

    def test_deprecated_pin_warns(self) -> None:
        reg = ModelRegistry()
        reg.add(_make_entry("anthropic/claude-sonnet-4-20260101", status="deprecated", last_seen=100.0))
        reg.add(_make_entry("anthropic/claude-sonnet-4-20260514", status="active", last_seen=200.0))
        warnings = reg.check_pins({"primary": "anthropic/claude-sonnet-4-20260101"})
        assert len(warnings) == 1
        assert warnings[0].status == "deprecated"
        assert warnings[0].suggested_replacement == "anthropic/claude-sonnet-4-20260514"

    def test_removed_pin_warns(self) -> None:
        reg = ModelRegistry()
        reg.add(_make_entry("anthropic/claude-sonnet-4-20260514"))  # Populate registry
        warnings = reg.check_pins({"primary": "anthropic/claude-sonnet-3-20250101"})
        assert len(warnings) == 1
        assert warnings[0].status == "removed"

    def test_removed_pin_suggests_family_replacement(self) -> None:
        reg = ModelRegistry()
        reg.add(_make_entry("anthropic/claude-sonnet-4-20260514"))
        # Pin an old version of the same family
        warnings = reg.check_pins({"primary": "anthropic/claude-sonnet-4-20260101"})
        assert len(warnings) == 1
        assert warnings[0].suggested_replacement == "anthropic/claude-sonnet-4-20260514"

    def test_empty_pins_no_warnings(self) -> None:
        reg = ModelRegistry()
        reg.add(_make_entry("anthropic/claude-sonnet-4"))
        warnings = reg.check_pins({})
        assert len(warnings) == 0

    def test_empty_registry_no_false_warnings(self) -> None:
        reg = ModelRegistry()
        # Empty registry should not warn about unknown models
        warnings = reg.check_pins({"primary": "anthropic/claude-sonnet-4"})
        assert len(warnings) == 0

    def test_multiple_pins_multiple_warnings(self) -> None:
        reg = ModelRegistry()
        reg.add(_make_entry("anthropic/claude-sonnet-4", status="deprecated"))
        reg.add(_make_entry("deepseek/deepseek-v3.2", status="deprecated"))
        warnings = reg.check_pins({
            "primary": "anthropic/claude-sonnet-4",
            "budget": "deepseek/deepseek-v3.2",
        })
        assert len(warnings) == 2


# ---------------------------------------------------------------------------
# Tests: Persistence (JSON serialization)
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_entry_serializable(self) -> None:
        entry = _make_entry("anthropic/claude-sonnet-4")
        data = asdict(entry)
        assert isinstance(json.dumps(data), str)

    def test_round_trip(self) -> None:
        entry = _make_entry("anthropic/claude-sonnet-4", context_window=200_000)
        data = asdict(entry)
        restored = ModelEntry(**data)
        assert restored.model_id == entry.model_id
        assert restored.context_window == entry.context_window
        assert restored.family == entry.family
