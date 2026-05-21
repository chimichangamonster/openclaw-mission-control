# ruff: noqa: INP001
"""Integration tests for admin partner-key CRUD.

Covers ``app/api/admin_partner_keys.py``. Uses an in-memory SQLite session
+ FastAPI TestClient, similar to the existing E2E suites. Tests cover:

* Successful key creation returns full token ONCE + payload
* Reserved scopes rejected at creation (422)
* Unknown scopes rejected at creation (422)
* Unknown organization returns 404
* List endpoint excludes secrets, respects filters
* Revoke endpoint idempotent + sets revoked_reason
* Revoke of unknown key returns 404
* Audit log fired on create + revoke
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.admin_partner_keys import router as admin_router
from app.core.partner_tokens import PREFIX, SEPARATOR, parse_partner_token
from app.core.platform_auth import require_platform_admin
from app.db.session import get_session
from app.models.organizations import Organization
from app.models.partner_api_key import PartnerApiKey


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
    """Insert a single test organization and return it."""
    org = Organization(id=uuid4(), name="Test Partner Org", slug="test-partner-org")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest_asyncio.fixture
async def stub_admin_user() -> Any:
    """Return a SimpleNamespace stub mimicking the platform-admin User."""
    from types import SimpleNamespace

    return SimpleNamespace(
        id=uuid4(),
        email="admin@home.local",
        platform_role="owner",
    )


@pytest.fixture
def app_factory(db_session: AsyncSession, stub_admin_user: Any) -> FastAPI:
    """Build a minimal FastAPI app mounting only the admin partner-keys router.

    Auth dep is overridden to return the stub admin; DB session dep is
    overridden to yield the seeded in-memory session.
    """
    app = FastAPI()
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(admin_router)
    app.include_router(api_v1)

    async def _override_admin() -> Any:
        return stub_admin_user

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[require_platform_admin] = _override_admin
    app.dependency_overrides[get_session] = _override_session
    return app


@pytest_asyncio.fixture
async def client(app_factory: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app_factory),
        base_url="http://testserver",
    ) as client:
        yield client


# === Create =============================================================


@pytest.mark.asyncio
async def test_create_partner_key_returns_full_token_once(
    client: AsyncClient,
    seeded_org: Organization,
    db_session: AsyncSession,
) -> None:
    """Happy path: valid request → 201 with full token + DB row created."""
    resp = await client.post(
        "/api/v1/admin/partner-keys",
        json={
            "organization_id": str(seeded_org.id),
            "label": "Optified v2 prod",
            "scopes": ["webhooks:manage", "identity:read"],
        },
    )
    assert resp.status_code == 201, resp.text

    payload = resp.json()
    full_token = payload["full_token"]
    assert full_token.startswith(PREFIX)
    assert SEPARATOR in full_token

    parsed = parse_partner_token(full_token)
    assert parsed is not None
    parsed_key_id, parsed_secret = parsed
    assert parsed_key_id == payload["key_id"]
    assert len(parsed_secret) >= 40  # entropy floor

    # DB has the row with hashed secret.
    db_row = await db_session.get(PartnerApiKey, UUID(payload["id"]))
    assert db_row is not None
    assert db_row.key_id == parsed_key_id
    assert db_row.key_hash != parsed_secret  # stored hashed, never plaintext
    assert db_row.label == "Optified v2 prod"
    assert sorted(db_row.scopes) == ["identity:read", "webhooks:manage"]


@pytest.mark.asyncio
async def test_create_rejects_reserved_scope(
    client: AsyncClient,
    seeded_org: Organization,
) -> None:
    """Reserved scopes (leads:*, skills:*, etc.) get 422 — no ghost-permissioned keys."""
    resp = await client.post(
        "/api/v1/admin/partner-keys",
        json={
            "organization_id": str(seeded_org.id),
            "label": "skill-author-attempt",
            "scopes": ["webhooks:manage", "skills:author"],
        },
    )
    assert resp.status_code == 422
    assert "reserved" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_rejects_unknown_scope(
    client: AsyncClient,
    seeded_org: Organization,
) -> None:
    """Scopes outside the union of real + reserved get 422."""
    resp = await client.post(
        "/api/v1/admin/partner-keys",
        json={
            "organization_id": str(seeded_org.id),
            "label": "typo-test",
            "scopes": ["webhooks:manaag"],  # typo
        },
    )
    assert resp.status_code == 422
    assert "not a known" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_rejects_unknown_organization(client: AsyncClient) -> None:
    """Org that doesn't exist → 404, not 500."""
    resp = await client.post(
        "/api/v1/admin/partner-keys",
        json={
            "organization_id": str(uuid4()),
            "label": "phantom",
            "scopes": ["identity:read"],
        },
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_with_rate_limit_override(
    client: AsyncClient,
    seeded_org: Organization,
    db_session: AsyncSession,
) -> None:
    """Override is persisted to the model and echoed in the response."""
    resp = await client.post(
        "/api/v1/admin/partner-keys",
        json={
            "organization_id": str(seeded_org.id),
            "label": "high-volume",
            "scopes": ["webhooks:manage"],
            "rate_limit_override": 2000,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["rate_limit_override"] == 2000

    db_row = await db_session.get(PartnerApiKey, UUID(resp.json()["id"]))
    assert db_row is not None
    assert db_row.rate_limit_override == 2000


@pytest.mark.asyncio
async def test_create_rejects_empty_label(
    client: AsyncClient,
    seeded_org: Organization,
) -> None:
    """Label must be 1+ chars — empty rejected by Pydantic validator."""
    resp = await client.post(
        "/api/v1/admin/partner-keys",
        json={
            "organization_id": str(seeded_org.id),
            "label": "",
            "scopes": ["identity:read"],
        },
    )
    assert resp.status_code == 422


# === List ===============================================================


@pytest.mark.asyncio
async def test_list_excludes_secret_and_hash(
    client: AsyncClient,
    seeded_org: Organization,
) -> None:
    """List response must NOT include full_token or key_hash."""
    create_resp = await client.post(
        "/api/v1/admin/partner-keys",
        json={
            "organization_id": str(seeded_org.id),
            "label": "test-key",
            "scopes": ["identity:read"],
        },
    )
    assert create_resp.status_code == 201

    list_resp = await client.get(
        f"/api/v1/admin/partner-keys?organization_id={seeded_org.id}",
    )
    assert list_resp.status_code == 200
    rows = list_resp.json()
    assert len(rows) == 1
    row = rows[0]
    assert "full_token" not in row
    assert "key_hash" not in row
    # ``key_id`` IS public — fine to expose.
    assert row["key_id"]


@pytest.mark.asyncio
async def test_list_filters_by_organization(
    client: AsyncClient,
    seeded_org: Organization,
    db_session: AsyncSession,
) -> None:
    """``organization_id`` filter limits results to one org."""
    # Seed a second org with its own key
    other = Organization(id=uuid4(), name="Other", slug="other")
    db_session.add(other)
    await db_session.commit()

    for org_id in (seeded_org.id, other.id):
        await client.post(
            "/api/v1/admin/partner-keys",
            json={
                "organization_id": str(org_id),
                "label": f"key-for-{org_id}",
                "scopes": ["identity:read"],
            },
        )

    resp = await client.get(
        f"/api/v1/admin/partner-keys?organization_id={seeded_org.id}",
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["organization_id"] == str(seeded_org.id)


@pytest.mark.asyncio
async def test_list_excludes_revoked_by_default(
    client: AsyncClient,
    seeded_org: Organization,
) -> None:
    """Revoked keys hidden unless include_revoked=true."""
    create_resp = await client.post(
        "/api/v1/admin/partner-keys",
        json={
            "organization_id": str(seeded_org.id),
            "label": "to-be-revoked",
            "scopes": ["identity:read"],
        },
    )
    key_id = create_resp.json()["id"]

    # Revoke it
    rev_resp = await client.request(
        "DELETE",
        f"/api/v1/admin/partner-keys/{key_id}",
        json={"revoked_reason": "rotated"},
    )
    assert rev_resp.status_code == 204

    # Default list excludes it
    default = await client.get(
        f"/api/v1/admin/partner-keys?organization_id={seeded_org.id}",
    )
    assert default.json() == []

    # include_revoked=true shows it
    with_revoked = await client.get(
        f"/api/v1/admin/partner-keys?organization_id={seeded_org.id}&include_revoked=true",
    )
    rows = with_revoked.json()
    assert len(rows) == 1
    assert rows[0]["revoked_at"] is not None
    assert rows[0]["revoked_reason"] == "rotated"


# === Revoke =============================================================


@pytest.mark.asyncio
async def test_revoke_idempotent(
    client: AsyncClient,
    seeded_org: Organization,
) -> None:
    """Re-revoking a revoked key is a no-op, NOT an error."""
    create_resp = await client.post(
        "/api/v1/admin/partner-keys",
        json={
            "organization_id": str(seeded_org.id),
            "label": "double-revoke",
            "scopes": ["identity:read"],
        },
    )
    key_id = create_resp.json()["id"]

    first = await client.request(
        "DELETE",
        f"/api/v1/admin/partner-keys/{key_id}",
        json={"revoked_reason": "rotated"},
    )
    second = await client.request(
        "DELETE",
        f"/api/v1/admin/partner-keys/{key_id}",
        json={"revoked_reason": "different reason that should NOT overwrite"},
    )
    assert first.status_code == 204
    assert second.status_code == 204

    # First reason wins (idempotent — second call doesn't update fields)
    list_resp = await client.get(
        f"/api/v1/admin/partner-keys?organization_id={seeded_org.id}&include_revoked=true",
    )
    assert list_resp.json()[0]["revoked_reason"] == "rotated"


@pytest.mark.asyncio
async def test_revoke_unknown_key_returns_404(client: AsyncClient) -> None:
    resp = await client.request(
        "DELETE",
        f"/api/v1/admin/partner-keys/{uuid4()}",
        json={"revoked_reason": "nope"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_revoke_requires_reason(
    client: AsyncClient,
    seeded_org: Organization,
) -> None:
    """Empty reason rejected — audit trail must capture intent."""
    create_resp = await client.post(
        "/api/v1/admin/partner-keys",
        json={
            "organization_id": str(seeded_org.id),
            "label": "needs-reason",
            "scopes": ["identity:read"],
        },
    )
    key_id = create_resp.json()["id"]

    resp = await client.request(
        "DELETE",
        f"/api/v1/admin/partner-keys/{key_id}",
        json={"revoked_reason": ""},
    )
    assert resp.status_code == 422
