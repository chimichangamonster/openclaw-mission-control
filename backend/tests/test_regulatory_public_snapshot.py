# ruff: noqa: INP001
"""HTTP tests for the public snapshot endpoints (item 101 v2 Phase 1b.2).

Covers:
- POST /regulatory/snapshot/public/rotate-token (admin+, returns new token)
- GET  /regulatory/snapshot/public/{token} (unauthenticated)
- Token rotation invalidates the previous token
- Wrong/missing token returns 404 (not 401 — token IS the credential)
- Returned snapshot is scoped to the token-owning org only
- Other-org streams/phases/tasks never leak into the response

Important: the public snapshot endpoint must NOT require auth headers,
gateway membership, or feature-flag enforcement at the request layer
(it's the public-marketing-site surface). The token IS the only credential.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import (
    check_org_rate_limit,
    get_session,
    require_org_from_actor,
    require_org_member,
)
from app.api.regulatory import REGULATORY_FEATURE_GATE
from app.api.regulatory import router as regulatory_router
from app.api.regulatory_public import router as regulatory_public_router
from app.models.organization_members import OrganizationMember
from app.models.organization_settings import OrganizationSettings
from app.models.organizations import Organization
from app.models.regulatory import (
    RegulatoryCountry,
    RegulatoryPhase,
    RegulatoryStream,
    RegulatoryTask,
)
from app.services.organizations import OrganizationContext

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


ORG_A_ID = uuid4()
ORG_B_ID = uuid4()
USER_A_ID = uuid4()
USER_B_ID = uuid4()


def _ctx(org: Organization, member: OrganizationMember) -> OrganizationContext:
    return OrganizationContext(organization=org, member=member)


async def _make_engine() -> Any:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


async def _seed(session: AsyncSession) -> dict[str, Any]:
    """Seed two orgs with parallel regulatory data so snapshot scoping is
    actually testable."""
    org_a = Organization(id=ORG_A_ID, name="Org A", slug="org-a")
    org_b = Organization(id=ORG_B_ID, name="Org B", slug="org-b")
    admin_a = OrganizationMember(
        id=uuid4(), organization_id=ORG_A_ID, user_id=USER_A_ID, role="admin"
    )
    member_a = OrganizationMember(
        id=uuid4(), organization_id=ORG_A_ID, user_id=uuid4(), role="member"
    )
    admin_b = OrganizationMember(
        id=uuid4(), organization_id=ORG_B_ID, user_id=USER_B_ID, role="admin"
    )
    settings_a = OrganizationSettings(
        id=uuid4(),
        organization_id=ORG_A_ID,
        regulatory_public_snapshot_token=None,
    )
    settings_b = OrganizationSettings(
        id=uuid4(),
        organization_id=ORG_B_ID,
        regulatory_public_snapshot_token=None,
    )
    session.add_all([org_a, org_b, admin_a, member_a, admin_b, settings_a, settings_b])
    await session.flush()

    # Org A regulatory data — Canada
    country_a = RegulatoryCountry(
        organization_id=ORG_A_ID,
        code="CA",
        name="Canada",
        status="active",
        display_label="Canada (A)",
    )
    stream_a = RegulatoryStream(
        organization_id=ORG_A_ID,
        slug="corporate",
        name="Corporate (A)",
        color_token="navy",
    )
    session.add_all([country_a, stream_a])
    await session.flush()
    phase_a = RegulatoryPhase(
        stream_id=stream_a.id,
        country_id=country_a.id,
        name="Incorporate (A)",
        badge_kind="corp",
    )
    session.add(phase_a)
    await session.flush()
    task_a = RegulatoryTask(phase_id=phase_a.id, body="NUANS (A)")
    session.add(task_a)

    # Org B regulatory data — also Canada
    country_b = RegulatoryCountry(
        organization_id=ORG_B_ID,
        code="CA",
        name="Canada",
        status="active",
        display_label="Canada (B)",
    )
    stream_b = RegulatoryStream(
        organization_id=ORG_B_ID,
        slug="corporate",
        name="Corporate (B)",
        color_token="navy",
    )
    session.add_all([country_b, stream_b])
    await session.flush()
    phase_b = RegulatoryPhase(
        stream_id=stream_b.id,
        country_id=country_b.id,
        name="Incorporate (B)",
        badge_kind="corp",
    )
    session.add(phase_b)
    await session.flush()
    task_b = RegulatoryTask(phase_id=phase_b.id, body="NUANS (B)")
    session.add(task_b)
    await session.commit()

    return {
        "org_a": org_a,
        "org_b": org_b,
        "admin_a": admin_a,
        "member_a": member_a,
        "admin_b": admin_b,
    }


@pytest_asyncio.fixture
async def env() -> AsyncIterator[dict[str, Any]]:
    engine = await _make_engine()
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        data = await _seed(session)
    yield {"maker": maker, "data": data}
    await engine.dispose()


def _make_app(maker: async_sessionmaker[AsyncSession], ctx: OrganizationContext) -> FastAPI:
    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(lifespan=_lifespan)
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(regulatory_router)
    api_v1.include_router(regulatory_public_router)
    app.include_router(api_v1)

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_org_member] = lambda: ctx
    app.dependency_overrides[require_org_from_actor] = lambda: ctx
    app.dependency_overrides[check_org_rate_limit] = lambda: None
    app.dependency_overrides[REGULATORY_FEATURE_GATE] = lambda: None
    return app


# ---------------------------------------------------------------------------
# Token rotation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_can_rotate_to_get_initial_token(env: dict[str, Any]) -> None:
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/regulatory/snapshot/public/rotate-token")
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body
    assert isinstance(body["token"], str)
    assert len(body["token"]) >= 32  # cryptographically meaningful


@pytest.mark.asyncio
async def test_member_role_cannot_rotate_token(env: dict[str, Any]) -> None:
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["member_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/regulatory/snapshot/public/rotate-token")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_rotation_invalidates_previous_token(env: dict[str, Any]) -> None:
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        first = await c.post("/api/v1/regulatory/snapshot/public/rotate-token")
        first_token = first.json()["token"]
        # First token works
        ok = await c.get(f"/api/v1/regulatory/snapshot/public/{first_token}")
        assert ok.status_code == 200
        # Rotate
        second = await c.post("/api/v1/regulatory/snapshot/public/rotate-token")
        second_token = second.json()["token"]
        assert second_token != first_token
        # Old token now 404s
        gone = await c.get(f"/api/v1/regulatory/snapshot/public/{first_token}")
        assert gone.status_code == 404
        # New token works
        new = await c.get(f"/api/v1/regulatory/snapshot/public/{second_token}")
        assert new.status_code == 200


# ---------------------------------------------------------------------------
# Public snapshot read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_token_returns_404(env: dict[str, Any]) -> None:
    """No auth headers required; the wrong-token branch must 404, not 401."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/regulatory/snapshot/public/not-a-real-token-abc123")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_snapshot_returns_only_token_owning_org_data(env: dict[str, Any]) -> None:
    """Org A's token returns Org A's data and ONLY Org A's data, even though
    Org B has a parallel-shaped Canada / Corporate / Incorporate / NUANS tree."""
    d = env["data"]
    # Rotate Org A's token
    app_a = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(
        transport=ASGITransport(app=app_a), base_url="http://test"
    ) as c:
        rotation = await c.post("/api/v1/regulatory/snapshot/public/rotate-token")
        token_a = rotation.json()["token"]
        snap = await c.get(f"/api/v1/regulatory/snapshot/public/{token_a}")
    assert snap.status_code == 200
    body = snap.json()
    # Returned country must be Canada (the only published country in v2)
    assert body["country"]["code"] == "CA"
    assert body["country"]["display_label"] == "Canada (A)"
    # Streams scoped to Org A only
    assert len(body["streams"]) == 1
    assert body["streams"][0]["name"] == "Corporate (A)"
    # Phases / tasks come from Org A only — never the (B) values
    flat_task_bodies: list[str] = []
    for stream in body["streams"]:
        for phase in stream["phases"]:
            for task in phase["tasks"]:
                flat_task_bodies.append(task["body"])
    assert flat_task_bodies == ["NUANS (A)"]
    # Defense-in-depth — no string from Org B leaks through anywhere
    serialized = snap.text
    assert "(B)" not in serialized


@pytest.mark.asyncio
async def test_snapshot_is_unauthenticated_no_dep_overrides_needed() -> None:
    """The public snapshot endpoint must not require any auth dependency.
    Build an app WITHOUT the require_org_member / actor / feature-gate overrides
    and confirm the GET still works (the wrong-token branch returns 404, not
    401 from missing auth)."""

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield

    engine = await _make_engine()
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as session:
        await _seed(session)

    app = FastAPI(lifespan=_lifespan)
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(regulatory_public_router)
    app.include_router(api_v1)

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/regulatory/snapshot/public/anything")
    assert resp.status_code == 404
    await engine.dispose()
