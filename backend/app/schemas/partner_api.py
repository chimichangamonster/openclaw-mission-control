"""Pydantic schemas for the Partner API v1 namespace.

See `docs/business/partner-api-v1-scope.md` for design context.
"""

from __future__ import annotations

from sqlmodel import SQLModel


class PartnerIdentityRead(SQLModel):
    """Response shape for ``GET /api/v1/partner/me``.

    Used by partners as a health-check / debugging endpoint to confirm
    their integration is authenticated correctly. Surfaces the calling
    key's identity, granted scopes, and rate-limit headroom.
    """

    partner_org: str
    key_id: str
    scopes: list[str]
    rate_limit_per_minute: int
