"""Pydantic/SQLModel schemas for the Partner API webhook endpoints.

See `docs/business/partner-api-v1-scope.md` (Webhooks section) for design.

The HMAC ``secret`` is returned ONCE in :class:`PartnerWebhookCreateResponse`
— the read shape (:class:`PartnerWebhookRead`) intentionally omits it.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field
from sqlmodel import SQLModel


class PartnerWebhookCreateRequest(SQLModel):
    """Body for ``POST /api/v1/partner/webhooks``.

    ``url`` is SSRF-validated server-side; partners cannot subscribe internal
    addresses. ``events`` may be empty in v1 — the only registered event
    ships in Step 6.
    """

    url: str = Field(min_length=1, max_length=2048)
    events: list[str] = Field(default_factory=list)


class PartnerWebhookRead(SQLModel):
    """Standard read shape — never includes the HMAC secret."""

    id: str
    organization_id: str
    url: str
    events: list[str]
    active: bool
    auto_disabled_at: datetime | None
    consecutive_failures: int
    created_at: datetime


class PartnerWebhookCreateResponse(PartnerWebhookRead):
    """Create response only — embeds the plaintext ``secret`` ONCE.

    Partners use ``secret`` to verify the HMAC on inbound webhook deliveries.
    After this response the secret is unrecoverable; rotation = delete +
    recreate.
    """

    secret: str


class PartnerWebhookTestRequest(SQLModel):
    """Body for ``POST /api/v1/partner/webhooks/{id}/test``.

    The partner echoes back the ``secret`` returned from the create
    response so the test event can be signed with the SAME HMAC key
    the partner verifies against. We deliberately do NOT cache the
    secret server-side (rotation = delete + recreate); requiring it
    in the request body preserves that invariant while still letting
    partners exercise the full signature-verification pipeline.

    If the partner has lost the secret, they delete + recreate the
    subscription to get a fresh one.
    """

    secret: str = Field(min_length=1, max_length=200)


class PartnerWebhookTestResponse(SQLModel):
    """Response for the test-event endpoint.

    ``event_id`` is the envelope's ``evt_<uuid>`` field — partners use it
    for trace correlation between the synchronous API response and the
    async webhook delivery they receive moments later.
    """

    event_id: str
    enqueued: bool


class PartnerWebhookFailureRead(SQLModel):
    """Single delivery-failure audit row returned by the failures endpoint."""

    id: str
    subscription_id: str
    event_type: str
    event_id: str
    status: str
    attempts: int
    http_status: int | None
    reason: str
    created_at: datetime


class PartnerWebhookFailuresPage(SQLModel):
    """Cursor-paginated failures response.

    ``next_cursor`` is opaque to the partner — a UUID string that the
    partner passes back as the ``cursor`` query parameter to fetch the
    next page. ``None`` when no more pages remain.
    """

    items: list[PartnerWebhookFailureRead]
    next_cursor: str | None
