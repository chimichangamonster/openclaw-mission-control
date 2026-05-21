"""Pydantic/SQLModel schemas for admin-only partner-key CRUD endpoints.

These schemas serve the internal ``/api/v1/admin/partner-keys`` namespace
used by platform admins to provision keys. NOT exposed in the partner-
facing OpenAPI spec.

See `docs/business/partner-api-v1-scope.md` for design.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field
from sqlmodel import SQLModel


class PartnerApiKeyCreateRequest(SQLModel):
    """Body for ``POST /api/v1/admin/partner-keys``.

    ``scopes`` must be a subset of ``REAL_SCOPES``; reserved scopes are
    rejected with 422 (see ``app/core/partner_tokens.validate_scopes``).
    """

    organization_id: UUID
    label: str = Field(min_length=1, max_length=200)
    scopes: list[str] = Field(default_factory=list)
    rate_limit_override: int | None = Field(default=None, gt=0)


class PartnerApiKeyCreateResponse(SQLModel):
    """Response for key creation. ``full_token`` is returned ONCE."""

    id: UUID
    organization_id: UUID
    key_id: str
    full_token: str
    scopes: list[str]
    label: str
    rate_limit_override: int | None
    created_at: datetime


class PartnerApiKeyListItem(SQLModel):
    """Single-key shape returned by ``GET /api/v1/admin/partner-keys``.

    Excludes the hash and the full token. ``last_used_at``, ``revoked_at``,
    and ``revoked_reason`` surface the key's lifecycle state.
    """

    id: UUID
    organization_id: UUID
    key_id: str
    scopes: list[str]
    label: str
    rate_limit_override: int | None
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    revoked_reason: str | None


class PartnerApiKeyRevokeRequest(SQLModel):
    """Body for ``DELETE /api/v1/admin/partner-keys/{id}``.

    ``revoked_reason`` is required so the audit trail captures intent.
    """

    revoked_reason: str = Field(min_length=1, max_length=500)
