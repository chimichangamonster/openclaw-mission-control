# ruff: noqa: INP001
"""Unit tests for app.services.cron_health.scan_cron_health.

The scanner walks per-org gateway workspaces under GATEWAY_WORKSPACES_ROOT/*/.openclaw/cron/jobs.json
and aggregates `failed` / `total` / `gateways_scanned`. Disabled jobs are excluded from `failed`
because a disabled job's stale `lastRunStatus: error` is operator-acknowledged history, not a
live alert.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.cron_health import scan_cron_health


def _write_jobs(workspaces_root: Path, slug: str, jobs: list[dict[str, Any]]) -> None:
    cron_dir = workspaces_root / slug / ".openclaw" / "cron"
    cron_dir.mkdir(parents=True, exist_ok=True)
    (cron_dir / "jobs.json").write_text(json.dumps({"version": 1, "jobs": jobs}))


def _job(name: str, last_status: str, *, enabled: bool = True) -> dict[str, Any]:
    return {
        "id": name,
        "name": name,
        "enabled": enabled,
        "state": {"lastRunStatus": last_status},
    }


class TestScanCronHealth:
    def test_no_workspaces_root_returns_no_data(self, tmp_path: Path) -> None:
        result = scan_cron_health(workspaces_root=None)
        assert result == {"status": "no_data", "failed": 0, "total": 0, "gateways_scanned": 0}

    def test_missing_workspaces_root_returns_no_data(self, tmp_path: Path) -> None:
        result = scan_cron_health(workspaces_root=str(tmp_path / "does-not-exist"))
        assert result["status"] == "no_data"

    def test_empty_workspaces_root_returns_no_data(self, tmp_path: Path) -> None:
        result = scan_cron_health(workspaces_root=str(tmp_path))
        assert result["status"] == "no_data"
        assert result["gateways_scanned"] == 0

    def test_all_ok_returns_status_ok(self, tmp_path: Path) -> None:
        _write_jobs(tmp_path, "vantage", [_job("a", "ok"), _job("b", "ok")])
        result = scan_cron_health(workspaces_root=str(tmp_path))
        assert result["status"] == "ok"
        assert result["failed"] == 0
        assert result["total"] == 2
        assert result["gateways_scanned"] == 1

    def test_enabled_error_counts_as_failed(self, tmp_path: Path) -> None:
        _write_jobs(tmp_path, "vantage", [_job("a", "ok"), _job("bad", "error")])
        result = scan_cron_health(workspaces_root=str(tmp_path))
        assert result["status"] == "failing"
        assert result["failed"] == 1
        assert result["total"] == 2

    def test_disabled_error_does_not_count(self, tmp_path: Path) -> None:
        """The bug fix — a disabled job's stale `lastRunStatus: error` must be ignored.

        Replays the 2026-05-07 ecosystem-intel-verify situation: the cron was disabled,
        but its prior error state kept /system/health flagged as degraded forever.
        """
        _write_jobs(
            tmp_path,
            "vantage",
            [_job("ok-job", "ok"), _job("disabled-old-error", "error", enabled=False)],
        )
        result = scan_cron_health(workspaces_root=str(tmp_path))
        assert result["status"] == "ok"
        assert result["failed"] == 0
        assert result["total"] == 2  # total still counts disabled jobs

    def test_disabled_default_to_enabled_when_field_missing(self, tmp_path: Path) -> None:
        """If `enabled` key is missing, treat as enabled (backwards-compat)."""
        job_no_flag = {"id": "x", "name": "x", "state": {"lastRunStatus": "error"}}
        _write_jobs(tmp_path, "vantage", [job_no_flag])
        result = scan_cron_health(workspaces_root=str(tmp_path))
        assert result["failed"] == 1

    def test_failed_status_alias_also_counts(self, tmp_path: Path) -> None:
        """Some gateway versions write `failed` instead of `error` — both must count."""
        _write_jobs(tmp_path, "vantage", [_job("a", "failed")])
        result = scan_cron_health(workspaces_root=str(tmp_path))
        assert result["failed"] == 1

    def test_legacy_last_status_field(self, tmp_path: Path) -> None:
        """Old job format used top-level `last_status` instead of `state.lastRunStatus`."""
        legacy = {"id": "x", "name": "x", "enabled": True, "last_status": "error"}
        _write_jobs(tmp_path, "vantage", [legacy])
        result = scan_cron_health(workspaces_root=str(tmp_path))
        assert result["failed"] == 1

    def test_legacy_last_status_respects_disabled(self, tmp_path: Path) -> None:
        legacy = {"id": "x", "name": "x", "enabled": False, "last_status": "error"}
        _write_jobs(tmp_path, "vantage", [legacy])
        result = scan_cron_health(workspaces_root=str(tmp_path))
        assert result["failed"] == 0

    def test_multiple_gateways_aggregate(self, tmp_path: Path) -> None:
        _write_jobs(tmp_path, "vantage", [_job("a", "ok"), _job("b", "error")])
        _write_jobs(tmp_path, "personal", [_job("c", "ok"), _job("d", "ok")])
        _write_jobs(
            tmp_path,
            "magnetik",
            [_job("e", "error", enabled=False), _job("f", "error")],
        )
        result = scan_cron_health(workspaces_root=str(tmp_path))
        assert result["gateways_scanned"] == 3
        assert result["total"] == 6
        assert result["failed"] == 2  # b + f, NOT the disabled e
        assert result["status"] == "failing"

    def test_malformed_jobs_json_skips_gateway(self, tmp_path: Path) -> None:
        _write_jobs(tmp_path, "good", [_job("a", "ok")])
        bad_dir = tmp_path / "broken" / ".openclaw" / "cron"
        bad_dir.mkdir(parents=True)
        (bad_dir / "jobs.json").write_text("{not valid json")
        result = scan_cron_health(workspaces_root=str(tmp_path))
        assert result["gateways_scanned"] == 1
        assert result["total"] == 1
        assert result["failed"] == 0

    def test_jobs_json_top_level_list_supported(self, tmp_path: Path) -> None:
        """Some old gateway versions wrote a bare list instead of {version, jobs}."""
        cron_dir = tmp_path / "vantage" / ".openclaw" / "cron"
        cron_dir.mkdir(parents=True)
        (cron_dir / "jobs.json").write_text(json.dumps([_job("a", "error")]))
        result = scan_cron_health(workspaces_root=str(tmp_path))
        assert result["failed"] == 1
        assert result["total"] == 1

    def test_org_dir_without_jobs_file_is_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "no-cron").mkdir()
        _write_jobs(tmp_path, "vantage", [_job("a", "ok")])
        result = scan_cron_health(workspaces_root=str(tmp_path))
        assert result["gateways_scanned"] == 1
