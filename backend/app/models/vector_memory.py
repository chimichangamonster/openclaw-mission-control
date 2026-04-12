"""Persistent vector memory for agent semantic recall."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Index, Text
from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped

RUNTIME_ANNOTATION_TYPES = (datetime,)

EMBEDDING_DIMENSIONS = 1536


class VectorMemory(TenantScoped, table=True):
    """Org-scoped vector embedding for agent semantic memory.

    Agents store facts, decisions, and summaries here via the embedding service.
    Retrieval is cosine-similarity nearest-neighbor search scoped to the org.
    """

    __tablename__ = "vector_memories"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        Index(
            "ix_vector_memories_org_source",
            "organization_id",
            "source",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    content: str = Field(sa_column=Column(Text, nullable=False))
    embedding: Any = Field(
        sa_column=Column(Vector(EMBEDDING_DIMENSIONS), nullable=False),
    )
    source: str = Field(index=True)
    agent_id: str | None = None
    metadata_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime | None = None
