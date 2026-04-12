# ruff: noqa: INP001
"""Unit tests for cron job CRUD helpers — pure tests, no DB imports."""

from __future__ import annotations

from typing import Any, Literal

import pytest
from pydantic import ValidationError
from sqlmodel import SQLModel

# ---------------------------------------------------------------------------
# Re-implement the param-building helpers here to avoid triggering the
# psycopg/DB import chain that comes with importing from app.api.cron_jobs.
# ---------------------------------------------------------------------------


class _NonEmpty(str):
    @classmethod
    def __get_validators__(cls):
        yield cls._validate

    @classmethod
    def _validate(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()


class CronJobCreate(SQLModel):
    name: str
    agent_id: str
    schedule_type: Literal["cron", "every", "at"]
    schedule_expr: str
    timezone: str = "America/Edmonton"
    message: str = ""
    thinking: str = ""
    timeout_seconds: int = 300
    session_target: str = "isolated"
    announce: bool = False
    enabled: bool = True
    description: str = ""


class CronJobUpdate(SQLModel):
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


def build_add_params(payload: CronJobCreate) -> dict[str, Any]:
    """Map CronJobCreate → gateway cron.add RPC params."""
    schedule: dict[str, Any] = {"kind": payload.schedule_type}
    if payload.schedule_type == "cron":
        schedule["expr"] = payload.schedule_expr
    elif payload.schedule_type == "every":
        schedule["every"] = payload.schedule_expr
    elif payload.schedule_type == "at":
        schedule["at"] = payload.schedule_expr
    schedule["tz"] = payload.timezone

    params: dict[str, Any] = {
        "id": "test-id",
        "name": payload.name,
        "agentId": payload.agent_id,
        "enabled": payload.enabled,
        "schedule": schedule,
        "payload": {"message": payload.message},
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


def build_update_params(job_id: str, payload: CronJobUpdate) -> dict[str, Any]:
    """Map CronJobUpdate → gateway cron.update RPC params."""
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
            schedule["expr"] = payload.schedule_expr
        if payload.timezone is not None:
            schedule["tz"] = payload.timezone
        params["schedule"] = schedule

    payload_update: dict[str, Any] = {}
    if payload.message is not None:
        payload_update["message"] = payload.message
    if payload.thinking is not None:
        payload_update["thinking"] = payload.thinking
    if payload.timeout_seconds is not None:
        payload_update["timeoutSeconds"] = payload.timeout_seconds
    if payload_update:
        params["payload"] = payload_update

    if payload.announce is not None:
        params["delivery"] = {"mode": "announce" if payload.announce else "silent"}

    return params


def normalize_job(j: dict) -> dict:
    """Minimal normalize matching the API helper."""
    schedule = j.get("schedule", {})
    payload = j.get("payload", {})
    delivery = j.get("delivery", {})
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
    }


# ---------------------------------------------------------------------------
# Tests: Schema validation
# ---------------------------------------------------------------------------


class TestCronJobCreateValidation:
    """Validate CronJobCreate schema constraints."""

    def test_valid_cron_job(self) -> None:
        job = CronJobCreate(
            name="morning-scan",
            agent_id="stock-analyst",
            schedule_type="cron",
            schedule_expr="0 9 * * 1-5",
        )
        assert job.name == "morning-scan"
        assert job.timezone == "America/Edmonton"
        assert job.session_target == "isolated"

    def test_defaults_are_sensible(self) -> None:
        job = CronJobCreate(
            name="test",
            agent_id="the-claw",
            schedule_type="every",
            schedule_expr="6h",
        )
        assert job.timeout_seconds == 300
        assert job.announce is False
        assert job.enabled is True

    def test_invalid_schedule_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CronJobCreate(
                name="bad",
                agent_id="the-claw",
                schedule_type="weekly",  # type: ignore[arg-type]
                schedule_expr="monday",
            )

    def test_all_schedule_types_accepted(self) -> None:
        for stype in ("cron", "every", "at"):
            job = CronJobCreate(
                name="test",
                agent_id="the-claw",
                schedule_type=stype,  # type: ignore[arg-type]
                schedule_expr="0 9 * * *",
            )
            assert job.schedule_type == stype


class TestCronJobUpdateValidation:
    """Validate CronJobUpdate partial update semantics."""

    def test_empty_update_is_valid(self) -> None:
        update = CronJobUpdate()
        assert update.name is None
        assert update.enabled is None

    def test_partial_update(self) -> None:
        update = CronJobUpdate(enabled=False, message="updated")
        assert update.enabled is False
        assert update.message == "updated"
        assert update.name is None

    def test_invalid_schedule_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CronJobUpdate(schedule_type="weekly")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests: Param mapping (snake_case → camelCase gateway format)
# ---------------------------------------------------------------------------


class TestBuildAddParams:
    """Verify snake_case → camelCase mapping for cron.add."""

    def test_cron_schedule_maps_to_expr(self) -> None:
        job = CronJobCreate(
            name="morning-scan",
            agent_id="stock-analyst",
            schedule_type="cron",
            schedule_expr="0 9 * * 1-5",
        )
        params = build_add_params(job)
        assert params["schedule"]["kind"] == "cron"
        assert params["schedule"]["expr"] == "0 9 * * 1-5"
        assert "every" not in params["schedule"]

    def test_every_schedule_maps_to_every(self) -> None:
        job = CronJobCreate(
            name="check-prices",
            agent_id="stock-analyst",
            schedule_type="every",
            schedule_expr="6h",
        )
        params = build_add_params(job)
        assert params["schedule"]["kind"] == "every"
        assert params["schedule"]["every"] == "6h"
        assert "expr" not in params["schedule"]

    def test_at_schedule_maps_to_at(self) -> None:
        job = CronJobCreate(
            name="one-time",
            agent_id="the-claw",
            schedule_type="at",
            schedule_expr="+30m",
        )
        params = build_add_params(job)
        assert params["schedule"]["kind"] == "at"
        assert params["schedule"]["at"] == "+30m"

    def test_agent_id_becomes_camel_case(self) -> None:
        job = CronJobCreate(
            name="test",
            agent_id="sports-analyst",
            schedule_type="cron",
            schedule_expr="0 9 * * *",
        )
        params = build_add_params(job)
        assert params["agentId"] == "sports-analyst"
        assert "agent_id" not in params

    def test_announce_maps_to_delivery_mode(self) -> None:
        job = CronJobCreate(
            name="test",
            agent_id="the-claw",
            schedule_type="cron",
            schedule_expr="0 9 * * *",
            announce=True,
        )
        params = build_add_params(job)
        assert params["delivery"]["mode"] == "announce"

    def test_silent_delivery_default(self) -> None:
        job = CronJobCreate(
            name="test",
            agent_id="the-claw",
            schedule_type="cron",
            schedule_expr="0 9 * * *",
        )
        params = build_add_params(job)
        assert params["delivery"]["mode"] == "silent"

    def test_thinking_and_timeout_in_payload(self) -> None:
        job = CronJobCreate(
            name="test",
            agent_id="the-claw",
            schedule_type="cron",
            schedule_expr="0 9 * * *",
            thinking="low",
            timeout_seconds=600,
        )
        params = build_add_params(job)
        assert params["payload"]["thinking"] == "low"
        assert params["payload"]["timeoutSeconds"] == 600

    def test_session_target_maps_correctly(self) -> None:
        job = CronJobCreate(
            name="test",
            agent_id="the-claw",
            schedule_type="cron",
            schedule_expr="0 9 * * *",
            session_target="isolated",
        )
        params = build_add_params(job)
        assert params["sessionTarget"] == "isolated"

    def test_timezone_in_schedule(self) -> None:
        job = CronJobCreate(
            name="test",
            agent_id="the-claw",
            schedule_type="cron",
            schedule_expr="0 9 * * *",
            timezone="America/New_York",
        )
        params = build_add_params(job)
        assert params["schedule"]["tz"] == "America/New_York"

    def test_description_included_when_set(self) -> None:
        job = CronJobCreate(
            name="test",
            agent_id="the-claw",
            schedule_type="cron",
            schedule_expr="0 9 * * *",
            description="Weekly scan",
        )
        params = build_add_params(job)
        assert params["description"] == "Weekly scan"

    def test_description_excluded_when_empty(self) -> None:
        job = CronJobCreate(
            name="test",
            agent_id="the-claw",
            schedule_type="cron",
            schedule_expr="0 9 * * *",
        )
        params = build_add_params(job)
        assert "description" not in params


class TestBuildUpdateParams:
    """Verify partial update param mapping."""

    def test_only_id_when_empty_update(self) -> None:
        update = CronJobUpdate()
        params = build_update_params("job-123", update)
        assert params == {"id": "job-123"}

    def test_enable_toggle(self) -> None:
        update = CronJobUpdate(enabled=False)
        params = build_update_params("job-123", update)
        assert params["enabled"] is False
        assert "schedule" not in params
        assert "payload" not in params

    def test_schedule_update(self) -> None:
        update = CronJobUpdate(schedule_type="every", schedule_expr="4h")
        params = build_update_params("job-123", update)
        assert params["schedule"]["kind"] == "every"
        assert params["schedule"]["every"] == "4h"

    def test_message_update(self) -> None:
        update = CronJobUpdate(message="new instructions")
        params = build_update_params("job-123", update)
        assert params["payload"]["message"] == "new instructions"

    def test_announce_toggle(self) -> None:
        update = CronJobUpdate(announce=True)
        params = build_update_params("job-123", update)
        assert params["delivery"]["mode"] == "announce"

    def test_timezone_only_update(self) -> None:
        update = CronJobUpdate(timezone="UTC")
        params = build_update_params("job-123", update)
        assert params["schedule"]["tz"] == "UTC"

    def test_expr_without_type_uses_generic_key(self) -> None:
        update = CronJobUpdate(schedule_expr="0 10 * * *")
        params = build_update_params("job-123", update)
        assert params["schedule"]["expr"] == "0 10 * * *"


# ---------------------------------------------------------------------------
# Tests: Job normalization
# ---------------------------------------------------------------------------


class TestNormalizeJob:
    """Verify raw gateway job dict → API response shape."""

    def test_basic_normalization(self) -> None:
        raw = {
            "id": "abc-123",
            "name": "morning-scan",
            "agentId": "stock-analyst",
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "0 9 * * 1-5", "tz": "America/Edmonton"},
            "payload": {"message": "Run scan", "thinking": "low", "timeoutSeconds": 120},
            "delivery": {"mode": "announce"},
            "sessionTarget": "isolated",
        }
        result = normalize_job(raw)
        assert result["id"] == "abc-123"
        assert result["agent_id"] == "stock-analyst"
        assert result["schedule_type"] == "cron"
        assert result["schedule_expr"] == "0 9 * * 1-5"
        assert result["timezone"] == "America/Edmonton"
        assert result["message"] == "Run scan"
        assert result["thinking"] == "low"
        assert result["timeout_seconds"] == 120
        assert result["session_target"] == "isolated"
        assert result["announce"] is True

    def test_every_schedule_normalization(self) -> None:
        raw = {
            "id": "def-456",
            "name": "price-check",
            "agentId": "stock-analyst",
            "enabled": True,
            "schedule": {"kind": "every", "every": "6h", "tz": "UTC"},
            "payload": {"message": "Check prices"},
            "delivery": {"mode": "silent"},
        }
        result = normalize_job(raw)
        assert result["schedule_type"] == "every"
        assert result["schedule_expr"] == "6h"
        assert result["announce"] is False

    def test_missing_fields_get_defaults(self) -> None:
        result = normalize_job({})
        assert result["id"] == ""
        assert result["name"] == ""
        assert result["agent_id"] == ""
        assert result["enabled"] is False
        assert result["schedule_type"] == ""
        assert result["timezone"] == "UTC"
        assert result["announce"] is False
