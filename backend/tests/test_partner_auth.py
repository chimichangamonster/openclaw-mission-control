# ruff: noqa: INP001, SLF001
"""Unit tests for partner-API auth dependency.

Covers ``app/core/partner_auth.py``. Uses ``monkeypatch`` + ``SimpleNamespace``
stubs in the same style as ``test_agent_auth_security.py`` — no real DB.

Tests cover the seven failure modes the auth flow must reject + the two
success modes:

  failure: no Authorization header
  failure: wrong scheme (non-Bearer)
  failure: malformed token (wrong prefix, missing separator)
  failure: unknown key_id (no DB row)
  failure: valid key_id but wrong secret
  failure: revoked key
  failure: scope mismatch
  success: identity:read short-circuit (always granted)
  success: webhooks:manage granted on key
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core import partner_auth
from app.core.partner_tokens import generate_partner_token, hash_partner_secret


class _RecordingLimiter:
    """Stub limiter that always allows and records the keys it was called with."""

    def __init__(self) -> None:
        self.keys: list[str] = []

    async def is_allowed(self, key: str) -> bool:
        self.keys.append(key)
        return True


class _StubAsyncResult:
    """Mimics ``await session.exec(...).first()`` semantics with a single value."""

    def __init__(self, value: Any) -> None:
        self._value = value

    def first(self) -> Any:
        return self._value


class _StubSession:
    """Stand-in for an SQLModel AsyncSession.

    ``exec_result`` controls what ``await session.exec(...)`` returns.
    ``get_result`` controls what ``await session.get(...)`` returns.
    """

    def __init__(self, *, exec_result: Any = None, get_result: Any = None) -> None:
        self._exec_result = exec_result
        self._get_result = get_result
        self.added: list[Any] = []

    async def exec(self, _query: Any) -> _StubAsyncResult:
        return _StubAsyncResult(self._exec_result)

    async def get(self, _model: Any, _pk: Any) -> Any:
        return self._get_result

    def add(self, obj: Any) -> None:
        self.added.append(obj)


def _build_request(
    *,
    authorization: str | None,
    path: str = "/api/v1/partner/me",
    ip: str = "203.0.113.55",
) -> SimpleNamespace:
    headers = {"Authorization": authorization} if authorization else {}
    return SimpleNamespace(
        headers=headers,
        client=SimpleNamespace(host=ip),
        url=SimpleNamespace(path=path),
        method="GET",
        state=SimpleNamespace(),
    )


def _make_api_key(
    *,
    secret: str,
    scopes: list[str],
    revoked_at: datetime | None = None,
    rate_limit_override: int | None = None,
) -> SimpleNamespace:
    """Build a stand-in PartnerApiKey row with a real PBKDF2 hash."""
    return SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        key_id=f"keyid-{uuid4().hex[:8]}",
        key_hash=hash_partner_secret(secret),
        scopes=list(scopes),
        label="test key",
        created_by=uuid4(),
        rate_limit_override=rate_limit_override,
        created_at=datetime.now(timezone.utc),
        last_used_at=None,
        revoked_at=revoked_at,
        revoked_reason=None,
    )


@pytest.fixture(autouse=True)
def _swap_limiter(monkeypatch: pytest.MonkeyPatch) -> _RecordingLimiter:
    """Replace the IP brute-force limiter with a recording stub on every test."""
    limiter = _RecordingLimiter()
    monkeypatch.setattr(partner_auth, "partner_auth_limiter", limiter)
    return limiter


# === Failure modes ========================================================


@pytest.mark.asyncio
async def test_missing_authorization_header_returns_401() -> None:
    request = _build_request(authorization=None)
    session = _StubSession()
    with pytest.raises(HTTPException) as exc_info:
        await partner_auth._resolve_partner_auth(request, None, session)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_non_bearer_scheme_returns_401() -> None:
    """Basic auth, raw token, etc. all fail without leaking which step rejected."""
    request = _build_request(authorization="Basic foo")
    session = _StubSession()
    with pytest.raises(HTTPException) as exc_info:
        await partner_auth._resolve_partner_auth(
            request, "Basic foo", session,  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_malformed_token_returns_401() -> None:
    """Bearer with non-vck_ prefix is rejected at parse step."""
    bad = "Bearer pak_legacy_token"
    request = _build_request(authorization=bad)
    session = _StubSession()
    with pytest.raises(HTTPException) as exc_info:
        await partner_auth._resolve_partner_auth(request, bad, session)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_unknown_key_id_returns_401() -> None:
    """Well-formed token whose key_id has no DB row → 401."""
    token, _, _ = generate_partner_token()
    request = _build_request(authorization=f"Bearer {token}")
    session = _StubSession(exec_result=None)  # no DB row found
    with pytest.raises(HTTPException) as exc_info:
        await partner_auth._resolve_partner_auth(
            request, f"Bearer {token}", session,  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_bad_secret_for_known_key_id_returns_401() -> None:
    """Key found by key_id but secret half hash-mismatches → 401."""
    token, _, _ = generate_partner_token()
    # The DB has a key with a DIFFERENT secret than the one we send.
    api_key = _make_api_key(secret="totally-different-secret", scopes=["webhooks:manage"])
    session = _StubSession(exec_result=api_key)
    request = _build_request(authorization=f"Bearer {token}")
    with pytest.raises(HTTPException) as exc_info:
        await partner_auth._resolve_partner_auth(
            request, f"Bearer {token}", session,  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_revoked_key_returns_401() -> None:
    """Even with valid secret, revoked_at != None means 401."""
    token, _, secret = generate_partner_token()
    api_key = _make_api_key(
        secret=secret,
        scopes=["webhooks:manage"],
        revoked_at=datetime.now(timezone.utc),
    )
    session = _StubSession(exec_result=api_key)
    request = _build_request(authorization=f"Bearer {token}")
    with pytest.raises(HTTPException) as exc_info:
        await partner_auth._resolve_partner_auth(
            request, f"Bearer {token}", session,  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_orphan_key_with_missing_org_returns_401() -> None:
    """If FK-broken (org row deleted), defend against orphan with 401 + log."""
    token, _, secret = generate_partner_token()
    api_key = _make_api_key(secret=secret, scopes=["webhooks:manage"])
    session = _StubSession(exec_result=api_key, get_result=None)  # org lookup returns None
    request = _build_request(authorization=f"Bearer {token}")
    with pytest.raises(HTTPException) as exc_info:
        await partner_auth._resolve_partner_auth(
            request, f"Bearer {token}", session,  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_rate_limited_at_ip_returns_429(monkeypatch: pytest.MonkeyPatch) -> None:
    """IP-based brute-force limiter rejection surfaces as 429, not 401."""

    class _BlockAll:
        async def is_allowed(self, _key: str) -> bool:
            return False

    monkeypatch.setattr(partner_auth, "partner_auth_limiter", _BlockAll())
    token, _, _ = generate_partner_token()
    request = _build_request(authorization=f"Bearer {token}")
    session = _StubSession()
    with pytest.raises(HTTPException) as exc_info:
        await partner_auth._resolve_partner_auth(
            request, f"Bearer {token}", session,  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == 429


# === Success paths ========================================================


@pytest.mark.asyncio
async def test_valid_key_returns_context(_swap_limiter: _RecordingLimiter) -> None:
    """Happy path: valid token, active key, real org → PartnerAuthContext."""
    token, _, secret = generate_partner_token()
    api_key = _make_api_key(secret=secret, scopes=["webhooks:manage"])
    org = SimpleNamespace(id=api_key.organization_id, slug="test-org")
    session = _StubSession(exec_result=api_key, get_result=org)
    request = _build_request(authorization=f"Bearer {token}")

    ctx = await partner_auth._resolve_partner_auth(
        request, f"Bearer {token}", session,  # type: ignore[arg-type]
    )

    assert ctx.api_key is api_key
    assert ctx.organization is org
    # Limiter must have been consulted.
    assert _swap_limiter.keys == ["203.0.113.55"]
    # request.state stashes the context for downstream rate-limit dep.
    assert request.state.partner_auth is ctx


@pytest.mark.asyncio
async def test_last_used_at_touched_on_success() -> None:
    """Successful auth bumps last_used_at + adds key to session for commit."""
    token, _, secret = generate_partner_token()
    api_key = _make_api_key(secret=secret, scopes=["webhooks:manage"])
    org = SimpleNamespace(id=api_key.organization_id)
    session = _StubSession(exec_result=api_key, get_result=org)
    request = _build_request(authorization=f"Bearer {token}")

    assert api_key.last_used_at is None
    await partner_auth._resolve_partner_auth(
        request, f"Bearer {token}", session,  # type: ignore[arg-type]
    )
    assert api_key.last_used_at is not None
    assert api_key in session.added


# === Scope enforcement (via the factory) ==================================


@pytest.mark.asyncio
async def test_identity_read_dep_short_circuits_scope_check() -> None:
    """identity:read is always granted — works even when scopes list is empty."""
    token, _, secret = generate_partner_token()
    api_key = _make_api_key(secret=secret, scopes=[])  # NO scopes granted
    org = SimpleNamespace(id=api_key.organization_id)
    session = _StubSession(exec_result=api_key, get_result=org)
    request = _build_request(authorization=f"Bearer {token}")

    # Call the captured dep directly (matches what FastAPI would do).
    ctx = await partner_auth.require_partner_identity_read(
        request=request,  # type: ignore[arg-type]
        authorization=f"Bearer {token}",
        session=session,  # type: ignore[arg-type]
    )
    assert ctx.api_key is api_key


@pytest.mark.asyncio
async def test_webhooks_manage_dep_accepts_granted_scope() -> None:
    token, _, secret = generate_partner_token()
    api_key = _make_api_key(secret=secret, scopes=["webhooks:manage"])
    org = SimpleNamespace(id=api_key.organization_id)
    session = _StubSession(exec_result=api_key, get_result=org)
    request = _build_request(authorization=f"Bearer {token}")

    ctx = await partner_auth.require_partner_webhooks_manage(
        request=request,  # type: ignore[arg-type]
        authorization=f"Bearer {token}",
        session=session,  # type: ignore[arg-type]
    )
    assert ctx.api_key is api_key


@pytest.mark.asyncio
async def test_webhooks_manage_dep_rejects_missing_scope() -> None:
    """Key without webhooks:manage scope → 403."""
    token, _, secret = generate_partner_token()
    # Has identity:read implicitly but NOT webhooks:manage.
    api_key = _make_api_key(secret=secret, scopes=[])
    org = SimpleNamespace(id=api_key.organization_id)
    session = _StubSession(exec_result=api_key, get_result=org)
    request = _build_request(authorization=f"Bearer {token}")

    with pytest.raises(HTTPException) as exc_info:
        await partner_auth.require_partner_webhooks_manage(
            request=request,  # type: ignore[arg-type]
            authorization=f"Bearer {token}",
            session=session,  # type: ignore[arg-type]
        )
    assert exc_info.value.status_code == 403


# === Logging hygiene =====================================================


@pytest.mark.asyncio
async def test_invalid_token_logs_prefix_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failed auth logs the token *prefix* (first 6 chars), never the full secret."""
    captured: list[tuple[str, tuple[object, ...]]] = []

    def _capture(message: str, *args: object, **_: object) -> None:
        captured.append((message, args))

    monkeypatch.setattr(partner_auth.logger, "warning", _capture)
    bad_token = "Bearer vck_thisisasecretthatshouldnotleak_morestuffhere"
    request = _build_request(authorization=bad_token)
    session = _StubSession(exec_result=None)  # key_id not found

    with pytest.raises(HTTPException):
        await partner_auth._resolve_partner_auth(
            request, bad_token, session,  # type: ignore[arg-type]
        )

    # At least one warning must have been logged.
    assert captured, "expected at least one warning log"
    # Token prefix in args is the FIRST 6 chars of the raw token (without "Bearer ").
    full_token = "vck_thisisasecretthatshouldnotleak_morestuffhere"
    for _msg, args in captured:
        for arg in args:
            if isinstance(arg, str):
                # The full token must NEVER appear in a log line.
                assert full_token not in arg, f"full token leaked in log arg: {arg!r}"
