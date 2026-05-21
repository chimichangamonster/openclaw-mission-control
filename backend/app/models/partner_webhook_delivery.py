"""Partner webhook delivery audit table.

See `docs/business/partner-api-v1-scope.md` (Webhook security → Retry schedule
+ Failures audit endpoint sections) for design.

Every delivery attempt that does NOT succeed on the first try writes one row
here:

* HTTP non-2xx response, timeout, or connection error → ``status="failed"``
* DNS-rebinding check failed at dispatch time → ``status="rejected_dns"``
* Auto-disable trigger fired (20 consecutive failures) → row + sub flips
* Final attempt past the retry schedule → ``status="dead_lettered"``

Successful deliveries do NOT write rows — only the subscription's
``consecutive_failures`` counter reset is recorded. This keeps the table
small (most partners have healthy endpoints) and the failures-audit endpoint
fast.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlmodel import Field

from app.core.time import utcnow
from app.models.base import QueryModel

# Delivery status enum (string-typed for SQLite + Postgres compatibility).
# Kept here next to the model so the failures-audit endpoint imports one
# canonical place.
DELIVERY_STATUS_FAILED = "failed"
DELIVERY_STATUS_REJECTED_DNS = "rejected_dns"
DELIVERY_STATUS_DEAD_LETTERED = "dead_lettered"


class PartnerWebhookDelivery(QueryModel, table=True):
    """Single audit row for one partner-webhook delivery attempt.

    Cursor pagination keys off the row ``id`` (UUID v4 — monotonic-enough
    for cursor cursors since we ORDER BY ``created_at DESC, id DESC`` and
    use the last row's id as the next cursor).
    """

    __tablename__ = "partner_webhook_deliveries"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    subscription_id: UUID = Field(
        foreign_key="partner_webhook_subscriptions.id",
        index=True,
    )
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)

    # Stripe-shaped event envelope fields — copied here for audit even after
    # the subscription is deleted (so partners can see "what fired before
    # the sub went away").
    event_type: str
    event_id: UUID  # the ``id`` field of the event envelope; UUIDv4

    # ``failed`` (HTTP error / timeout) | ``rejected_dns`` (DNS-rebinding
    # check tripped) | ``dead_lettered`` (final retry exhausted).
    status: str

    # Attempt number that failed (1-indexed). ``attempts=6`` paired with
    # status=dead_lettered means we exhausted the retry schedule.
    attempts: int

    # HTTP status returned by the partner endpoint, if any. NULL for
    # network errors and DNS-rebinding rejections.
    http_status: int | None = Field(default=None)

    # Short reason string — also used in logs. Examples:
    # "http_502", "timeout", "connection_refused", "dns_resolved_to_private".
    reason: str

    created_at: datetime = Field(default_factory=utcnow, index=True)

    def to_safe_dict(self) -> dict[str, Any]:
        """Read-shape for the failures-audit endpoint.

        ``id`` is emitted as a bare UUID string — the endpoint already
        scopes to a single subscription, so no prefix needed.
        """
        return {
            "id": str(self.id),
            "subscription_id": f"wh_{self.subscription_id}",
            "event_type": self.event_type,
            "event_id": str(self.event_id),
            "status": self.status,
            "attempts": self.attempts,
            "http_status": self.http_status,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
        }
