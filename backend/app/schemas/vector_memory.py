"""Schemas for agent vector memory API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field
from sqlmodel import SQLModel

from app.schemas.common import NonEmptyStr


class VectorMemoryStore(SQLModel):
    """Request body for storing a new memory."""

    content: NonEmptyStr
    source: NonEmptyStr
    extra: dict[str, Any] = {}
    ttl_days: int | None = Field(default=None, ge=1, le=365)


class VectorMemorySearch(SQLModel):
    """Request body for semantic memory search."""

    query: NonEmptyStr
    limit: int = Field(default=5, ge=1, le=50)
    source_filter: str | None = None


class VectorMemoryRead(SQLModel):
    """Response item for memory search results."""

    id: UUID
    content: str
    source: str
    agent_id: str | None = None
    similarity: float
    extra: dict[str, Any] = {}
    created_at: datetime


class VectorMemoryForget(SQLModel):
    """Request body for bulk memory deletion by source."""

    source: NonEmptyStr
