# ruff: noqa: INP001
"""Integration tests for ``GET /api/v1/partner/me``.

Builds a minimal FastAPI app with just the partner router, overrides the
auth dep to return a stub ``PartnerAuthContext``, and exercises the route
via ``httpx.AsyncClient``. Same pattern as ``test_auth_bootstrap_api.py``.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.partner import router as partner_router
from app.core import partner_auth
from app.core.partner_auth import PartnerAuthContext


def _build_test_app(*, ctx: PartnerAuthContext | None) -> FastAPI:
    """Build a stripped-down FastAPI app mounting only the partner router."""
    app = FastAPI()
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(partner_router)
    app.include_router(api_v1)

    async def _override_require_identity() -> PartnerAuthContext:
        if ctx is None:
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        return ctx

    async def _override_rate_limit() -> None:
        return None

    # Per feedback_capture_factory_deps_for_test_override.md — overrides
    # MUST target the module-level captured callable, not the factory.
    app.dependency_overrides[partner_auth.require_partner_identity_read] = (
        _override_require_identity
    )
    app.dependency_overrides[partner_auth.check_partner_rate_limit] = (
        _override_rate_limit
    )
    return app


def _make_ctx(
    *,
    scopes: list[str],
    rate_limit_override: int | None = None,
    slug: str = "test-partner-org",
) -> PartnerAuthContext:
    org_id = uuid4()
    api_key = SimpleNamespace(
        id=uuid4(),
        organization_id=org_id,
        key_id="kid_abc123",
        scopes=list(scopes),
        rate_limit_override=rate_limit_override,
    )
    organization = SimpleNamespace(id=org_id, slug=slug)
    return PartnerAuthContext(api_key=api_key, organization=organization)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_me_returns_identity_payload() -> None:
    ctx = _make_ctx(scopes=["webhooks:manage", "identity:read"])
    app = _build_test_app(ctx=ctx)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/partner/me")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["partner_org"] == "test-partner-org"
    assert payload["key_id"] == "kid_abc123"
    assert sorted(payload["scopes"]) == ["identity:read", "webhooks:manage"]
    assert payload["rate_limit_per_minute"] == 600  # default ceiling


@pytest.mark.asyncio
async def test_me_falls_back_to_org_uuid_when_slug_missing() -> None:
    """Orgs without a slug surface their UUID instead. Defensive fallback."""
    ctx = _make_ctx(scopes=["identity:read"], slug="")
    app = _build_test_app(ctx=ctx)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/partner/me")

    assert resp.status_code == 200
    payload = resp.json()
    # partner_org falls back to str(organization.id) when slug is empty
    assert payload["partner_org"] == str(ctx.organization.id)


@pytest.mark.asyncio
async def test_me_surfaces_rate_limit_override() -> None:
    """When key has rate_limit_override, /me reports that value, not the default."""
    ctx = _make_ctx(
        scopes=["webhooks:manage"],
        rate_limit_override=2000,
    )
    app = _build_test_app(ctx=ctx)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/partner/me")

    assert resp.status_code == 200
    assert resp.json()["rate_limit_per_minute"] == 2000


@pytest.mark.asyncio
async def test_me_rejects_unauthenticated_requests() -> None:
    """No auth context → 401 (the override returns None to simulate failed auth)."""
    app = _build_test_app(ctx=None)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/partner/me")

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_does_not_leak_key_hash_or_secret() -> None:
    """The /me response must NOT include the hash, secret, or any sensitive field.

    Defensive test against future regressions where a developer adds the
    full PartnerApiKey object to the response. Schema is whitelist-style
    so this should be impossible, but the test locks the invariant.
    """
    ctx = _make_ctx(scopes=["webhooks:manage", "identity:read"])
    # Decorate the api_key with sentinel-prefixed fields so any field that
    # slips through with the prefix is detectable in the response body.
    ctx.api_key.key_hash = "SENSITIVE_HASH_VALUE_DO_NOT_LEAK"
    ctx.api_key.revoked_at = None
    ctx.api_key.label = "internal label not for partners"

    app = _build_test_app(ctx=ctx)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        resp = await client.get("/api/v1/partner/me")

    assert resp.status_code == 200
    body = resp.text
    assert "SENSITIVE_HASH_VALUE_DO_NOT_LEAK" not in body
    assert "internal label not for partners" not in body
    # Allowed top-level keys are exactly the schema fields.
    allowed = {"partner_org", "key_id", "scopes", "rate_limit_per_minute"}
    assert set(resp.json().keys()) == allowed
