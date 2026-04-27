"""Schemas for the Org-Context Files API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field
from sqlmodel import SQLModel

from app.schemas.common import NonEmptyStr

# Allowed visibility values — mirrors the email-account convention.
VISIBILITY_VALUES = {"shared", "private"}

# Suggested categories — the frontend enforces selection from this list.
# Backend stores any string so future categories don't require a migration.
CATEGORY_SUGGESTIONS = (
    "customers",
    "pricing",
    "regulations",
    "brand",
    "contracts",
    "deployments",
    "prospects",
    "rules-of-engagement",
    "other",
)


class OrgContextFileCreate(SQLModel):
    """Phase 1 metadata-only create. Phase 2 will add a multipart upload
    endpoint that runs document_intake + redact + embed before persisting."""

    filename: NonEmptyStr
    category: str = Field(default="other")
    content_type: str = Field(default="application/octet-stream")
    source: str | None = None
    visibility: str = Field(default="shared")
    is_living_data: bool = True
    extracted_text: str | None = None


class OrgContextFileUpdate(SQLModel):
    """Mutable fields. ``filename`` and ``content_type`` are immutable
    once a file is uploaded (re-upload to change them)."""

    category: str | None = None
    source: str | None = None
    visibility: str | None = None
    is_living_data: bool | None = None


class OrgContextFileRead(SQLModel):
    """Standard read shape. Excludes ``embedding`` (large binary, internal
    use) and the raw text — callers fetch text via the detail endpoint."""

    id: UUID
    filename: str
    category: str
    content_type: str
    source: str | None = None
    visibility: str
    is_living_data: bool
    uploaded_at: datetime
    last_updated: datetime
    has_embedding: bool
    age_days: int


class OrgContextFileDetail(OrgContextFileRead):
    """Detail view includes the redacted extracted text."""

    extracted_text: str | None = None


class OrgContextSearch(SQLModel):
    """Request body for semantic search across org-context files."""

    query: NonEmptyStr
    limit: int = Field(default=5, ge=1, le=25)
    category_filter: str | None = None


class OrgContextSearchHit(SQLModel):
    """One hit returned by the agent search endpoint.

    Includes everything the citing skill needs to age-stamp the citation
    and decide whether to surface a staleness warning.
    """

    id: UUID
    filename: str
    category: str
    source: str | None = None
    visibility: str
    is_living_data: bool
    snippet: str
    uploaded_at: datetime | None = None
    last_updated: datetime | None = None
    similarity: float
