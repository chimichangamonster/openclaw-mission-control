"""Schemas for the ecosystem-intel API surface."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel import SQLModel


class EcosystemRepoRead(SQLModel):
    """Read model for a tracked ecosystem repo, with computed growth delta."""

    id: UUID
    full_name: str
    owner: str
    name: str
    description: str | None = None
    html_url: str
    language: str | None = None
    category: str
    stars: int
    forks: int
    open_issues: int
    topics: list[str] = []
    pushed_at: datetime | None = None
    repo_created_at: datetime | None = None
    first_seen_at: datetime
    last_synced_at: datetime
    growth_24h: int = 0


class EcosystemRefreshResult(SQLModel):
    """Returned from POST /ecosystem-intel/refresh."""

    fetched: int
    upserted: int
    snapshots: int
    started_at: datetime
    finished_at: datetime
    error: str | None = None


class EcosystemStatus(SQLModel):
    """Returned from GET /ecosystem-intel/status — page header info."""

    repo_count: int
    last_synced_at: datetime | None = None
    has_token: bool
