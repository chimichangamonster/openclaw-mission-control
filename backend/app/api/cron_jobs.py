"""Cron jobs API — reads gateway cron config, manages via gateway WS."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from app.api.deps import ORG_RATE_LIMIT_DEP, require_feature, require_org_member, require_org_role
from app.core.logging import get_logger
from app.core.workspace import resolve_org_workspace
from app.db.session import async_session_maker
from app.models.gateways import Gateway
from app.schemas.cron_jobs import CronJobCreate, CronJobUpdate
from app.services.openclaw.gateway_resolver import gateway_client_config
from app.services.openclaw.gateway_rpc import (
    GatewayConfig,
    OpenClawGatewayError,
    openclaw_call,
)
from app.services.organizations import OrganizationContext

logger = get_logger(__name__)
router = APIRouter(
    prefix="/cron-jobs",
    tags=["cron-jobs"],
    dependencies=[Depends(require_feature("cron_jobs")), ORG_RATE_LIMIT_DEP],
)

_OPERATOR_DEP = Depends(require_org_role("operator"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_cron_file(org_ctx: OrganizationContext) -> Path:
    """Resolve the cron jobs.json path for the current org.

    Legacy single-tenant fallback (LEGACY_CRON_JOBS_FILE) retired 2026-04-11 —
    per-org gateways are the only source of truth.
    """
    workspace = resolve_org_workspace(org_ctx.organization)
    # cron/ is a sibling of workspace/ inside .openclaw/
    return workspace.parent / "cron" / "jobs.json"


def _read_jobs(cron_file: Path) -> list[dict]:
    """Read cron jobs from a gateway's jobs.json file."""
    if not cron_file.exists():
        return []
    try:
        data = json.loads(cron_file.read_text())
        if isinstance(data, dict) and "jobs" in data:
            return data["jobs"]
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("cron.read_failed", extra={"error": str(exc), "path": str(cron_file)})
        return []


def _normalize_job(j: dict) -> dict:
    """Normalize a raw gateway job dict into the API response shape."""
    schedule = j.get("schedule", {})
    state = j.get("state", {})
    payload = j.get("payload", {})
    delivery = j.get("delivery", {})

    next_run_ms = state.get("nextRunAtMs")
    last_run_ms = state.get("lastRunAtMs")

    return {
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
        "next_run": (
            datetime.fromtimestamp(next_run_ms / 1000, tz=UTC).isoformat() if next_run_ms else None
        ),
        "last_run": (
            datetime.fromtimestamp(last_run_ms / 1000, tz=UTC).isoformat() if last_run_ms else None
        ),
        "last_status": state.get("lastRunStatus", None),
        "created_at": datetime.fromtimestamp(j.get("createdAtMs", 0) / 1000, tz=UTC).isoformat(),
    }


async def _get_gateway_config(org_ctx: OrganizationContext) -> GatewayConfig:
    """Resolve the gateway RPC config for the current org."""
    async with async_session_maker() as db_session:
        result = await db_session.execute(
            select(Gateway).where(Gateway.organization_id == org_ctx.organization.id).limit(1)
        )
        gateway = result.scalars().first()

    if not gateway or not gateway.url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No gateway configured for this organization",
        )
    return gateway_client_config(gateway)


async def _rpc_call(method: str, params: dict[str, Any] | None, config: GatewayConfig) -> Any:
    """Call a gateway cron RPC method with standard error handling."""
    try:
        return await openclaw_call(method, params, config=config)
    except OpenClawGatewayError as exc:
        logger.warning("cron.rpc_failed", extra={"method": method, "error": str(exc)})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


def _build_add_params(payload: CronJobCreate) -> dict[str, Any]:
    """Map a CronJobCreate schema to the gateway cron.add RPC params."""
    schedule: dict[str, Any] = {"kind": payload.schedule_type}
    if payload.schedule_type == "cron":
        schedule["expr"] = payload.schedule_expr
    elif payload.schedule_type == "every":
        schedule["every"] = payload.schedule_expr
    elif payload.schedule_type == "at":
        schedule["at"] = payload.schedule_expr
    schedule["tz"] = payload.timezone

    params: dict[str, Any] = {
        "id": str(uuid4()),
        "name": payload.name,
        "agentId": payload.agent_id,
        "enabled": payload.enabled,
        "schedule": schedule,
        "payload": {
            "message": payload.message,
        },
        "sessionTarget": payload.session_target,
        "delivery": {"mode": "announce" if payload.announce else "silent"},
    }
    if payload.description:
        params["description"] = payload.description
    if payload.thinking:
        params["payload"]["thinking"] = payload.thinking
    if payload.timeout_seconds:
        params["payload"]["timeoutSeconds"] = payload.timeout_seconds
    return params


def _build_update_params(job_id: str, payload: CronJobUpdate) -> dict[str, Any]:
    """Map a CronJobUpdate schema to the gateway cron.update RPC params."""
    params: dict[str, Any] = {"id": job_id}

    if payload.name is not None:
        params["name"] = payload.name
    if payload.description is not None:
        params["description"] = payload.description
    if payload.agent_id is not None:
        params["agentId"] = payload.agent_id
    if payload.enabled is not None:
        params["enabled"] = payload.enabled
    if payload.session_target is not None:
        params["sessionTarget"] = payload.session_target

    # Schedule fields — only include if any schedule field changed
    if any(v is not None for v in [payload.schedule_type, payload.schedule_expr, payload.timezone]):
        schedule: dict[str, Any] = {}
        if payload.schedule_type is not None:
            schedule["kind"] = payload.schedule_type
            # Set the correct key for the expression
            expr = payload.schedule_expr
            if expr is not None:
                if payload.schedule_type == "cron":
                    schedule["expr"] = expr
                elif payload.schedule_type == "every":
                    schedule["every"] = expr
                elif payload.schedule_type == "at":
                    schedule["at"] = expr
        elif payload.schedule_expr is not None:
            # Expression changed but type didn't — use generic expr key
            schedule["expr"] = payload.schedule_expr
        if payload.timezone is not None:
            schedule["tz"] = payload.timezone
        params["schedule"] = schedule

    # Payload fields
    payload_update: dict[str, Any] = {}
    if payload.message is not None:
        payload_update["message"] = payload.message
    if payload.thinking is not None:
        payload_update["thinking"] = payload.thinking
    if payload.timeout_seconds is not None:
        payload_update["timeoutSeconds"] = payload.timeout_seconds
    if payload_update:
        params["payload"] = payload_update

    # Delivery
    if payload.announce is not None:
        params["delivery"] = {"mode": "announce" if payload.announce else "silent"}

    return params


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_cron_jobs(
    org_ctx: OrganizationContext = Depends(require_org_member),
) -> list[dict]:
    """List cron jobs for the current organization's gateway.

    Tries gateway RPC first for fresh data; falls back to reading jobs.json
    from disk if the gateway is unreachable.
    """
    try:
        config = await _get_gateway_config(org_ctx)
        rpc_result = await _rpc_call("cron.list", None, config)
        # Gateway returns a list of job dicts or {"jobs": [...]}
        if isinstance(rpc_result, dict) and "jobs" in rpc_result:
            jobs = rpc_result["jobs"]
        elif isinstance(rpc_result, list):
            jobs = rpc_result
        else:
            jobs = []
        return [_normalize_job(j) for j in jobs]
    except HTTPException:
        # Gateway unavailable — fall back to file read
        logger.info("cron.list_fallback_to_file")
        cron_file = _resolve_cron_file(org_ctx)
        jobs = _read_jobs(cron_file)
        return [_normalize_job(j) for j in jobs]


@router.post("", dependencies=[_OPERATOR_DEP], status_code=status.HTTP_201_CREATED)
async def create_cron_job(
    payload: CronJobCreate,
    org_ctx: OrganizationContext = Depends(require_org_member),
) -> dict:
    """Create a new cron job via the gateway."""
    config = await _get_gateway_config(org_ctx)
    params = _build_add_params(payload)
    result = await _rpc_call("cron.add", params, config)
    return result if isinstance(result, dict) else {"ok": True, "id": params["id"]}


@router.patch("/{job_id}", dependencies=[_OPERATOR_DEP])
async def update_cron_job(
    job_id: str,
    payload: CronJobUpdate,
    org_ctx: OrganizationContext = Depends(require_org_member),
) -> dict:
    """Update an existing cron job via the gateway."""
    config = await _get_gateway_config(org_ctx)
    params = _build_update_params(job_id, payload)
    result = await _rpc_call("cron.update", params, config)
    return result if isinstance(result, dict) else {"ok": True}


@router.delete("/{job_id}", dependencies=[_OPERATOR_DEP], status_code=status.HTTP_204_NO_CONTENT)
async def delete_cron_job(
    job_id: str,
    org_ctx: OrganizationContext = Depends(require_org_member),
) -> None:
    """Remove a cron job via the gateway."""
    config = await _get_gateway_config(org_ctx)
    await _rpc_call("cron.remove", {"id": job_id}, config)


@router.post("/{job_id}/run", dependencies=[_OPERATOR_DEP])
async def run_cron_job(
    job_id: str,
    org_ctx: OrganizationContext = Depends(require_org_member),
) -> dict:
    """Manually trigger a cron job to run immediately."""
    config = await _get_gateway_config(org_ctx)
    result = await _rpc_call("cron.run", {"id": job_id}, config)
    return result if isinstance(result, dict) else {"ok": True}


@router.get("/{job_id}/runs")
async def get_cron_job_runs(
    job_id: str,
    org_ctx: OrganizationContext = Depends(require_org_member),
) -> list[dict]:
    """Get run history for a cron job."""
    config = await _get_gateway_config(org_ctx)
    result = await _rpc_call("cron.runs", {"id": job_id}, config)
    if isinstance(result, list):
        return result
    if isinstance(result, dict) and "runs" in result:
        return result["runs"]
    return []
