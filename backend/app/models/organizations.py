"""Organization model representing top-level tenant entities."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field

from app.core.time import utcnow
from app.models.base import QueryModel

RUNTIME_ANNOTATION_TYPES = (datetime,)


def slugify(name: str) -> str:
    """Convert an org name to a URL-safe slug for directory/container naming."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


class Organization(QueryModel, table=True):
    """Top-level organization tenant record."""

    __tablename__ = "organizations"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    slug: str = Field(default="", index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
