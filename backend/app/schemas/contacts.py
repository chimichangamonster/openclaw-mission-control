"""Schemas for org contacts endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel import SQLModel

from app.schemas.common import NonEmptyStr

RUNTIME_ANNOTATION_TYPES = (datetime, UUID, NonEmptyStr)


class OrgContactRead(SQLModel):
    """Serialized org contact."""

    id: UUID
    organization_id: UUID
    created_by_user_id: UUID | None = None
    email: str
    name: str = ""
    company: str = ""
    phone: str = ""
    role: str = ""
    notes: str = ""
    source: str = "manual"
    created_at: datetime
    updated_at: datetime


class OrgContactCreate(SQLModel):
    """Payload for creating a contact."""

    email: NonEmptyStr
    name: str = ""
    company: str = ""
    phone: str = ""
    role: str = ""
    notes: str = ""


class OrgContactUpdate(SQLModel):
    """Payload for updating a contact."""

    name: str | None = None
    email: str | None = None
    company: str | None = None
    phone: str | None = None
    role: str | None = None
    notes: str | None = None
