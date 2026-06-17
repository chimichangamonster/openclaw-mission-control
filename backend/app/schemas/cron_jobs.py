"""Schemas for cron job CRUD endpoints.

This module is intentionally free of DB / psycopg imports so the gateway-RPC
param builders below (``build_add_params`` / ``build_update_params``) can be
imported and unit-tested directly. The API layer (``app.api.cron_jobs``) is the
only caller; tests exercise the REAL functions, not a copy — a duplicated copy
is what let the 2026.5.2 ``cron.update`` schema drift ship undetected.
"""

from __future__ import annotations

from typing import Any, Literal

from sqlmodel import SQLModel

from app.schemas.common import NonEmptyStr


class CronJobCreate(SQLModel):
    """Payload for creating a cron job via gateway RPC."""

    name: NonEmptyStr
    agent_id: NonEmptyStr
    schedule_type: Literal["cron", "every", "at"]
    schedule_expr: NonEmptyStr
    timezone: str = "America/Edmonton"
    message: str = ""
    thinking: str = ""
    timeout_seconds: int = 300
    session_target: str = "isolated"
    announce: bool = False
    enabled: bool = True
    description: str = ""


class CronJobUpdate(SQLModel):
    """Payload for updating a cron job (all fields optional)."""

    name: str | None = None
    agent_id: str | None = None
    schedule_type: Literal["cron", "every", "at"] | None = None
    schedule_expr: str | None = None
    timezone: str | None = None
    message: str | None = None
    thinking: str | None = None
    timeout_seconds: int | None = None
    session_target: str | None = None
    announce: bool | None = None
    enabled: bool | None = None
    description: str | None = None


class CronRunRecord(SQLModel):
    """A single cron job run from gateway history."""

    run_id: str = ""
    job_id: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    status: str = ""
    error: str | None = None
    duration_ms: int | None = None


# ---------------------------------------------------------------------------
# Gateway RPC param builders (pure mapping — no DB, unit-tested directly)
# ---------------------------------------------------------------------------


def build_add_params(payload: CronJobCreate) -> dict[str, Any]:
    """Map a CronJobCreate schema to the gateway ``cron.add`` RPC params.

    Note: ``cron.add`` does NOT accept a client-supplied ``id`` — the gateway
    assigns the UUID (item 42 regression).
    """
    schedule: dict[str, Any] = {"kind": payload.schedule_type}
    if payload.schedule_type == "cron":
        schedule["expr"] = payload.schedule_expr
    elif payload.schedule_type == "every":
        schedule["every"] = payload.schedule_expr
    elif payload.schedule_type == "at":
        schedule["at"] = payload.schedule_expr
    schedule["tz"] = payload.timezone

    params: dict[str, Any] = {
        "name": payload.name,
        "agentId": payload.agent_id,
        "enabled": payload.enabled,
        "schedule": schedule,
        "payload": {"message": payload.message},
        "sessionTarget": payload.session_target,
        # delivery.mode enum is announce|webhook|none — NEVER 'silent' (item 42).
        "delivery": {"mode": "announce" if payload.announce else "none"},
    }
    if payload.description:
        params["description"] = payload.description
    if payload.thinking:
        params["payload"]["thinking"] = payload.thinking
    if payload.timeout_seconds:
        params["payload"]["timeoutSeconds"] = payload.timeout_seconds
    return params


def build_update_params(job_id: str, payload: CronJobUpdate) -> dict[str, Any]:
    """Map a CronJobUpdate schema to the gateway ``cron.update`` RPC params.

    OpenClaw 2026.5.2 changed the ``cron.update`` schema from the flat
    ``{id, payload, schedule, ...}`` shape to ``{jobId, patch:{...}}``. Sending
    the old shape returns ``invalid cron.update params: must have required
    property 'patch' / 'jobId'`` and 502s — this silently broke the /cron-jobs
    UI's edit + enable/disable toggle from the 2026-06-09 fleet upgrade until
    fixed 2026-06-17. ``cron.add``/``run``/``runs``/``remove`` still take ``id``.
    """
    patch: dict[str, Any] = {}

    if payload.name is not None:
        patch["name"] = payload.name
    if payload.description is not None:
        patch["description"] = payload.description
    if payload.agent_id is not None:
        patch["agentId"] = payload.agent_id
    if payload.enabled is not None:
        patch["enabled"] = payload.enabled
    if payload.session_target is not None:
        patch["sessionTarget"] = payload.session_target

    # Schedule fields — only include if any schedule field changed.
    if any(v is not None for v in [payload.schedule_type, payload.schedule_expr, payload.timezone]):
        schedule: dict[str, Any] = {}
        if payload.schedule_type is not None:
            schedule["kind"] = payload.schedule_type
            expr = payload.schedule_expr
            if expr is not None:
                if payload.schedule_type == "cron":
                    schedule["expr"] = expr
                elif payload.schedule_type == "every":
                    schedule["every"] = expr
                elif payload.schedule_type == "at":
                    schedule["at"] = expr
        elif payload.schedule_expr is not None:
            # Expression changed but type didn't — use generic expr key.
            schedule["expr"] = payload.schedule_expr
        if payload.timezone is not None:
            schedule["tz"] = payload.timezone
        patch["schedule"] = schedule

    # Payload fields.
    payload_update: dict[str, Any] = {}
    if payload.message is not None:
        payload_update["message"] = payload.message
    if payload.thinking is not None:
        payload_update["thinking"] = payload.thinking
    if payload.timeout_seconds is not None:
        payload_update["timeoutSeconds"] = payload.timeout_seconds
    if payload_update:
        patch["payload"] = payload_update

    # Delivery — enum is announce|webhook|none, never 'silent' (item 42).
    if payload.announce is not None:
        patch["delivery"] = {"mode": "announce" if payload.announce else "none"}

    return {"jobId": job_id, "patch": patch}
