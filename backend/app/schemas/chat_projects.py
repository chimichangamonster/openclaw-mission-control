"""Schemas for chat project CRUD + session assignment endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel import SQLModel

from app.schemas.common import NonEmptyStr


class ChatProjectCreate(SQLModel):
    """Payload for creating a chat project."""

    name: NonEmptyStr
    description: str | None = None
    color: str | None = None
    sort_order: int = 0


class ChatProjectUpdate(SQLModel):
    """Payload for updating a chat project (all fields optional)."""

    name: str | None = None
    description: str | None = None
    color: str | None = None
    sort_order: int | None = None
    archived: bool | None = None


class ChatProjectRead(SQLModel):
    """Read model for a chat project, returned from list/create/update endpoints."""

    id: UUID
    name: str
    description: str | None = None
    color: str | None = None
    sort_order: int = 0
    archived: bool = False
    session_count: int = 0
    created_at: datetime
    updated_at: datetime


class SessionProjectAssignment(SQLModel):
    """Payload for assigning a session to a project (null to unassign)."""

    project_id: UUID | None = None
