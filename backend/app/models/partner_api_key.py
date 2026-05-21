"""Partner API key model for the `/api/v1/partner/*` namespace.

See `docs/business/partner-api-v1-scope.md` (Auth model section) for full design.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field

from app.core.time import utcnow
from app.models.base import QueryModel


class PartnerApiKey(QueryModel, table=True):
    """Bearer-token credential issued to a partner organization.

    Wire format: ``vck_<key_id>_<secret>``. The ``key_id`` portion is the
    public identifier used for DB lookup; the ``secret`` half is hashed
    via PBKDF2-HMAC-SHA256 and never persisted in plaintext.
    """

    __tablename__ = "partner_api_keys"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)

    # Public identifier (the middle segment of the wire-format token).
    # Indexed because lookup-by-key_id is the auth hot path.
    key_id: str = Field(unique=True, index=True)

    # PBKDF2-SHA256 hash of the secret half. Format matches
    # ``app/core/partner_tokens.hash_partner_token``:
    # ``pbkdf2_sha256$<iterations>$<salt_b64>$<digest_b64>``.
    key_hash: str

    # Granted scope strings; rejected at creation if any are in the
    # reserved enum (see ``partner_tokens.RESERVED_SCOPES``).
    scopes: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Human-readable name shown in admin tooling (e.g. "Optified v2 prod").
    label: str

    # Creator audit trail.
    created_by: UUID = Field(foreign_key="users.id")

    # Per-org rate-limit override (req/min). NULL means use the platform
    # default of 600. Set by admins via the partner-key CRUD endpoint.
    rate_limit_override: int | None = Field(default=None)

    created_at: datetime = Field(default_factory=utcnow)
    last_used_at: datetime | None = Field(default=None, index=True)
    revoked_at: datetime | None = Field(default=None, index=True)

    # Audit context for revocation (e.g. "rotated", "partner left",
    # "suspected leak"). Required when ``revoked_at`` is set.
    revoked_reason: str | None = Field(default=None)

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialise without the hash. Safe for admin-list responses."""
        return {
            "id": str(self.id),
            "organization_id": str(self.organization_id),
            "key_id": self.key_id,
            "scopes": list(self.scopes),
            "label": self.label,
            "created_by": str(self.created_by),
            "rate_limit_override": self.rate_limit_override,
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "revoked_reason": self.revoked_reason,
        }
