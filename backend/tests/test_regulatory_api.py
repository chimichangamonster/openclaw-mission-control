# ruff: noqa: INP001
"""HTTP-level tests for the regulatory tracker API (item 101 v2 Phase 1b.1).

These complement the ORM-level isolation tests in `test_regulatory_isolation.py`.
Both layers run side-by-side post-Phase-1b — the ORM tests lock the data-layer
contract (the right query shape returns the right rows), and these tests lock
the endpoint contract (the route enforces the contract via auth, role, and
same-org checks at FK boundaries).

Coverage focus per the conversation that scoped this file:
- Cross-org READ isolation (mirror of test_list_*_scoped_to_caller_org)
- Cross-org WRITE blocked at FK boundaries (Phase create, Task create) —
  mirror of test_phase_cannot_link_streams_from_different_orgs
- M2M same-org enforcement on TaskTag — the silent-leak surface
- Role gating: streams/tags admin-only; phases/tasks operator+
- Feature-flag gate: regulatory flag off → 403 across all routes

Tests that intentionally do NOT exist here:
- Full CRUD happy-path round-trips (ORM tests verify the contract those
  satisfy; an HTTP CRUD round-trip is just integration-test theater)
- Validation edge cases (Pydantic handles those; testing them is testing FastAPI)
- Per-route auth-mode plumbing (covered by test_e2e_org_isolation.py for the
  whole platform)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

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
from app.models.organization_members import OrganizationMember
from app.models.organizations import Organization
from app.models.regulatory import (
    RegulatoryCountry,
    RegulatoryPhase,
    RegulatoryStream,
    RegulatoryTag,
    RegulatoryTask,
)
from app.services.organizations import OrganizationContext

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# ---------------------------------------------------------------------------
# Fixtures — two orgs, parallel data
# ---------------------------------------------------------------------------

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
    """Seed two orgs each with one stream, one country, one phase, one task,
    and one tag. Used by every test as the cross-org baseline."""

    org_a = Organization(id=ORG_A_ID, name="Org A", slug="org-a")
    org_b = Organization(id=ORG_B_ID, name="Org B", slug="org-b")
    member_a_admin = OrganizationMember(
        id=uuid4(),
        organization_id=ORG_A_ID,
        user_id=USER_A_ID,
        role="admin",
    )
    member_a_member = OrganizationMember(
        id=uuid4(),
        organization_id=ORG_A_ID,
        user_id=uuid4(),
        role="member",
    )
    member_a_viewer = OrganizationMember(
        id=uuid4(),
        organization_id=ORG_A_ID,
        user_id=uuid4(),
        role="viewer",
    )
    member_b_admin = OrganizationMember(
        id=uuid4(),
        organization_id=ORG_B_ID,
        user_id=USER_B_ID,
        role="admin",
    )
    session.add_all(
        [org_a, org_b, member_a_admin, member_a_member, member_a_viewer, member_b_admin]
    )
    await session.flush()

    # Org A regulatory tree
    country_a = RegulatoryCountry(
        organization_id=ORG_A_ID,
        code="CA",
        name="Canada",
        status="active",
        display_label="Canada",
    )
    stream_a = RegulatoryStream(
        organization_id=ORG_A_ID,
        slug="corporate",
        name="Corporate",
        color_token="navy",
    )
    tag_a = RegulatoryTag(
        organization_id=ORG_A_ID,
        slug="abca",
        label="ABCA (A)",
        kind="corporate",
    )
    session.add_all([country_a, stream_a, tag_a])
    await session.flush()

    phase_a = RegulatoryPhase(
        stream_id=stream_a.id,
        country_id=country_a.id,
        name="Incorporate (A)",
        badge_kind="corp",
    )
    session.add(phase_a)
    await session.flush()

    task_a = RegulatoryTask(
        phase_id=phase_a.id,
        body="NUANS search (A)",
        completed=False,
    )
    session.add(task_a)
    await session.flush()

    # Org B regulatory tree
    country_b = RegulatoryCountry(
        organization_id=ORG_B_ID,
        code="CA",
        name="Canada",
        status="active",
        display_label="Canada",
    )
    stream_b = RegulatoryStream(
        organization_id=ORG_B_ID,
        slug="corporate",
        name="Corporate",
        color_token="navy",
    )
    tag_b = RegulatoryTag(
        organization_id=ORG_B_ID,
        slug="abca",
        label="ABCA (B)",
        kind="corporate",
    )
    session.add_all([country_b, stream_b, tag_b])
    await session.flush()

    phase_b = RegulatoryPhase(
        stream_id=stream_b.id,
        country_id=country_b.id,
        name="Incorporate (B)",
        badge_kind="corp",
    )
    session.add(phase_b)
    await session.flush()

    task_b = RegulatoryTask(
        phase_id=phase_b.id,
        body="NUANS search (B)",
        completed=False,
    )
    session.add(task_b)
    await session.commit()

    return {
        "org_a": org_a,
        "org_b": org_b,
        "admin_a": member_a_admin,
        "member_a": member_a_member,
        "viewer_a": member_a_viewer,
        "admin_b": member_b_admin,
        "stream_a_id": stream_a.id,
        "stream_b_id": stream_b.id,
        "country_a_id": country_a.id,
        "country_b_id": country_b.id,
        "tag_a_id": tag_a.id,
        "tag_b_id": tag_b.id,
        "phase_a_id": phase_a.id,
        "phase_b_id": phase_b.id,
        "task_a_id": task_a.id,
        "task_b_id": task_b.id,
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
    """Build a FastAPI app wired to the regulatory router with the given org ctx.

    The feature-flag gate is overridden to a no-op by default; individual tests
    that need to test the gate can override it back.
    """

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(lifespan=_lifespan)
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(regulatory_router)
    app.include_router(api_v1)

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_org_member] = lambda: ctx
    # ORG_RATE_LIMIT_DEP and the feature-flag dep both chain through
    # require_org_from_actor (the user-or-agent auth resolver). In tests
    # we short-circuit it to the same ctx — no real auth header is sent.
    app.dependency_overrides[require_org_from_actor] = lambda: ctx
    app.dependency_overrides[check_org_rate_limit] = lambda: None
    # Feature flag is enabled in test by default; specific tests override
    # this back with a 403-raising closure.
    app.dependency_overrides[REGULATORY_FEATURE_GATE] = lambda: None
    return app


# ---------------------------------------------------------------------------
# Cross-org READ isolation (HTTP mirrors of contract tests)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_GET_streams_returns_only_caller_org(env: dict[str, Any]) -> None:
    """GET /regulatory/streams returns only the caller's org rows."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/regulatory/streams")
    assert resp.status_code == 200
    streams = resp.json()
    assert len(streams) == 1
    assert UUID(streams[0]["id"]) == d["stream_a_id"]
    assert streams[0]["organization_id"] == str(ORG_A_ID)


@pytest.mark.asyncio
async def test_GET_tags_returns_only_caller_org(env: dict[str, Any]) -> None:
    """GET /regulatory/tags returns only the caller's org rows."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/regulatory/tags")
    assert resp.status_code == 200
    tags = resp.json()
    assert len(tags) == 1
    assert UUID(tags[0]["id"]) == d["tag_a_id"]
    assert tags[0]["label"] == "ABCA (A)"


@pytest.mark.asyncio
async def test_GET_phases_traces_through_stream_to_org(env: dict[str, Any]) -> None:
    """GET /regulatory/phases joins through Stream — only own-org phases visible."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/regulatory/phases")
    assert resp.status_code == 200
    phases = resp.json()
    assert len(phases) == 1
    assert UUID(phases[0]["id"]) == d["phase_a_id"]
    assert UUID(phases[0]["stream_id"]) == d["stream_a_id"]


@pytest.mark.asyncio
async def test_GET_tasks_traces_through_phase_chain_to_org(env: dict[str, Any]) -> None:
    """GET /regulatory/tasks two-hop joins through Phase→Stream — only own-org tasks visible."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/regulatory/tasks")
    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) == 1
    assert UUID(tasks[0]["id"]) == d["task_a_id"]


# ---------------------------------------------------------------------------
# Cross-org access on individual rows → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_PATCH_stream_in_other_org_returns_404(env: dict[str, Any]) -> None:
    """Caller in org A cannot update a stream that belongs to org B."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/regulatory/streams/{d['stream_b_id']}",
            json={"name": "Hijacked"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_PATCH_phase_in_other_org_returns_404(env: dict[str, Any]) -> None:
    """Caller in org A cannot update a phase that belongs to org B (FK chain check)."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch(
            f"/api/v1/regulatory/phases/{d['phase_b_id']}",
            json={"name": "Hijacked"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_toggle_task_in_other_org_returns_404(env: dict[str, Any]) -> None:
    """Caller in org A cannot toggle a task that belongs to org B (two-hop chain)."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(f"/api/v1/regulatory/tasks/{d['task_b_id']}/toggle")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Same-org enforcement at FK boundaries (Phase 1b's load-bearing surface)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_POST_phase_with_cross_org_stream_returns_404(env: dict[str, Any]) -> None:
    """Org A admin cannot create a phase referencing org B's stream.

    This is the silent-leak surface the model layer permits. Only the API
    same-org check prevents it.
    """
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/regulatory/phases",
            json={
                "stream_id": str(d["stream_b_id"]),  # cross-org
                "country_id": str(d["country_a_id"]),
                "name": "Should Fail",
            },
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_POST_phase_with_cross_org_country_returns_404(env: dict[str, Any]) -> None:
    """Org A admin cannot create a phase referencing org B's country."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/regulatory/phases",
            json={
                "stream_id": str(d["stream_a_id"]),
                "country_id": str(d["country_b_id"]),  # cross-org
                "name": "Should Fail",
            },
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_POST_task_in_cross_org_phase_returns_404(env: dict[str, Any]) -> None:
    """Org A operator cannot create a task in org B's phase (two-hop chain check)."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/regulatory/tasks",
            json={
                "phase_id": str(d["phase_b_id"]),  # cross-org
                "body": "Should Fail",
            },
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_POST_task_tag_with_cross_org_tag_returns_404(env: dict[str, Any]) -> None:
    """Org A operator cannot link org B's tag to org A's task.

    THE M2M silent-leak surface. The model permits any (task_id, tag_id) pair;
    this endpoint check is the only line of defense.
    """
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/regulatory/task-tags",
            json={
                "task_id": str(d["task_a_id"]),
                "tag_id": str(d["tag_b_id"]),  # cross-org
            },
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_POST_task_tag_with_cross_org_task_returns_404(env: dict[str, Any]) -> None:
    """Org A operator cannot link org A's tag to org B's task."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/regulatory/task-tags",
            json={
                "task_id": str(d["task_b_id"]),  # cross-org
                "tag_id": str(d["tag_a_id"]),
            },
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Role gating — admin+ for taxonomy, operator+ for workflow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_POST_stream_as_member_returns_403(env: dict[str, Any]) -> None:
    """Streams are admin+; member role gets 403."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["member_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/regulatory/streams",
            json={"slug": "new-stream", "name": "New Stream"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_POST_tag_as_member_returns_403(env: dict[str, Any]) -> None:
    """Tags are admin+; member role gets 403."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["member_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/regulatory/tags",
            json={"slug": "new-tag", "label": "New", "kind": "regulatory"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_POST_task_as_viewer_returns_403(env: dict[str, Any]) -> None:
    """Tasks are operator+; viewer role gets 403."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["viewer_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/regulatory/tasks",
            json={"phase_id": str(d["phase_a_id"]), "body": "New task"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_GET_streams_as_member_returns_200(env: dict[str, Any]) -> None:
    """Reads are member+; member role gets 200."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["member_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/regulatory/streams")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Happy paths — same-org create works (smoke tests, not exhaustive CRUD)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_POST_phase_with_same_org_refs_succeeds(env: dict[str, Any]) -> None:
    """Sanity: creating a phase with own-org stream + country works."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/regulatory/phases",
            json={
                "stream_id": str(d["stream_a_id"]),
                "country_id": str(d["country_a_id"]),
                "name": "New Phase",
            },
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "New Phase"
    assert UUID(body["stream_id"]) == d["stream_a_id"]


@pytest.mark.asyncio
async def test_POST_task_tag_same_org_succeeds_and_is_idempotent(
    env: dict[str, Any],
) -> None:
    """Sanity: linking own-org task + tag works, and re-linking is idempotent."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        body = {"task_id": str(d["task_a_id"]), "tag_id": str(d["tag_a_id"])}
        resp1 = await c.post("/api/v1/regulatory/task-tags", json=body)
        assert resp1.status_code == 201
        # Re-link is idempotent — returns 201 with same composite key, not 409.
        resp2 = await c.post("/api/v1/regulatory/task-tags", json=body)
        assert resp2.status_code == 201
        assert resp1.json() == resp2.json()


# ---------------------------------------------------------------------------
# Feature flag gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routes_blocked_when_regulatory_flag_disabled(env: dict[str, Any]) -> None:
    """When the regulatory feature flag is off, routes return 403.

    This re-overrides the require_feature dep that _make_app set to a no-op,
    making it raise the same way the real dep would when the flag is off.
    """
    from fastapi import HTTPException, status

    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))

    def _flag_off() -> None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="regulatory disabled"
        )

    app.dependency_overrides[REGULATORY_FEATURE_GATE] = _flag_off

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for path in [
            "/api/v1/regulatory/streams",
            "/api/v1/regulatory/countries",
            "/api/v1/regulatory/tags",
            "/api/v1/regulatory/phases",
            "/api/v1/regulatory/tasks",
        ]:
            resp = await c.get(path)
            assert resp.status_code == 403, f"{path} should be blocked when flag off"
