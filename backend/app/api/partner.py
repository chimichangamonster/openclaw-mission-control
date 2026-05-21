"""Partner API v1 — public-facing namespace for *Beast siblings / partners.

See `docs/business/partner-api-v1-scope.md` for full design.

v1 surface (substrate-only, no resource CRUD):

* ``GET    /api/v1/partner/me``                            — identity + rate-limit headroom
* ``POST   /api/v1/partner/webhooks``                       — create subscription
* ``GET    /api/v1/partner/webhooks``                       — list subscriptions
* ``DELETE /api/v1/partner/webhooks/{id}``                  — remove subscription
* ``POST   /api/v1/partner/webhooks/{id}/test``             — fire vc.test.ping (Step 6)
* ``GET    /api/v1/partner/webhooks/{id}/failures``         — paginated audit (Step 7)

This module currently ships Steps 3 + 5 of Session A:
``/me`` plus webhook subscription CRUD. The dispatch + failures-audit
endpoints land in Steps 6-7 alongside the worker code.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select

from app.core.logging import get_logger
from app.core.partner_auth import (
    PARTNER_RATE_LIMIT_DEP,
    PartnerAuthContext,
    require_partner_identity_read,
    require_partner_webhooks_manage,
)
from app.core.partner_tokens import hash_partner_secret, verify_partner_secret
from app.core.time import utcnow
from app.db.session import get_session
from app.models.partner_webhook_delivery import PartnerWebhookDelivery
from app.models.partner_webhook_subscription import PartnerWebhookSubscription
from app.schemas.partner_api import PartnerIdentityRead
from app.schemas.partner_webhooks import (
    PartnerWebhookCreateRequest,
    PartnerWebhookCreateResponse,
    PartnerWebhookFailureRead,
    PartnerWebhookFailuresPage,
    PartnerWebhookRead,
    PartnerWebhookTestRequest,
    PartnerWebhookTestResponse,
)
from app.services.partner_webhook_dispatch import enqueue_partner_webhook_event
from app.services.partner_webhook_url_validation import (
    WebhookUrlValidationError,
    validate_webhook_url_at_create_time,
)

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)

router = APIRouter(prefix="/partner", tags=["partner-v1"])

SESSION_DEP = Depends(get_session)

# Wire prefixes for the public ID + secret formats.
SUBSCRIPTION_ID_PREFIX = "wh_"
SECRET_PREFIX = "whsec_"

# Entropy floor for the HMAC secret half. 32 bytes ≈ 256 bits before
# PBKDF2 hardening — comfortably above any brute-force budget.
SECRET_ENTROPY_BYTES = 32


def _generate_webhook_secret() -> str:
    """Return a partner-facing HMAC secret with the ``whsec_`` prefix."""
    return f"{SECRET_PREFIX}{secrets.token_urlsafe(SECRET_ENTROPY_BYTES)}"


def _parse_subscription_id(raw: str) -> UUID:
    """Parse a public ``wh_<uuid>`` string into its underlying ``UUID``.

    Raises ``HTTPException(404)`` on any parse failure — we don't leak
    whether the ID was malformed vs. a non-existent valid UUID. Partner-
    visible behaviour is the same: "subscription not found."
    """
    if not raw.startswith(SUBSCRIPTION_ID_PREFIX):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    try:
        return UUID(raw[len(SUBSCRIPTION_ID_PREFIX) :])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from exc


# === Identity ============================================================


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


# === Webhook subscriptions ===============================================


@router.post(
    "/webhooks",
    response_model=PartnerWebhookCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a webhook subscription (HMAC secret returned ONCE)",
)
async def create_webhook_subscription(
    body: PartnerWebhookCreateRequest,
    ctx: PartnerAuthContext = Depends(require_partner_webhooks_manage),
    _rate_limit: None = PARTNER_RATE_LIMIT_DEP,
    session: AsyncSession = SESSION_DEP,
) -> PartnerWebhookCreateResponse:
    """Register a new webhook subscription for the calling partner org.

    Validates ``url`` against the strict SSRF policy at create time — see
    :mod:`app.services.partner_webhook_url_validation` for the full rule
    set. The dispatcher re-validates at fire time for DNS-rebinding
    defense. Empty ``events`` is allowed in v1 (the only registered event
    ships in Step 6).

    The HMAC ``secret`` is returned ONCE in this response. Partners must
    store it for signature verification; rotation = delete + recreate.
    """
    try:
        validate_webhook_url_at_create_time(body.url)
    except WebhookUrlValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"webhook url rejected: {exc.reason}",
        ) from exc

    secret = _generate_webhook_secret()
    secret_hash = hash_partner_secret(secret)

    subscription = PartnerWebhookSubscription(
        organization_id=ctx.organization.id,
        url=body.url,
        events=list(body.events),
        secret_hash=secret_hash,
        active=True,
        consecutive_failures=0,
        created_at=utcnow(),
    )
    session.add(subscription)
    await session.commit()
    await session.refresh(subscription)

    logger.info(
        "partner webhook created org_id=%s subscription_id=%s url_host=%s events=%s",
        ctx.organization.id,
        subscription.id,
        body.url.split("://", 1)[-1].split("/", 1)[0],
        body.events,
    )

    safe = subscription.to_safe_dict()
    return PartnerWebhookCreateResponse(secret=secret, **safe)


@router.get(
    "/webhooks",
    response_model=list[PartnerWebhookRead],
    summary="List the calling partner org's webhook subscriptions",
)
async def list_webhook_subscriptions(
    ctx: PartnerAuthContext = Depends(require_partner_webhooks_manage),
    _rate_limit: None = PARTNER_RATE_LIMIT_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[PartnerWebhookRead]:
    """List webhook subscriptions owned by the calling partner org.

    Strictly org-scoped — never includes subscriptions belonging to other
    orgs even if the platform admin shares a key family. The HMAC secret
    is never included in the read shape.
    """
    statement = (
        select(PartnerWebhookSubscription)
        .where(
            PartnerWebhookSubscription.organization_id == ctx.organization.id  # type: ignore[arg-type]
        )
        .order_by(PartnerWebhookSubscription.created_at.desc())  # type: ignore[union-attr]
    )
    rows = (await session.exec(statement)).all()
    return [PartnerWebhookRead(**row.to_safe_dict()) for row in rows]


@router.delete(
    "/webhooks/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a webhook subscription owned by the calling partner org",
)
async def delete_webhook_subscription(
    subscription_id: str,
    ctx: PartnerAuthContext = Depends(require_partner_webhooks_manage),
    _rate_limit: None = PARTNER_RATE_LIMIT_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    """Hard-delete a webhook subscription by ``wh_<uuid>`` ID.

    Org-scoped: deletion of another org's subscription returns 404, not
    403 — we don't leak existence to the caller.
    """
    uuid_value = _parse_subscription_id(subscription_id)

    subscription = await session.get(PartnerWebhookSubscription, uuid_value)
    if subscription is None or subscription.organization_id != ctx.organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    await session.delete(subscription)
    await session.commit()

    logger.info(
        "partner webhook deleted org_id=%s subscription_id=%s",
        ctx.organization.id,
        uuid_value,
    )


# === Test event ===========================================================


@router.post(
    "/webhooks/{subscription_id}/test",
    response_model=PartnerWebhookTestResponse,
    summary="Fire vc.test.ping through the full dispatch pipeline",
)
async def fire_test_webhook(
    subscription_id: str,
    body: PartnerWebhookTestRequest,
    ctx: PartnerAuthContext = Depends(require_partner_webhooks_manage),
    _rate_limit: None = PARTNER_RATE_LIMIT_DEP,
    session: AsyncSession = SESSION_DEP,
) -> PartnerWebhookTestResponse:
    """Fire a ``vc.test.ping`` event through the real dispatch pipeline.

    The partner echoes their stored ``secret`` in the request body — we
    deliberately do NOT cache the secret server-side after creation, so
    the test endpoint requires the partner to supply it. The supplied
    secret is verified against the stored ``secret_hash`` to prevent
    junk-secret triggering (also incidentally a sanity check the partner
    is testing with the right secret).

    On success the event is enqueued (not yet delivered — that happens
    asynchronously on the worker). Partners observe receipt at their
    configured ``url`` shortly afterward. The returned ``event_id`` lets
    them correlate this synchronous response with the async delivery.
    """
    uuid_value = _parse_subscription_id(subscription_id)

    subscription = await session.get(PartnerWebhookSubscription, uuid_value)
    if subscription is None or subscription.organization_id != ctx.organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if not subscription.active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="subscription is inactive (auto-disabled); delete and recreate to resume",
        )

    if not verify_partner_secret(body.secret, subscription.secret_hash):
        # 401 because the supplied credential is wrong, not a generic 422.
        # We surface the failure shape so partners debugging integration
        # know to re-check their stored secret.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="supplied secret does not match this subscription",
        )

    event_id = enqueue_partner_webhook_event(
        subscription_id=subscription.id,
        organization_id=ctx.organization.id,
        url=subscription.url,
        secret=body.secret,
        event_type="vc.test.ping",
        data={"message": "integration test"},
    )

    logger.info(
        "partner_webhook.test_fired org_id=%s subscription_id=%s event_id=%s",
        ctx.organization.id,
        subscription.id,
        event_id,
    )

    return PartnerWebhookTestResponse(event_id=event_id, enqueued=True)


# === Failures audit (Step 7) =============================================

_FAILURES_PAGE_DEFAULT = 50
_FAILURES_PAGE_MAX = 200


@router.get(
    "/webhooks/{subscription_id}/failures",
    response_model=PartnerWebhookFailuresPage,
    summary="Paginated delivery-failure audit for a subscription",
)
async def list_webhook_failures(
    subscription_id: str,
    cursor: str | None = Query(default=None),
    limit: int = Query(
        default=_FAILURES_PAGE_DEFAULT,
        ge=1,
        le=_FAILURES_PAGE_MAX,
    ),
    ctx: PartnerAuthContext = Depends(require_partner_webhooks_manage),
    _rate_limit: None = PARTNER_RATE_LIMIT_DEP,
    session: AsyncSession = SESSION_DEP,
) -> PartnerWebhookFailuresPage:
    """Cursor-paginated delivery failures for ``subscription_id``.

    Ordered newest-first by ``created_at, id``. ``next_cursor`` is the
    ``id`` of the last row in this page; pass it back as ``cursor`` to
    fetch the next page. ``next_cursor=null`` when no more pages remain.

    Strictly org-scoped — failures for another org's subscription
    return 404 (no existence leak via the failures stream either).
    """
    uuid_value = _parse_subscription_id(subscription_id)

    subscription = await session.get(PartnerWebhookSubscription, uuid_value)
    if subscription is None or subscription.organization_id != ctx.organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    statement = (
        select(PartnerWebhookDelivery)
        .where(
            PartnerWebhookDelivery.subscription_id == uuid_value,  # type: ignore[arg-type]
        )
        .order_by(
            PartnerWebhookDelivery.created_at.desc(),  # type: ignore[union-attr]
            PartnerWebhookDelivery.id.desc(),  # type: ignore[union-attr]
        )
        .limit(limit + 1)  # fetch one extra to know if next page exists
    )

    if cursor is not None:
        try:
            cursor_uuid = UUID(cursor)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid cursor",
            ) from exc
        cursor_row = await session.get(PartnerWebhookDelivery, cursor_uuid)
        if cursor_row is None or cursor_row.subscription_id != uuid_value:
            # Don't leak whether the cursor was for another org's row.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid cursor",
            )
        statement = statement.where(
            (PartnerWebhookDelivery.created_at < cursor_row.created_at)  # type: ignore[operator]
            | (
                (PartnerWebhookDelivery.created_at == cursor_row.created_at)
                & (PartnerWebhookDelivery.id < cursor_uuid)  # type: ignore[operator]
            )
        )

    rows = (await session.exec(statement)).all()
    has_more = len(rows) > limit
    page_rows = list(rows[:limit])

    return PartnerWebhookFailuresPage(
        items=[PartnerWebhookFailureRead(**row.to_safe_dict()) for row in page_rows],
        next_cursor=str(page_rows[-1].id) if has_more and page_rows else None,
    )
