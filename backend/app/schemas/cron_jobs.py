"""Schemas for cron job CRUD endpoints."""

from __future__ import annotations

from typing import Literal

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
