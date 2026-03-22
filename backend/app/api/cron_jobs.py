"""Cron jobs API — reads gateway cron config, manages via gateway WS."""

from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import ORG_RATE_LIMIT_DEP, require_feature, require_org_member
from app.core.logging import get_logger
from app.services.organizations import OrganizationContext

logger = get_logger(__name__)
router = APIRouter(
    prefix="/cron-jobs",
    tags=["cron-jobs"],
    dependencies=[Depends(require_feature("cron_jobs")), ORG_RATE_LIMIT_DEP],
)

CRON_JOBS_FILE = Path("/app/gateway-cron/jobs.json")


def _read_jobs() -> list[dict]:
    """Read cron jobs from the gateway's jobs.json file."""
    if not CRON_JOBS_FILE.exists():
        return []
    try:
        data = json.loads(CRON_JOBS_FILE.read_text())
        if isinstance(data, dict) and "jobs" in data:
            return data["jobs"]
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("cron.read_failed", extra={"error": str(exc)})
        return []


@router.get("")
async def list_cron_jobs(
    org_ctx: OrganizationContext = Depends(require_org_member),
) -> list[dict]:
    """List all cron jobs from the gateway."""
    jobs = _read_jobs()
    out = []
    for j in jobs:
        schedule = j.get("schedule", {})
        state = j.get("state", {})
        payload = j.get("payload", {})
        delivery = j.get("delivery", {})

        next_run_ms = state.get("nextRunAtMs")
        last_run_ms = state.get("lastRunAtMs")

        out.append({
            "id": j.get("id", ""),
            "name": j.get("name", ""),
            "description": j.get("description", ""),
            "agent_id": j.get("agentId", ""),
            "enabled": j.get("enabled", False),
            "schedule_type": schedule.get("kind", ""),
            "schedule_expr": schedule.get("expr", schedule.get("every", schedule.get("at", ""))),
            "timezone": schedule.get("tz", "UTC"),
            "message": payload.get("message", ""),
            "thinking": payload.get("thinking", ""),
            "timeout_seconds": payload.get("timeoutSeconds", 0),
            "session_target": j.get("sessionTarget", ""),
            "announce": delivery.get("mode") == "announce",
            "next_run": datetime.fromtimestamp(next_run_ms / 1000, tz=UTC).isoformat() if next_run_ms else None,
            "last_run": datetime.fromtimestamp(last_run_ms / 1000, tz=UTC).isoformat() if last_run_ms else None,
            "last_status": state.get("lastRunStatus", None),
            "created_at": datetime.fromtimestamp(j.get("createdAtMs", 0) / 1000, tz=UTC).isoformat(),
        })
    return out
