# ruff: noqa: INP001
"""HTTP tests for POST /regulatory/import-html (item 101 v2 Phase 1b.2).

The import endpoint parses ``equipment-tracker.html`` into the regulatory
tables. Idempotency is the load-bearing property — re-running the import
on the same HTML must not duplicate streams, countries, phases, tasks,
tags, or priority notes.

Coverage focus:
- Admin-only role gate
- Successful first-import creates the expected row counts
- Re-import is idempotent (no duplicates)
- Idempotency key tolerates trivial whitespace edits in task text
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
from sqlmodel import SQLModel, select
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
    RegulatoryPriorityNote,
    RegulatoryStream,
    RegulatoryTag,
    RegulatoryTask,
    RegulatoryTaskTag,
)
from app.services.organizations import OrganizationContext

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


# ---------------------------------------------------------------------------
# Sample tracker HTML — small but exercises every parser path
# ---------------------------------------------------------------------------

SAMPLE_HTML = """
<div class="tab-panel" id="panel-canada" data-country-label="Canada">
  <div id="stream-navy">
    <div class="stream-header navy">
      <div class="stream-title">Corporate Foundation</div>
      <div class="stream-subtitle">Setup</div>
      <div class="stream-budget">Budget: $50K · Regulator: ABCA</div>
    </div>
    <div class="phase-block">
      <div class="phase-title-row open" data-phase-toggle>
        <span class="phase-badge badge-corp">Urgent</span>
        <span class="phase-name">Incorporate</span>
        <span class="phase-timing">Days 1-10</span>
      </div>
      <div class="phase-items open">
        <div class="priority-note critical">BLOCKING ITEM: Incorporate first.</div>
        <div class="task-item" data-task-toggle>
          <div class="task-check"></div>
          <div class="task-body">
            <div class="task-text">NUANS name search</div>
            <div class="task-note">Reserves the name 90 days.</div>
            <div class="task-tags">
              <span class="tag tag-corp">ABCA</span>
              <span class="tag tag-critical">Day 1</span>
            </div>
          </div>
        </div>
        <div class="task-item" data-task-toggle>
          <div class="task-check"></div>
          <div class="task-body">
            <div class="task-text">File Articles of Incorporation</div>
            <div class="task-tags">
              <span class="tag tag-corp">ABCA</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div id="stream-green">
    <div class="stream-header green">
      <div class="stream-title">Eboiler</div>
      <div class="stream-subtitle">Pressure equipment</div>
      <div class="stream-budget">Budget: $352K · Regulator: ABSA</div>
    </div>
    <div class="phase-block">
      <div class="phase-title-row" data-phase-toggle>
        <span class="phase-badge badge-now">Immediate</span>
        <span class="phase-name">Engage P.Eng.</span>
        <span class="phase-timing">Months 0-2</span>
      </div>
      <div class="phase-items">
        <div class="task-item" data-task-toggle>
          <div class="task-check"></div>
          <div class="task-body">
            <div class="task-text">Engage CRN specialist</div>
            <div class="task-tags">
              <span class="tag tag-absa">ABSA</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
""".strip()

# Same logical content but with whitespace noise in one task body — should
# hash to the same body_hash as SAMPLE_HTML and dedup.
WHITESPACE_NOISE_HTML = SAMPLE_HTML.replace(
    '<div class="task-text">NUANS name search</div>',
    '<div class="task-text">  NUANS\n   name   search  </div>',
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ORG_ID = uuid4()
USER_ID = uuid4()


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
    org = Organization(id=ORG_ID, name="Magnetik", slug="magnetik")
    admin = OrganizationMember(id=uuid4(), organization_id=ORG_ID, user_id=USER_ID, role="admin")
    member = OrganizationMember(id=uuid4(), organization_id=ORG_ID, user_id=uuid4(), role="member")
    session.add_all([org, admin, member])
    await session.commit()
    return {"org": org, "admin": admin, "member": member}


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


async def _count_rows(maker: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    async with maker() as session:
        counts = {}
        for label, model in (
            ("countries", RegulatoryCountry),
            ("streams", RegulatoryStream),
            ("phases", RegulatoryPhase),
            ("tasks", RegulatoryTask),
            ("tags", RegulatoryTag),
            ("priority_notes", RegulatoryPriorityNote),
            ("task_tags", RegulatoryTaskTag),
        ):
            result = await session.execute(select(model))
            counts[label] = len(list(result.scalars().all()))
        return counts


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_can_import_and_creates_expected_rows(env: dict[str, Any]) -> None:
    """First import creates 1 country, 2 streams, 2 phases, 3 tasks, 3 tags
    (corp, critical, absa), 1 priority note, 4 task-tag links."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org"], d["admin"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/regulatory/import-html",
            files={"file": ("tracker.html", SAMPLE_HTML.encode(), "text/html")},
        )
    assert resp.status_code == 201, resp.text
    summary = resp.json()
    assert summary["countries_created"] == 1
    assert summary["streams_created"] == 2
    assert summary["phases_created"] == 2
    assert summary["tasks_created"] == 3
    assert summary["tags_created"] == 3
    assert summary["priority_notes_created"] == 1
    # Skipped counters all zero on first import.
    assert summary["tasks_skipped_duplicate"] == 0
    assert summary["streams_skipped_existing"] == 0
    assert summary["phases_skipped_existing"] == 0

    counts = await _count_rows(env["maker"])
    assert counts["countries"] == 1
    assert counts["streams"] == 2
    assert counts["phases"] == 2
    assert counts["tasks"] == 3
    assert counts["tags"] == 3
    assert counts["priority_notes"] == 1
    # Task→tag links: NUANS has 2, Articles has 1, Engage has 1 = 4
    assert counts["task_tags"] == 4


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_re_import_is_idempotent_no_duplicates(env: dict[str, Any]) -> None:
    """Running the same import twice must not double row counts."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org"], d["admin"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        first = await c.post(
            "/api/v1/regulatory/import-html",
            files={"file": ("tracker.html", SAMPLE_HTML.encode(), "text/html")},
        )
        second = await c.post(
            "/api/v1/regulatory/import-html",
            files={"file": ("tracker.html", SAMPLE_HTML.encode(), "text/html")},
        )
    assert first.status_code == 201
    assert second.status_code == 201

    second_summary = second.json()
    assert second_summary["tasks_created"] == 0
    assert second_summary["tasks_skipped_duplicate"] == 3
    assert second_summary["streams_skipped_existing"] == 2
    assert second_summary["phases_skipped_existing"] == 2

    counts = await _count_rows(env["maker"])
    # Same counts as after first import.
    assert counts["streams"] == 2
    assert counts["phases"] == 2
    assert counts["tasks"] == 3
    assert counts["task_tags"] == 4


@pytest.mark.asyncio
async def test_re_import_with_whitespace_noise_dedups(env: dict[str, Any]) -> None:
    """Import-then-reimport with whitespace differences in task text should
    still dedup — body_hash is computed on normalized text."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org"], d["admin"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        first = await c.post(
            "/api/v1/regulatory/import-html",
            files={"file": ("tracker.html", SAMPLE_HTML.encode(), "text/html")},
        )
        second = await c.post(
            "/api/v1/regulatory/import-html",
            files={
                "file": (
                    "tracker.html",
                    WHITESPACE_NOISE_HTML.encode(),
                    "text/html",
                )
            },
        )
    assert first.status_code == 201
    assert second.status_code == 201
    counts = await _count_rows(env["maker"])
    assert counts["tasks"] == 3  # not 4


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_member_role_cannot_import(env: dict[str, Any]) -> None:
    """Non-admin members get 403."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org"], d["member"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/regulatory/import-html",
            files={"file": ("tracker.html", SAMPLE_HTML.encode(), "text/html")},
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_html_returns_422(env: dict[str, Any]) -> None:
    """An HTML file with no published-country panels can't seed anything —
    surface this as 422 rather than a confusing 201 with all zeros."""
    d = env["data"]
    app = _make_app(env["maker"], _ctx(d["org"], d["admin"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/regulatory/import-html",
            files={
                "file": (
                    "empty.html",
                    b"<html><body><p>nothing here</p></body></html>",
                    "text/html",
                )
            },
        )
    assert resp.status_code == 422
