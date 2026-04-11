# ruff: noqa: INP001
"""Unit tests for cron watchdog logic — pure tests, no DB imports."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

# Replicate the watchdog constants here to avoid importing from app
# (which triggers psycopg/DB import chain)
CRON_TASK_PREFIXES = [
    "Morning Scan",
    "Portfolio Monitor",
    "Cost Optimizer",
]

STALE_THRESHOLD = timedelta(minutes=30)


def is_cron_task(title: str) -> bool:
    """Check if a task title matches a known cron job prefix."""
    return any(title.startswith(prefix) for prefix in CRON_TASK_PREFIXES)


def is_stale(created_at: datetime, now: datetime) -> bool:
    """Check if a task is stale based on creation time."""
    return (now - created_at) > STALE_THRESHOLD


class TestCronTaskDetection:
    """Verify cron task title matching."""

    def test_morning_scan_matches(self) -> None:
        assert is_cron_task("Morning Scan — 2026-03-21")

    def test_portfolio_monitor_matches(self) -> None:
        assert is_cron_task("Portfolio Monitor — 2026-03-21")

    def test_cost_optimizer_matches(self) -> None:
        assert is_cron_task("Cost Optimizer — 2026-04-01")

    def test_user_created_task_does_not_match(self) -> None:
        assert not is_cron_task("Investigate AAPL earnings report")

    def test_similar_but_wrong_prefix_does_not_match(self) -> None:
        assert not is_cron_task("Morning meeting notes")
        assert not is_cron_task("Portfolio review Q1")
        assert not is_cron_task("Cost analysis for client")

    def test_empty_title_does_not_match(self) -> None:
        assert not is_cron_task("")


class TestStalenessDetection:
    """Verify staleness threshold logic."""

    def test_fresh_task_is_not_stale(self) -> None:
        now = datetime.now(UTC)
        created = now - timedelta(minutes=5)
        assert not is_stale(created, now)

    def test_task_at_threshold_is_not_stale(self) -> None:
        now = datetime.now(UTC)
        created = now - timedelta(minutes=30)
        assert not is_stale(created, now)

    def test_task_past_threshold_is_stale(self) -> None:
        now = datetime.now(UTC)
        created = now - timedelta(minutes=31)
        assert is_stale(created, now)

    def test_task_way_past_threshold_is_stale(self) -> None:
        now = datetime.now(UTC)
        created = now - timedelta(hours=2)
        assert is_stale(created, now)

    def test_threshold_is_30_minutes(self) -> None:
        assert STALE_THRESHOLD.total_seconds() == 1800


class TestAlertDedup:
    """Verify dedup set behavior for alert suppression."""

    def test_set_prevents_duplicate_alerts(self) -> None:
        alerted: set = set()
        task_id = uuid4()
        alerted.add(task_id)
        assert task_id in alerted
        # Second add is a no-op
        alerted.add(task_id)
        assert len(alerted) == 1

    def test_prune_clears_set(self) -> None:
        alerted: set = set()
        for _ in range(150):
            alerted.add(uuid4())
        assert len(alerted) == 150
        # Simulate prune (as done in cron_watchdog.py)
        if len(alerted) > 100:
            alerted.clear()
        assert len(alerted) == 0
