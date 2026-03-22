"""Google Calendar OAuth connection per organization."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped


class GoogleCalendarConnection(TenantScoped, table=True):
    """OAuth-connected Google account for Calendar integration."""

    __tablename__ = "google_calendar_connections"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "provider_account_id", name="uq_gcal_org_account"
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    provider_account_id: str = ""
    email_address: str = ""
    display_name: str | None = None
    access_token_encrypted: str = ""
    refresh_token_encrypted: str = ""
    token_expires_at: datetime | None = None
    scopes: str | None = None
    is_active: bool = Field(default=True)
    # Default calendar ID (usually "primary")
    default_calendar_id: str = Field(default="primary")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
