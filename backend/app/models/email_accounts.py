"""OAuth-connected email account model."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped

RUNTIME_ANNOTATION_TYPES = (datetime,)


class EmailAccount(TenantScoped, table=True):
    """OAuth-connected email account for Zoho Mail or Microsoft Outlook."""

    __tablename__ = "email_accounts"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "provider", "email_address", name="uq_email_accounts_org_provider_email"
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    provider: str = Field(index=True)  # "zoho" or "microsoft"
    email_address: str = Field(index=True)
    display_name: str | None = None
    access_token_encrypted: str = ""
    refresh_token_encrypted: str = ""
    token_expires_at: datetime | None = None
    scopes: str | None = None
    provider_account_id: str | None = None
    sync_enabled: bool = Field(default=True, index=True)
    visibility: str = Field(default="shared", index=True)  # "shared" or "private"
    # Scope controls — restrict what agents can access
    allowed_folders_json: str = Field(default="[]")  # empty = all folders
    blocked_senders_json: str = Field(default="[]")  # emails from these senders are hidden from agents
    last_sync_at: datetime | None = None
    last_sync_error: str | None = None
    sync_cursor: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
