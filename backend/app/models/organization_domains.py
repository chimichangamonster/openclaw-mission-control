"""Domain-to-organization mapping for automatic org assignment on sign-in."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.core.time import utcnow
from app.models.base import QueryModel

# Common personal email providers — cannot be claimed by any org.
PERSONAL_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        "yahoo.com",
        "yahoo.ca",
        "icloud.com",
        "me.com",
        "mac.com",
        "aol.com",
        "protonmail.com",
        "proton.me",
        "pm.me",
        "zoho.com",
        "mail.com",
        "gmx.com",
        "gmx.net",
        "yandex.com",
        "fastmail.com",
        "tutanota.com",
        "tuta.io",
    }
)


class OrganizationDomain(QueryModel, table=True):
    """Maps an email domain to an organization for automatic member assignment."""

    __tablename__ = "organization_domains"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("domain", name="uq_org_domains_domain"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    domain: str = Field(index=True)  # e.g. "eliteconstruction.ca"
    default_role: str = Field(default="member")  # role assigned to auto-joined users
    verified: bool = Field(default=True)  # reserved for future domain verification
    created_at: datetime = Field(default_factory=utcnow)
