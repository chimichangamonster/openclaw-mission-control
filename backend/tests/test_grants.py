# ruff: noqa: INP001
"""HTTP-level tests for the grants tracker API (item 107 v2 Phase 1).

Mirrors test_regulatory_api.py shape exactly: two-org fixture, in-memory
SQLite, FastAPI app with dependency overrides, httpx AsyncClient.

Coverage focus per item 107 scope:
- Cross-org READ isolation (list, detail, status math)
- Cross-org WRITE blocked (PATCH grant in other org → 404)
- M2M same-org enforcement on prerequisite linking — the silent-leak
  surface (mirror of the RegulatoryTaskTag contract)
- Role gating: grant CREATE operator+, DELETE admin+, draws/deadlines
  operator+
- Feature-flag gate: grants_tracker off → 403 across all routes
- Prerequisite status math (total / complete / blocking_critical / percent)
- Idempotent prerequisite linking — re-adding same task returns existing link
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
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
from app.api.grants import GRANTS_FEATURE_GATE
from app.api.grants import router as grants_router
from app.models.grants import (
    Grant,
    GrantDrawSchedule,
    GrantPrerequisiteTask,
    GrantReportingDeadline,
)
from app.models.organization_members import OrganizationMember
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
    """Seed two orgs each with one grant + one regulatory task (for
    prerequisite linking) + one draw + one deadline.
    """

    org_a = Organization(id=ORG_A_ID, name="Org A", slug="org-a")
    org_b = Organization(id=ORG_B_ID, name="Org B", slug="org-b")
    member_a_admin = OrganizationMember(
        id=uuid4(),
        organization_id=ORG_A_ID,
        user_id=USER_A_ID,
        role="admin",
    )
    member_a_operator = OrganizationMember(
        id=uuid4(),
        organization_id=ORG_A_ID,
        user_id=uuid4(),
        role="operator",
    )
    member_a_member = OrganizationMember(
        id=uuid4(),
        organization_id=ORG_A_ID,
        user_id=uuid4(),
        role="member",
    )
    member_b_admin = OrganizationMember(
        id=uuid4(),
        organization_id=ORG_B_ID,
        user_id=USER_B_ID,
        role="admin",
    )
    session.add_all(
        [
            org_a,
            org_b,
            member_a_admin,
            member_a_operator,
            member_a_member,
            member_b_admin,
        ]
    )
    await session.flush()

    # Org A regulatory tree (so we can test prerequisite linking)
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
    )
    session.add_all([country_a, stream_a])
    await session.flush()

    phase_a = RegulatoryPhase(
        stream_id=stream_a.id, country_id=country_a.id, name="Incorporate (A)"
    )
    session.add(phase_a)
    await session.flush()

    reg_task_a_incomplete = RegulatoryTask(
        phase_id=phase_a.id, body="Incorporate Magnetik (A)", completed=False
    )
    reg_task_a_complete = RegulatoryTask(
        phase_id=phase_a.id, body="NUANS search (A)", completed=True
    )
    session.add_all([reg_task_a_incomplete, reg_task_a_complete])

    # Org B regulatory tree (so we can attempt cross-org M2M)
    country_b = RegulatoryCountry(
        organization_id=ORG_B_ID,
        code="CA",
        name="Canada",
        status="active",
        display_label="Canada",
    )
    stream_b = RegulatoryStream(
        organization_id=ORG_B_ID, slug="corporate", name="Corporate"
    )
    session.add_all([country_b, stream_b])
    await session.flush()

    phase_b = RegulatoryPhase(
        stream_id=stream_b.id, country_id=country_b.id, name="Incorporate (B)"
    )
    session.add(phase_b)
    await session.flush()

    reg_task_b = RegulatoryTask(
        phase_id=phase_b.id, body="Org B incorporate task", completed=False
    )
    session.add(reg_task_b)
    await session.flush()

    # Grants
    grant_a = Grant(
        organization_id=ORG_A_ID,
        granting_body="Emissions Reduction Alberta",
        program_name="Industrial Transformation Challenge 2026-27",
        application_status="drafting",
        awarded_amount=Decimal("850000.00"),
        currency="CAD",
    )
    grant_b = Grant(
        organization_id=ORG_B_ID,
        granting_body="Org B Funder",
        program_name="Org B Program",
        application_status="planned",
    )
    session.add_all([grant_a, grant_b])
    await session.flush()

    draw_a = GrantDrawSchedule(
        grant_id=grant_a.id,
        milestone_label="Project kickoff",
        target_amount=Decimal("100000.00"),
        target_date=date(2026, 8, 1),
        status="pending",
    )
    deadline_a = GrantReportingDeadline(
        grant_id=grant_a.id,
        deadline_date=date(2026, 12, 1),
        deadline_type="interim_report",
        description="Q3 progress",
        status="upcoming",
    )
    session.add_all([draw_a, deadline_a])

    await session.commit()

    return {
        "org_a": org_a,
        "org_b": org_b,
        "admin_a": member_a_admin,
        "operator_a": member_a_operator,
        "member_a": member_a_member,
        "admin_b": member_b_admin,
        "grant_a_id": grant_a.id,
        "grant_b_id": grant_b.id,
        "draw_a_id": draw_a.id,
        "deadline_a_id": deadline_a.id,
        "reg_task_a_incomplete_id": reg_task_a_incomplete.id,
        "reg_task_a_complete_id": reg_task_a_complete.id,
        "reg_task_b_id": reg_task_b.id,
    }


@pytest_asyncio.fixture
async def env() -> AsyncIterator[dict[str, Any]]:
    engine = await _make_engine()
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        data = await _seed(session)
    yield {"maker": maker, "data": data}
    await engine.dispose()


def _make_app(
    maker: async_sessionmaker[AsyncSession], ctx: OrganizationContext
) -> FastAPI:
    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(lifespan=_lifespan)
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(grants_router)
    app.include_router(api_v1)

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_org_member] = lambda: ctx
    app.dependency_overrides[require_org_from_actor] = lambda: ctx
    app.dependency_overrides[check_org_rate_limit] = lambda: None
    app.dependency_overrides[GRANTS_FEATURE_GATE] = lambda: None
    return app


# ---------------------------------------------------------------------------
# Cross-org READ isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_GET_grants_returns_only_caller_org(env: dict[str, Any]) -> None:
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.get("/api/v1/grants")
    assert resp.status_code == 200
    grants = resp.json()
    assert len(grants) == 1
    assert UUID(grants[0]["id"]) == d["grant_a_id"]
    assert grants[0]["organization_id"] == str(ORG_A_ID)


@pytest.mark.asyncio
async def test_GET_grant_detail_includes_nested_draws_deadlines(
    env: dict[str, Any],
) -> None:
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.get(f"/api/v1/grants/{d['grant_a_id']}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert UUID(body["id"]) == d["grant_a_id"]
    assert len(body["draws"]) == 1
    assert UUID(body["draws"][0]["id"]) == d["draw_a_id"]
    assert len(body["deadlines"]) == 1
    assert UUID(body["deadlines"][0]["id"]) == d["deadline_a_id"]
    assert body["prerequisites"] == []


@pytest.mark.asyncio
async def test_GET_grant_in_other_org_returns_404(env: dict[str, Any]) -> None:
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.get(f"/api/v1/grants/{d['grant_b_id']}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Cross-org WRITE blocked at FK boundary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_PATCH_grant_in_other_org_returns_404(env: dict[str, Any]) -> None:
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.patch(
            f"/api/v1/grants/{d['grant_b_id']}",
            json={"program_name": "Hijacked"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_DELETE_grant_in_other_org_returns_404(env: dict[str, Any]) -> None:
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.delete(f"/api/v1/grants/{d['grant_b_id']}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_draw_on_other_org_grant_returns_404(
    env: dict[str, Any],
) -> None:
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.post(
            f"/api/v1/grants/{d['grant_b_id']}/draws",
            json={"milestone_label": "Sneak", "target_amount": "100.00"},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Grant CRUD happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_POST_grant_creates_with_caller_org(env: dict[str, Any]) -> None:
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.post(
            "/api/v1/grants",
            json={
                "granting_body": "Alberta Innovates",
                "program_name": "Voucher",
                "application_status": "drafting",
                "currency": "CAD",
            },
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["organization_id"] == str(ORG_A_ID)
    assert body["granting_body"] == "Alberta Innovates"
    assert body["application_status"] == "drafting"


@pytest.mark.asyncio
async def test_PATCH_grant_updates_status_to_awarded(env: dict[str, Any]) -> None:
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.patch(
            f"/api/v1/grants/{d['grant_a_id']}",
            json={
                "application_status": "awarded",
                "decision_at": "2026-09-15",
            },
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["application_status"] == "awarded"


# ---------------------------------------------------------------------------
# Prerequisite linking — same-org guard (the M2M silent-leak surface)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_POST_prerequisite_links_when_task_in_same_org(
    env: dict[str, Any],
) -> None:
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.post(
            f"/api/v1/grants/{d['grant_a_id']}/prerequisites",
            json={
                "regulatory_task_id": str(d["reg_task_a_incomplete_id"]),
                "is_critical": True,
            },
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert UUID(body["regulatory_task_id"]) == d["reg_task_a_incomplete_id"]
    assert body["is_critical"] is True
    assert body["task_body"] == "Incorporate Magnetik (A)"
    assert body["task_completed"] is False


@pytest.mark.asyncio
async def test_POST_prerequisite_blocked_when_task_in_other_org(
    env: dict[str, Any],
) -> None:
    """The M2M silent-leak surface — must 404 before insert.

    Mirrors the RegulatoryTaskTag same-org contract test in
    test_regulatory_isolation.py.
    """
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.post(
            f"/api/v1/grants/{d['grant_a_id']}/prerequisites",
            json={"regulatory_task_id": str(d["reg_task_b_id"])},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_POST_prerequisite_idempotent_on_duplicate_link(
    env: dict[str, Any],
) -> None:
    """Re-linking the same task returns the existing link, not a duplicate."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        first = await c.post(
            f"/api/v1/grants/{d['grant_a_id']}/prerequisites",
            json={"regulatory_task_id": str(d["reg_task_a_incomplete_id"])},
        )
        second = await c.post(
            f"/api/v1/grants/{d['grant_a_id']}/prerequisites",
            json={"regulatory_task_id": str(d["reg_task_a_incomplete_id"])},
        )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["created_at"] == second.json()["created_at"]


@pytest.mark.asyncio
async def test_GET_prerequisite_status_aggregates_correctly(
    env: dict[str, Any],
) -> None:
    """1 critical-incomplete + 1 complete = 2 total, 1 complete, 1 blocking, 50%."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        await c.post(
            f"/api/v1/grants/{d['grant_a_id']}/prerequisites",
            json={
                "regulatory_task_id": str(d["reg_task_a_incomplete_id"]),
                "is_critical": True,
            },
        )
        await c.post(
            f"/api/v1/grants/{d['grant_a_id']}/prerequisites",
            json={
                "regulatory_task_id": str(d["reg_task_a_complete_id"]),
                "is_critical": True,
            },
        )
        resp = await c.get(
            f"/api/v1/grants/{d['grant_a_id']}/prerequisites/status"
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["complete"] == 1
    assert body["blocking_critical"] == 1
    assert body["percent"] == 0.5


@pytest.mark.asyncio
async def test_DELETE_prerequisite_removes_link(env: dict[str, Any]) -> None:
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        await c.post(
            f"/api/v1/grants/{d['grant_a_id']}/prerequisites",
            json={"regulatory_task_id": str(d["reg_task_a_incomplete_id"])},
        )
        resp = await c.delete(
            f"/api/v1/grants/{d['grant_a_id']}/prerequisites/{d['reg_task_a_incomplete_id']}"
        )
    assert resp.status_code == 204
    # Status should now show 0 prereqs.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.get(
            f"/api/v1/grants/{d['grant_a_id']}/prerequisites/status"
        )
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# Draw / deadline cross-org guards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_PATCH_draw_in_other_org_returns_404(env: dict[str, Any]) -> None:
    """Caller in org A patches a draw belonging to org B's grant → 404."""
    d = env["data"]
    # Manually create a draw on org_b's grant
    async with env["maker"]() as session:
        draw_b = GrantDrawSchedule(
            grant_id=d["grant_b_id"],
            milestone_label="B kickoff",
            target_amount=Decimal("50000.00"),
        )
        session.add(draw_b)
        await session.commit()
        draw_b_id = draw_b.id

    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.patch(
            f"/api/v1/grants/draws/{draw_b_id}",
            json={"status": "approved"},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Feature-flag gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routes_blocked_when_grants_flag_disabled(
    env: dict[str, Any],
) -> None:
    from fastapi import HTTPException, status as http_status

    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org_a"], d["admin_a"]))

    def _flag_off() -> None:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="grants_tracker disabled",
        )

    app.dependency_overrides[GRANTS_FEATURE_GATE] = _flag_off

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.get("/api/v1/grants")
        assert resp.status_code == 403
        resp = await c.get(f"/api/v1/grants/{d['grant_a_id']}")
        assert resp.status_code == 403
        resp = await c.post(
            "/api/v1/grants",
            json={"granting_body": "x", "program_name": "y"},
        )
        assert resp.status_code == 403
