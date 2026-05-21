"""HMAC signing + envelope construction for partner webhook deliveries.

See `docs/business/partner-api-v1-scope.md` (Webhook security → HMAC signing
+ Event envelope sections) for design.

Outbound header convention (matches Stripe):

* ``X-VC-Signature: sha256=<hex>`` — HMAC-SHA256 of ``<timestamp>.<body>``
  using the subscription's HMAC secret as the key.
* ``X-VC-Timestamp: <unix-ms>`` — millisecond Unix timestamp signed alongside
  the body. Partner must reject any delivery whose timestamp is outside
  ±5 minutes of their clock to defend against replay.

The signature is over ``<timestamp>.<body>`` (timestamp + literal ``.`` +
body bytes). The literal-dot separator is *unambiguous* because timestamps
are pure digits — same robustness rationale as the ``vck_<key_id>.<secret>``
wire format in :mod:`app.core.partner_tokens`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from app.core.time import utcnow

SIGNATURE_HEADER = "X-VC-Signature"
TIMESTAMP_HEADER = "X-VC-Timestamp"
SIGNATURE_ALGORITHM_PREFIX = "sha256="

# Partner-side clock skew window. Identical to the Stripe-default 5 minutes;
# the scope doc commits to this number.
REPLAY_WINDOW_SECONDS = 300


def _utc_timestamp_ms() -> int:
    """Current Unix timestamp in milliseconds (UTC)."""
    return int(time.time() * 1000)


def build_event_envelope(
    *,
    event_type: str,
    subscription_id: UUID,
    data: dict[str, Any],
    occurred_at: datetime | None = None,
    event_id: UUID | None = None,
) -> dict[str, Any]:
    """Construct the Stripe-shaped envelope partners route on.

    ``event_id`` defaults to a fresh UUIDv4 so retry-induced duplicates can
    be deduped client-side. Tests pass an explicit one to lock invariants.
    """
    return {
        "event": event_type,
        "id": f"evt_{event_id or uuid4()}",
        "subscription_id": f"wh_{subscription_id}",
        "occurred_at": (occurred_at or utcnow()).isoformat() + "Z"
        if occurred_at is None or occurred_at.tzinfo is None
        else occurred_at.isoformat(),
        "data": data,
    }


def serialize_envelope(envelope: dict[str, Any]) -> bytes:
    """Canonical body serialization. Stable key ordering for repeatable signatures."""
    return json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_body(
    *,
    secret: str,
    body: bytes,
    timestamp_ms: int | None = None,
) -> tuple[str, str]:
    """Return ``(signature_header_value, timestamp_header_value)``.

    Signature is HMAC-SHA256 over ``<timestamp>.<body>``; the partner
    recomputes the same string and verifies. ``timestamp_ms`` can be
    passed explicitly for deterministic test signatures.
    """
    ts = timestamp_ms if timestamp_ms is not None else _utc_timestamp_ms()
    msg = f"{ts}.".encode("utf-8") + body
    digest = hmac.new(
        secret.encode("utf-8"),
        msg=msg,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"{SIGNATURE_ALGORITHM_PREFIX}{digest}", str(ts)


def verify_signature(
    *,
    secret: str,
    body: bytes,
    signature_header: str,
    timestamp_header: str,
    tolerance_seconds: int = REPLAY_WINDOW_SECONDS,
    now_ms: int | None = None,
) -> bool:
    """Constant-time verification of a webhook signature.

    Returns False on any of:

    * Missing ``sha256=`` prefix
    * Malformed timestamp
    * Timestamp outside ±tolerance_seconds of ``now_ms``
    * HMAC mismatch (constant-time compared)

    The partner SDK we ship to customers will mirror this function.
    Mission Control uses it in tests to lock the signature shape.
    """
    if not signature_header.startswith(SIGNATURE_ALGORITHM_PREFIX):
        return False
    received_digest = signature_header[len(SIGNATURE_ALGORITHM_PREFIX) :]

    try:
        ts_int = int(timestamp_header)
    except (TypeError, ValueError):
        return False

    current_ms = now_ms if now_ms is not None else _utc_timestamp_ms()
    if abs(current_ms - ts_int) > tolerance_seconds * 1000:
        return False

    msg = f"{ts_int}.".encode("utf-8") + body
    expected_digest = hmac.new(
        secret.encode("utf-8"),
        msg=msg,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(received_digest, expected_digest)
