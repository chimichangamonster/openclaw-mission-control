"""Schemas for observability / quality scoring API."""

from __future__ import annotations

from pydantic import Field
from sqlmodel import SQLModel

from app.schemas.common import NonEmptyStr


class QualityScoreCreate(SQLModel):
    """Request body for submitting a quality score to Langfuse."""

    trace_id: NonEmptyStr
    name: NonEmptyStr = Field(
        description="Score name — e.g. 'accuracy', 'helpfulness', 'relevance'"
    )
    value: float = Field(ge=0.0, le=1.0, description="Score value between 0 and 1")
    comment: str | None = Field(
        default=None, max_length=1000, description="Optional explanation"
    )
