"""Manual organization contacts — external people (clients, contractors, suppliers)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped

RUNTIME_ANNOTATION_TYPES = (datetime,)


class OrgContact(TenantScoped, table=True):
    """An external contact associated with an organization."""

    __tablename__ = "org_contacts"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_org_contacts_org_email"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    created_by_user_id: UUID | None = Field(default=None, foreign_key="users.id")
    email: str = Field(index=True)
    name: str = ""
    company: str = ""
    phone: str = ""
    role: str = ""  # e.g. "foreman", "client", "supplier"
    notes: str = ""
    source: str = Field(default="manual", index=True)  # "manual" or "email"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
