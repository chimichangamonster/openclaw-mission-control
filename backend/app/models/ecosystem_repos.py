"""Ecosystem intelligence — trending GitHub repos from the agent/AI ecosystem.

These tables are global (not org-scoped). Access is gated per-org via the
`ecosystem_intel` feature flag at the API layer. Storing per-org would 4x the
data with no benefit — GitHub repo metadata is the same for every viewer.

Two tables:
- `ecosystem_repos` — stable identity per repo, holds latest snapshot inline
  (stars, forks, language, description) so the list page is a single read.
- `ecosystem_snapshots` — historical stars/forks per refresh cycle, used to
  compute 24h growth deltas.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field

from app.core.time import utcnow
from app.models.base import QueryModel


class EcosystemRepo(QueryModel, table=True):
    """A GitHub repo tracked by the ecosystem-intel feed."""

    __tablename__ = "ecosystem_repos"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    full_name: str = Field(index=True, unique=True)
    owner: str = Field(index=True)
    name: str
    description: str | None = None
    html_url: str
    language: str | None = Field(default=None, index=True)
    category: str = Field(default="other", index=True)
    stars: int = Field(default=0, index=True)
    forks: int = Field(default=0)
    open_issues: int = Field(default=0)
    topics_json: str = Field(default="[]")
    pushed_at: datetime | None = None
    repo_created_at: datetime | None = None
    first_seen_at: datetime = Field(default_factory=utcnow)
    last_synced_at: datetime = Field(default_factory=utcnow, index=True)


class EcosystemSnapshot(QueryModel, table=True):
    """Historical stars/forks snapshot per refresh, used for growth deltas."""

    __tablename__ = "ecosystem_snapshots"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    repo_id: UUID = Field(foreign_key="ecosystem_repos.id", index=True)
    captured_at: datetime = Field(default_factory=utcnow, index=True)
    stars: int = Field(default=0)
    forks: int = Field(default=0)
