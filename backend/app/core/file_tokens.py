"""HMAC-signed temporary file download tokens.

Tokens encode a workspace-relative file path and an expiration timestamp.
They are compact, URL-safe, and require no database storage.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode

from app.core.config import settings


def _get_signing_key() -> bytes:
    key = settings.encryption_key or settings.email_token_encryption_key
    if not key:
        raise ValueError("ENCRYPTION_KEY must be set for file token signing.")
    return hashlib.sha256(key.encode()).digest()


def create_file_token(relative_path: str, expires_hours: int = 24) -> str:
    """Create a signed, URL-safe token encoding a file path and expiry."""
    payload = json.dumps(
        {"p": relative_path, "e": int(time.time()) + expires_hours * 3600},
        separators=(",", ":"),
    )
    payload_b64 = urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = hmac.new(_get_signing_key(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_file_token(token: str) -> str | None:
    """Verify token signature and expiry. Returns the relative path or None."""
    parts = token.split(".", 1)
    if len(parts) != 2:
        return None
    payload_b64, sig = parts

    expected_sig = hmac.new(
        _get_signing_key(), payload_b64.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None

    # Restore base64 padding
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    try:
        payload = json.loads(urlsafe_b64decode(padded))
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get("e", 0) < time.time():
        return None

    path = payload.get("p")
    if not isinstance(path, str) or not path:
        return None
    return path
