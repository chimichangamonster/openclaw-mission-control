"""Org-Context Files — persistent, queryable, org-scoped reference docs.

Phase 1 ships the model + CRUD only. Phase 2 adds the upload pipeline
(document_intake → redact → embed) and a semantic-search endpoint.

The pattern this primitive solves: agents need persistent organizational
state (active prospects, current product catalog, certification status,
brand guidelines, rules-of-engagement) that doesn't live in SOUL.md and
doesn't evaporate with the chat session. Every cited source carries its
own age + living-data flag so agents can warn when retrieved context is
stale instead of confidently quoting it as current truth.

See ``docs/technical/planning-next-sprint.md`` item 58 for full scope and
the reliability argument behind staleness-aware citation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import Column, Index, Text
from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped

RUNTIME_ANNOTATION_TYPES = (datetime,)

# Mirrors VectorMemory — same OpenRouter text-embedding-3-small dimensions.
EMBEDDING_DIMENSIONS = 1536


class OrgContextFile(TenantScoped, table=True):
    """Org-scoped reference document with semantic-searchable embedding.

    One row per uploaded file. Phase 1 stores file-level embeddings only;
    chunk-level embeddings can be added in a later phase if file size
    warrants it (the document_intake pipeline already extracts page-level
    text so chunking would not require a re-extract).

    The ``embedding`` column is nullable so admins can create a row before
    the upload pipeline finishes (or to support manual re-embed flows).
    """

    __tablename__ = "org_context_files"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        Index(
            "ix_org_context_files_org_category",
            "organization_id",
            "category",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)

    # File metadata
    filename: str = Field(index=True)
    content_type: str = Field(default="application/octet-stream")
    category: str = Field(default="other", index=True)
    source: str | None = None  # Optional human note: where this file came from

    # Extracted + redacted plaintext (pipeline-populated in Phase 2).
    # Nullable in Phase 1 since CRUD admits empty rows.
    extracted_text: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )

    # Vector embedding over extracted_text (Phase 2 populates).
    embedding: Any = Field(
        default=None,
        sa_column=Column(Vector(EMBEDDING_DIMENSIONS), nullable=True),
    )

    # Visibility — same model as email accounts. Private = owner + admin
    # only. Shared = all org members. Defaults to shared.
    visibility: str = Field(default="shared")

    # Living vs static — drives the staleness warning. True (default) means
    # this file represents data that changes (prospect pipeline, customer
    # list). False means stable reference (regulations text, brand guide).
    is_living_data: bool = Field(default=True)

    # Audit / staleness
    uploaded_by_user_id: UUID | None = Field(
        default=None,
        foreign_key="users.id",
    )
    uploaded_at: datetime = Field(default_factory=utcnow)
    last_updated: datetime = Field(default_factory=utcnow)
