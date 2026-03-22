"""User model storing identity and profile preferences."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field

from app.models.base import QueryModel

# Bump this when terms change — users must re-accept
CURRENT_TERMS_VERSION = "2026.1"


class User(QueryModel, table=True):
    """Application user account and profile attributes."""

    __tablename__ = "users"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    clerk_user_id: str = Field(index=True, unique=True)
    email: str | None = Field(default=None, index=True)
    name: str | None = None
    preferred_name: str | None = None
    pronouns: str | None = None
    timezone: str | None = None
    notes: str | None = None
    context: str | None = None
    is_super_admin: bool = Field(default=False)
    active_organization_id: UUID | None = Field(
        default=None,
        foreign_key="organizations.id",
        index=True,
    )
    # Terms & conditions acceptance
    terms_accepted_version: str | None = Field(default=None)
    terms_accepted_at: datetime | None = Field(default=None)
    privacy_accepted_at: datetime | None = Field(default=None)
