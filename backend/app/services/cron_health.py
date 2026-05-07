"""Cron health scan for /api/v1/system/health.

Walks per-org gateway workspaces under ``GATEWAY_WORKSPACES_ROOT`` and aggregates
counts of cron jobs and their last-run status.

Disabled jobs (``enabled: False``) are excluded from the failed count: a disabled
job's stale ``lastRunStatus: error`` is operator-acknowledged history, not a live
alert. Without this guard, a once-failed cron that the operator deliberately
disabled keeps ``/system/health`` permanently flagged as degraded — exactly what
happened with ``ecosystem-intel-verify`` on 2026-05-07.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

_FAILURE_STATUSES = ("error", "failed")


def _job_last_status(job: Any) -> str | None:
    """Extract last-run status from a job dict, supporting both modern and legacy shapes."""
    if not isinstance(job, dict):
        return None
    raw_state = job.get("state")
    state: dict[str, Any] = raw_state if isinstance(raw_state, dict) else {}
    last_status = state.get("lastRunStatus")
    if last_status is None:
        last_status = job.get("last_status")
    return last_status if isinstance(last_status, str) else None


def _job_is_enabled(job: Any) -> bool:
    """Return whether the job should count toward the failed total. Missing key → enabled."""
    if not isinstance(job, dict):
        return False
    flag = job.get("enabled", True)
    return bool(flag)


def scan_cron_health(workspaces_root: str | None = None) -> dict[str, Any]:
    """Aggregate cron health across all per-org gateway workspaces.

    Args:
        workspaces_root: Path to the gateway workspaces parent dir. If ``None``,
            falls back to the ``GATEWAY_WORKSPACES_ROOT`` env var. If neither is
            present or the path doesn't exist, returns ``status: "no_data"``.

    Returns:
        A dict with keys ``status`` (``ok`` | ``failing`` | ``no_data``),
        ``failed``, ``total``, ``gateways_scanned``.
    """
    root_str = workspaces_root or os.environ.get("GATEWAY_WORKSPACES_ROOT")
    if not root_str:
        return {"status": "no_data", "failed": 0, "total": 0, "gateways_scanned": 0}

    root = Path(root_str)
    if not root.exists():
        return {"status": "no_data", "failed": 0, "total": 0, "gateways_scanned": 0}

    failed = 0
    total = 0
    gateways_scanned = 0

    for org_dir in root.iterdir():
        if not org_dir.is_dir():
            continue
        jobs_file = org_dir / ".openclaw" / "cron" / "jobs.json"
        if not jobs_file.exists():
            continue

        try:
            data = json.loads(jobs_file.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("cron_health.read_failed path=%s error=%s", jobs_file, exc)
            continue

        if isinstance(data, dict) and "jobs" in data:
            jobs = data["jobs"]
        else:
            jobs = data
        if not isinstance(jobs, list):
            continue

        gateways_scanned += 1
        total += len(jobs)
        for job in jobs:
            if not _job_is_enabled(job):
                continue
            last_status = _job_last_status(job)
            if last_status in _FAILURE_STATUSES:
                failed += 1

    if gateways_scanned == 0:
        return {"status": "no_data", "failed": 0, "total": 0, "gateways_scanned": 0}

    return {
        "status": "ok" if failed == 0 else "failing",
        "failed": failed,
        "total": total,
        "gateways_scanned": gateways_scanned,
    }
