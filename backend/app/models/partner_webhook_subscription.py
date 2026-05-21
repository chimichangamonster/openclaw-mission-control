"""Partner webhook subscription model for the `/api/v1/partner/webhooks` namespace.

See `docs/business/partner-api-v1-scope.md` (Webhooks section + Webhook security
section) for full design.

A partner organization registers one or more URLs to receive HMAC-signed event
deliveries. The ``events`` list filters which event types fire deliveries; an
empty list is accepted in v1 (the only real event ``vc.test.ping`` ships in
Step 6 alongside the dispatcher).

The HMAC ``secret`` half is shown ONCE in the create-response (analogous to
``PartnerApiKey.full_token``). After that point only ``secret_hash`` is
recoverable from the DB, and that's what the dispatcher reads on every fire.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field

from app.core.time import utcnow
from app.models.base import QueryModel


class PartnerWebhookSubscription(QueryModel, table=True):
    """Bearer-style webhook subscription owned by a partner organization.

    Lifecycle: created → (optional) auto-disabled after 20 consecutive
    failures → deleted (partner must recreate to resume after auto-disable;
    forces re-verification of their endpoint).
    """

    __tablename__ = "partner_webhook_subscriptions"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)

    # Target HTTPS URL — SSRF-validated at create time and re-validated at
    # dispatch time (DNS-rebinding defense). See partner_webhook_url_validation.
    url: str

    # Event type filter. Empty list is intentionally allowed in v1 — the only
    # registered v1 event is ``vc.test.ping`` and Step 6 of the rollout adds
    # the dispatch + worker code that consults this list.
    events: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # PBKDF2-SHA256 hash of the HMAC ``secret`` half. Format matches
    # ``app/core/partner_tokens.hash_partner_secret``. The plaintext secret is
    # returned ONCE in the create response.
    secret_hash: str

    # ``active`` flips to False when ``consecutive_failures`` hits 20 (set by
    # the dispatch worker, not by partner CRUD). Re-activation requires
    # delete + recreate.
    active: bool = Field(default=True)

    # Timestamp the auto-disable triggered; surfaced in ``/me`` so partners
    # can see disabled subs without a separate audit endpoint.
    auto_disabled_at: datetime | None = Field(default=None)

    # Reset to 0 on any 2xx delivery; incremented on each failed attempt
    # past the retry schedule. Watched by the auto-disable trigger.
    consecutive_failures: int = Field(default=0)

    created_at: datetime = Field(default_factory=utcnow)

    @property
    def is_active(self) -> bool:
        return self.active

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialise without ``secret_hash``. Safe for any read response.

        The ``id`` is emitted as ``wh_<uuid>`` to match the public shape
        documented in the scope doc; partners reference subscriptions by this
        form. ``secret`` is intentionally absent — only the create-response
        ever includes it.
        """
        return {
            "id": f"wh_{self.id}",
            "organization_id": str(self.organization_id),
            "url": self.url,
            "events": list(self.events),
            "active": self.active,
            "auto_disabled_at": (
                self.auto_disabled_at.isoformat() if self.auto_disabled_at else None
            ),
            "consecutive_failures": self.consecutive_failures,
            "created_at": self.created_at.isoformat(),
        }
