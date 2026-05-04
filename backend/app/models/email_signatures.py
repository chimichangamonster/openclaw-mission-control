"""Email signature library — per-account multi-signature with default."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped

RUNTIME_ANNOTATION_TYPES = (datetime,)


class EmailSignature(TenantScoped, table=True):
    """An HTML signature stored against an EmailAccount.

    Each EmailAccount can have multiple signatures. Exactly one is marked
    default (enforced at the API layer, not via DB constraint, so toggling
    default fits in a single transaction). The send pipeline appends the
    resolved signature's HTML to outbound message bodies — provider APIs do
    not auto-append the signatures users configure in their web UI.
    """

    __tablename__ = "email_signatures"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    email_account_id: UUID = Field(foreign_key="email_accounts.id", index=True)
    name: str
    body_html: str
    is_default: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
