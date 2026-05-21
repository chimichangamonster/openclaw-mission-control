# ruff: noqa: INP001
"""Integration tests for partner webhook subscription CRUD.

Covers ``app/api/partner.py`` (webhook endpoints) plus the SSRF defense in
``app/services/partner_webhook_url_validation.py``. Uses an in-memory SQLite
session + FastAPI TestClient, mirroring ``test_admin_partner_keys.py``.

Tests target Step 5 of the Partner API v1 implementation order (model +
endpoints + SSRF + secret-return-once invariant). Dispatch + DNS-rebinding
at fire time + failures audit ship in Steps 6-7 with their own coverage.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.partner import router as partner_router
from app.core import partner_auth
from app.core.partner_auth import PartnerAuthContext
from app.core.partner_tokens import verify_partner_secret
from app.db.session import get_session
from app.models.organizations import Organization
from app.models.partner_webhook_subscription import PartnerWebhookSubscription
from app.services import partner_webhook_url_validation
from app.services.partner_webhook_url_validation import (
    WebhookUrlValidationError,
    _is_forbidden_ip,
    validate_webhook_url_at_create_time,
)


# === Fixtures ===========================================================


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Fresh in-memory SQLite session per test, with all SQLModel tables created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded_org(db_session: AsyncSession) -> Organization:
    org = Organization(id=uuid4(), name="Test Partner Org", slug="test-partner-org")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


def _make_ctx(org: Organization, scopes: list[str]) -> PartnerAuthContext:
    """Build a stub PartnerAuthContext with the given scopes."""
    api_key = SimpleNamespace(
        id=uuid4(),
        organization_id=org.id,
        key_id="kid_test123",
        scopes=list(scopes),
        rate_limit_override=None,
    )
    return PartnerAuthContext(api_key=api_key, organization=org)  # type: ignore[arg-type]


@pytest.fixture
def app_factory(
    db_session: AsyncSession,
    seeded_org: Organization,
    monkeypatch: pytest.MonkeyPatch,
) -> FastAPI:
    """Build a minimal FastAPI app mounting the partner router with:

    * webhooks:manage scope on the auth context (default — overridden per test)
    * SSRF validator monkeypatched to bypass real DNS by default; tests that
      exercise URL validation enable specific behaviors via the monkeypatch.
    """
    app = FastAPI()
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(partner_router)
    app.include_router(api_v1)

    ctx = _make_ctx(seeded_org, scopes=["webhooks:manage", "identity:read"])

    async def _override_require_webhooks() -> PartnerAuthContext:
        return ctx

    async def _override_require_identity() -> PartnerAuthContext:
        return ctx

    async def _override_rate_limit() -> None:
        return None

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[partner_auth.require_partner_webhooks_manage] = (
        _override_require_webhooks
    )
    app.dependency_overrides[partner_auth.require_partner_identity_read] = (
        _override_require_identity
    )
    app.dependency_overrides[partner_auth.check_partner_rate_limit] = (
        _override_rate_limit
    )
    app.dependency_overrides[get_session] = _override_session

    # Stash the context on the app for tests that need to flip scopes/org.
    app.state.partner_ctx = ctx  # type: ignore[attr-defined]

    # Default: skip real DNS in the SSRF validator. Tests that exercise the
    # rejection paths use their own helpers that don't depend on this.
    monkeypatch.setattr(
        partner_webhook_url_validation,
        "_resolve_all",
        lambda hostname: ["93.184.216.34"],  # example.com public IP
    )

    return app


@pytest_asyncio.fixture
async def client(app_factory: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app_factory),
        base_url="http://testserver",
    ) as ac:
        yield ac


# === Create =============================================================


@pytest.mark.asyncio
async def test_create_returns_secret_once(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """POST /webhooks returns the plaintext secret ONCE; DB stores only the hash."""
    resp = await client.post(
        "/api/v1/partner/webhooks",
        json={"url": "https://partner.example.com/vc-events", "events": []},
    )
    assert resp.status_code == 201, resp.text

    payload = resp.json()
    assert payload["secret"].startswith("whsec_")
    assert payload["id"].startswith("wh_")
    assert payload["active"] is True
    assert payload["consecutive_failures"] == 0
    assert payload["url"] == "https://partner.example.com/vc-events"
    assert payload["events"] == []

    # DB row exists with secret_hash (not the plaintext).
    rows = (await db_session.exec(select(PartnerWebhookSubscription))).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.secret_hash != payload["secret"]
    # The stored hash actually verifies against the plaintext secret.
    assert verify_partner_secret(payload["secret"], row.secret_hash)


@pytest.mark.asyncio
async def test_create_with_events(client: AsyncClient) -> None:
    """``events`` list round-trips through the create response."""
    resp = await client.post(
        "/api/v1/partner/webhooks",
        json={
            "url": "https://partner.example.com/hooks",
            "events": ["vc.test.ping"],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["events"] == ["vc.test.ping"]


@pytest.mark.asyncio
async def test_create_rejects_http_scheme(client: AsyncClient) -> None:
    """HTTP rejected at create time — partner-facing webhooks must be HTTPS."""
    resp = await client.post(
        "/api/v1/partner/webhooks",
        json={"url": "http://partner.example.com/hooks", "events": []},
    )
    assert resp.status_code == 422
    assert "https" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_rejects_loopback_ip_literal(client: AsyncClient) -> None:
    """``https://127.0.0.1/...`` rejected — loopback never legitimate."""
    resp = await client.post(
        "/api/v1/partner/webhooks",
        json={"url": "https://127.0.0.1/hooks", "events": []},
    )
    assert resp.status_code == 422
    assert "forbidden" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_rejects_rfc1918_ip_literal(client: AsyncClient) -> None:
    """RFC1918 private IP literal rejected."""
    resp = await client.post(
        "/api/v1/partner/webhooks",
        json={"url": "https://192.168.1.42/hooks", "events": []},
    )
    assert resp.status_code == 422
    assert "forbidden" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_rejects_localhost_hostname(client: AsyncClient) -> None:
    """Literal ``localhost`` hostname rejected without DNS resolution."""
    resp = await client.post(
        "/api/v1/partner/webhooks",
        json={"url": "https://localhost/hooks", "events": []},
    )
    assert resp.status_code == 422
    assert "internal" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_rejects_internal_suffix(client: AsyncClient) -> None:
    """``.internal`` suffix rejected — common internal-DNS convention."""
    resp = await client.post(
        "/api/v1/partner/webhooks",
        json={"url": "https://partner.internal/hooks", "events": []},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_when_dns_resolves_to_private(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hostname that DNS-resolves to a private IP is rejected at create time."""
    monkeypatch.setattr(
        partner_webhook_url_validation,
        "_resolve_all",
        lambda hostname: ["10.0.0.5"],  # private despite public-looking hostname
    )
    resp = await client.post(
        "/api/v1/partner/webhooks",
        json={"url": "https://attacker.example.com/hooks", "events": []},
    )
    assert resp.status_code == 422
    assert "forbidden" in resp.json()["detail"].lower()


# === Read ===============================================================


@pytest.mark.asyncio
async def test_list_returns_own_subscriptions_only(
    app_factory: FastAPI,
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """List endpoint is org-scoped — never includes other orgs' subscriptions."""
    # Create one under the calling org
    create = await client.post(
        "/api/v1/partner/webhooks",
        json={"url": "https://partner.example.com/hooks", "events": []},
    )
    assert create.status_code == 201

    # Seed a second org with a foreign subscription directly in DB.
    other_org = Organization(id=uuid4(), name="Other", slug="other")
    foreign_sub = PartnerWebhookSubscription(
        organization_id=other_org.id,
        url="https://other.example.com/hooks",
        events=[],
        secret_hash="dummy",
    )
    db_session.add(other_org)
    db_session.add(foreign_sub)
    await db_session.commit()

    resp = await client.get("/api/v1/partner/webhooks")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["url"] == "https://partner.example.com/hooks"
    # secret never appears in list responses
    assert "secret" not in rows[0]


@pytest.mark.asyncio
async def test_list_excludes_secret_field(client: AsyncClient) -> None:
    """Read shape must not include the HMAC secret under any name."""
    create = await client.post(
        "/api/v1/partner/webhooks",
        json={"url": "https://partner.example.com/hooks", "events": []},
    )
    assert create.status_code == 201
    plaintext_secret = create.json()["secret"]

    resp = await client.get("/api/v1/partner/webhooks")
    assert resp.status_code == 200
    body = resp.text
    assert plaintext_secret not in body
    assert "secret_hash" not in body
    assert "secret" not in resp.json()[0]


# === Delete =============================================================


@pytest.mark.asyncio
async def test_delete_removes_own_subscription(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    create = await client.post(
        "/api/v1/partner/webhooks",
        json={"url": "https://partner.example.com/hooks", "events": []},
    )
    assert create.status_code == 201
    sub_id = create.json()["id"]
    assert sub_id.startswith("wh_")

    resp = await client.delete(f"/api/v1/partner/webhooks/{sub_id}")
    assert resp.status_code == 204

    remaining = (await db_session.exec(select(PartnerWebhookSubscription))).all()
    assert remaining == []


@pytest.mark.asyncio
async def test_delete_other_orgs_subscription_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Cross-org deletion attempt returns 404 — no existence leak."""
    other_org = Organization(id=uuid4(), name="Other", slug="other")
    foreign_sub = PartnerWebhookSubscription(
        organization_id=other_org.id,
        url="https://other.example.com/hooks",
        events=[],
        secret_hash="dummy",
    )
    db_session.add(other_org)
    db_session.add(foreign_sub)
    await db_session.commit()
    await db_session.refresh(foreign_sub)

    resp = await client.delete(f"/api/v1/partner/webhooks/wh_{foreign_sub.id}")
    assert resp.status_code == 404

    # Foreign subscription is still in DB.
    still_there = await db_session.get(PartnerWebhookSubscription, foreign_sub.id)
    assert still_there is not None


@pytest.mark.asyncio
async def test_delete_malformed_id_returns_404(client: AsyncClient) -> None:
    """Non-``wh_<uuid>`` IDs return 404, not 422 — same as unknown subscription."""
    resp = await client.delete("/api/v1/partner/webhooks/not-a-valid-id")
    assert resp.status_code == 404

    # wh_ prefix but garbage suffix also 404.
    resp2 = await client.delete("/api/v1/partner/webhooks/wh_not-a-uuid")
    assert resp2.status_code == 404


# === Scope enforcement ==================================================


@pytest.mark.asyncio
async def test_webhook_endpoints_require_webhooks_manage_scope(
    db_session: AsyncSession,
    seeded_org: Organization,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A key with only identity:read cannot reach webhook endpoints.

    Builds an app where the auth dep raises 403 to simulate scope mismatch
    (mirrors what the real ``_require_partner_key`` does on missing scope).
    """
    from fastapi import HTTPException, status

    app = FastAPI()
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(partner_router)
    app.include_router(api_v1)

    async def _deny_webhooks() -> PartnerAuthContext:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    async def _allow_identity() -> PartnerAuthContext:
        return _make_ctx(seeded_org, scopes=["identity:read"])

    async def _no_rate_limit() -> None:
        return None

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[partner_auth.require_partner_webhooks_manage] = (
        _deny_webhooks
    )
    app.dependency_overrides[partner_auth.require_partner_identity_read] = (
        _allow_identity
    )
    app.dependency_overrides[partner_auth.check_partner_rate_limit] = _no_rate_limit
    app.dependency_overrides[get_session] = _session

    monkeypatch.setattr(
        partner_webhook_url_validation,
        "_resolve_all",
        lambda hostname: ["93.184.216.34"],
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        # /me still works (identity:read).
        me = await ac.get("/api/v1/partner/me")
        assert me.status_code == 200

        # Webhook endpoints are 403'd.
        create = await ac.post(
            "/api/v1/partner/webhooks",
            json={"url": "https://partner.example.com/hooks", "events": []},
        )
        assert create.status_code == 403

        listing = await ac.get("/api/v1/partner/webhooks")
        assert listing.status_code == 403


# === URL validation helper unit tests ===================================


def test_is_forbidden_ip_covers_loopback_rfc1918_link_local() -> None:
    assert _is_forbidden_ip("127.0.0.1")
    assert _is_forbidden_ip("10.0.0.1")
    assert _is_forbidden_ip("172.16.5.5")
    assert _is_forbidden_ip("192.168.1.1")
    assert _is_forbidden_ip("169.254.5.5")
    assert _is_forbidden_ip("::1")


def test_is_forbidden_ip_covers_cgnat_and_tailscale() -> None:
    """CGNAT 100.64/10 (incl. Tailscale tailnet IPv4) + Tailscale IPv6 ULA."""
    assert _is_forbidden_ip("100.64.0.1")
    assert _is_forbidden_ip("100.127.255.254")
    assert _is_forbidden_ip("fd7a:115c:a1e0::1")


def test_is_forbidden_ip_allows_legitimate_public_addresses() -> None:
    """Sanity check that real public addresses pass."""
    assert not _is_forbidden_ip("93.184.216.34")  # example.com
    assert not _is_forbidden_ip("8.8.8.8")  # Google DNS
    assert not _is_forbidden_ip("2606:4700:4700::1111")  # Cloudflare public v6


def test_validate_webhook_url_rejects_userinfo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """URLs with embedded credentials are rejected — they can mask SSRF intent."""
    monkeypatch.setattr(
        partner_webhook_url_validation,
        "_resolve_all",
        lambda hostname: ["93.184.216.34"],
    )
    with pytest.raises(WebhookUrlValidationError) as excinfo:
        validate_webhook_url_at_create_time(
            "https://user:pass@partner.example.com/hooks",
        )
    assert "userinfo" in excinfo.value.reason
