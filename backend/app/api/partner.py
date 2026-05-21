"""Partner API v1 — public-facing namespace for *Beast siblings / partners.

See `docs/business/partner-api-v1-scope.md` for full design.

v1 surface (substrate-only, no resource CRUD):

* ``GET    /api/v1/partner/me``                            — identity + rate-limit headroom
* ``POST   /api/v1/partner/webhooks``                       — create subscription
* ``GET    /api/v1/partner/webhooks``                       — list subscriptions
* ``DELETE /api/v1/partner/webhooks/{id}``                  — remove subscription
* ``POST   /api/v1/partner/webhooks/{id}/test``             — fire vc.test.ping
* ``GET    /api/v1/partner/webhooks/{id}/failures``         — paginated delivery failure audit

This module ships **Step 3 of Session A** — only the ``/me`` endpoint. Webhook
endpoints land in Steps 5-7. Mounted under ``api_v1`` in ``main.py`` so its
real prefix is ``/api/v1/partner``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.logging import get_logger
from app.core.partner_auth import (
    PARTNER_RATE_LIMIT_DEP,
    PartnerAuthContext,
    require_partner_identity_read,
)
from app.schemas.partner_api import PartnerIdentityRead

logger = get_logger(__name__)

router = APIRouter(prefix="/partner", tags=["partner-v1"])


@router.get(
    "/me",
    response_model=PartnerIdentityRead,
    summary="Identity + scopes + rate-limit headroom for the calling key",
)
async def get_me(
    ctx: PartnerAuthContext = Depends(require_partner_identity_read),
    _rate_limit: None = PARTNER_RATE_LIMIT_DEP,
) -> PartnerIdentityRead:
    """Return the calling key's identity, scopes, and rate-limit headroom.

    Always callable (``identity:read`` is non-revocable for any valid key).
    Used by partners as a health-check / debugging endpoint to confirm
    their integration is authenticated correctly.
    """
    api_key = ctx.api_key
    organization = ctx.organization

    # Rate-limit headroom — for v1 we report the configured ceiling without
    # querying the limiter's actual remaining count. The X-RateLimit-*
    # headers (added in a later step) will carry the live counters.
    rate_limit = api_key.rate_limit_override or 600

    return PartnerIdentityRead(
        partner_org=organization.slug or str(organization.id),
        key_id=api_key.key_id,
        scopes=list(api_key.scopes),
        rate_limit_per_minute=rate_limit,
    )
