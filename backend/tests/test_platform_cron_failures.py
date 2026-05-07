# ruff: noqa: INP001
"""Tests for /platform/cron-failures rollup helpers — pure tests, no DB imports.

Mirrors the test_cron_jobs_api.py / test_platform_roles.py pattern: re-implement
the helpers locally to dodge the psycopg/DB import chain.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


def _parse_iso_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _summarize_error(error: Any, max_length: int = 200) -> str:
    if not error:
        return ""
    text = str(error).strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def _filter_failed_runs(
    runs: list[dict[str, Any]], cutoff: datetime
) -> list[dict[str, Any]]:
    failures = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        if run.get("status") != "error":
            continue
        started = _parse_iso_timestamp(run.get("started_at"))
        if started is None or started < cutoff:
            continue
        failures.append(
            {
                "run_id": run.get("run_id", ""),
                "started_at": run.get("started_at"),
                "duration_ms": run.get("duration_ms"),
                "error_summary": _summarize_error(run.get("error")),
            }
        )
    return failures


# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------


class TestParseIsoTimestamp:
    def test_iso_string_with_timezone(self) -> None:
        result = _parse_iso_timestamp("2026-05-07T10:30:00+00:00")
        assert result is not None
        assert result.year == 2026
        assert result.tzinfo is not None

    def test_iso_string_with_z_suffix(self) -> None:
        result = _parse_iso_timestamp("2026-05-07T10:30:00Z")
        assert result is not None
        assert result.tzinfo is not None

    def test_epoch_milliseconds(self) -> None:
        # 2026-01-01 00:00:00 UTC
        result = _parse_iso_timestamp(1767225600000)
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 1

    def test_none_returns_none(self) -> None:
        assert _parse_iso_timestamp(None) is None

    def test_garbage_string_returns_none(self) -> None:
        assert _parse_iso_timestamp("not a date") is None

    def test_empty_string_returns_none(self) -> None:
        assert _parse_iso_timestamp("") is None


# ---------------------------------------------------------------------------
# Error summary truncation
# ---------------------------------------------------------------------------


class TestSummarizeError:
    def test_short_error_passes_through(self) -> None:
        assert _summarize_error("Connection refused") == "Connection refused"

    def test_strips_whitespace(self) -> None:
        assert _summarize_error("  Connection refused  ") == "Connection refused"

    def test_truncates_long_error(self) -> None:
        long_error = "x" * 300
        result = _summarize_error(long_error, max_length=50)
        assert len(result) == 50
        assert result.endswith("…")

    def test_empty_returns_empty(self) -> None:
        assert _summarize_error("") == ""
        assert _summarize_error(None) == ""

    def test_non_string_coerced(self) -> None:
        # Gateway sometimes returns non-string error field
        assert _summarize_error(42) == "42"


# ---------------------------------------------------------------------------
# Failed-run filtering — the load-bearing logic
# ---------------------------------------------------------------------------


class TestFilterFailedRuns:
    def test_keeps_recent_error_runs(self) -> None:
        cutoff = datetime(2026, 5, 7, 0, 0, 0, tzinfo=UTC)
        runs = [
            {
                "run_id": "r1",
                "status": "error",
                "started_at": "2026-05-07T10:00:00+00:00",
                "duration_ms": 1500,
                "error": "Timeout",
            }
        ]
        result = _filter_failed_runs(runs, cutoff)
        assert len(result) == 1
        assert result[0]["run_id"] == "r1"
        assert result[0]["error_summary"] == "Timeout"

    def test_drops_success_runs(self) -> None:
        cutoff = datetime(2026, 5, 7, 0, 0, 0, tzinfo=UTC)
        runs = [
            {
                "run_id": "r1",
                "status": "success",
                "started_at": "2026-05-07T10:00:00+00:00",
            }
        ]
        assert _filter_failed_runs(runs, cutoff) == []

    def test_drops_old_error_runs(self) -> None:
        cutoff = datetime(2026, 5, 7, 0, 0, 0, tzinfo=UTC)
        runs = [
            {
                "run_id": "r1",
                "status": "error",
                "started_at": "2026-05-01T10:00:00+00:00",  # Before cutoff
                "error": "Old failure",
            }
        ]
        assert _filter_failed_runs(runs, cutoff) == []

    def test_drops_runs_with_no_started_at(self) -> None:
        cutoff = datetime(2026, 5, 7, 0, 0, 0, tzinfo=UTC)
        runs = [
            {"run_id": "r1", "status": "error", "started_at": None, "error": "x"}
        ]
        assert _filter_failed_runs(runs, cutoff) == []

    def test_drops_non_dict_entries(self) -> None:
        cutoff = datetime(2026, 5, 7, 0, 0, 0, tzinfo=UTC)
        runs = ["not a dict", None, 42]  # type: ignore[list-item]
        assert _filter_failed_runs(runs, cutoff) == []  # type: ignore[arg-type]

    def test_window_boundary_inclusive_after_cutoff(self) -> None:
        cutoff = datetime(2026, 5, 7, 0, 0, 0, tzinfo=UTC)
        # One second after cutoff — must be kept.
        runs = [
            {
                "run_id": "r1",
                "status": "error",
                "started_at": (cutoff + timedelta(seconds=1)).isoformat(),
                "error": "x",
            }
        ]
        assert len(_filter_failed_runs(runs, cutoff)) == 1

    def test_window_boundary_excludes_before_cutoff(self) -> None:
        cutoff = datetime(2026, 5, 7, 0, 0, 0, tzinfo=UTC)
        runs = [
            {
                "run_id": "r1",
                "status": "error",
                "started_at": (cutoff - timedelta(seconds=1)).isoformat(),
                "error": "x",
            }
        ]
        assert _filter_failed_runs(runs, cutoff) == []

    def test_mixed_runs_returns_only_failures(self) -> None:
        cutoff = datetime(2026, 5, 7, 0, 0, 0, tzinfo=UTC)
        runs = [
            {
                "run_id": "r1",
                "status": "success",
                "started_at": "2026-05-07T10:00:00+00:00",
            },
            {
                "run_id": "r2",
                "status": "error",
                "started_at": "2026-05-07T11:00:00+00:00",
                "error": "Boom",
            },
            {
                "run_id": "r3",
                "status": "error",
                "started_at": "2026-05-01T10:00:00+00:00",  # Old failure
                "error": "Old",
            },
        ]
        result = _filter_failed_runs(runs, cutoff)
        assert len(result) == 1
        assert result[0]["run_id"] == "r2"
        assert result[0]["error_summary"] == "Boom"

    def test_preserves_duration_ms(self) -> None:
        cutoff = datetime(2026, 5, 7, 0, 0, 0, tzinfo=UTC)
        runs = [
            {
                "run_id": "r1",
                "status": "error",
                "started_at": "2026-05-07T10:00:00+00:00",
                "duration_ms": 4321,
                "error": "x",
            }
        ]
        result = _filter_failed_runs(runs, cutoff)
        assert result[0]["duration_ms"] == 4321
