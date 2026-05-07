# ruff: noqa: INP001
"""Org-isolation tests for /api/v1/cost-tracker/errors.

Locks the 2026-05-07 multi-tenancy fix: ActivityEvent rows tagged with
organization_id are scoped to that org's Error Log on Agent Activity. Rows
with NULL organization_id are platform-wide and visible to every org's admins.

Pre-fix behavior: every org saw every other org's error log because
activity_events was a flat orgless table — closed by adding the
organization_id column + threading it through track_error() callers +
filtering both endpoints by current org.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.cost_tracker import require_org_admin, router as cost_tracker_router
from app.api.deps import (
    check_org_rate_limit,
    require_org_member,
)
from app.core.time import utcnow
from app.models.activity_events import ActivityEvent
from app.models.organization_members import OrganizationMember
from app.models.organizations import Organization
from app.services.organizations import OrganizationContext


ORG_A_ID = uuid4()
ORG_B_ID = uuid4()


async def _seed_errors(session_maker: async_sessionmaker[AsyncSession]) -> None:
    """Seed three error rows: one for Org A, one for Org B, one platform-wide (NULL)."""
    async with session_maker() as session:
        now = utcnow()
        org_a = Organization(id=ORG_A_ID, name="Org A", created_at=now, updated_at=now)
        org_b = Organization(id=ORG_B_ID, name="Org B", created_at=now, updated_at=now)
        session.add_all([org_a, org_b])
        await session.commit()

        session.add_all(
            [
                ActivityEvent(
                    id=uuid4(),
                    event_type="system.error.budget",
                    message="[WARNING] Org A monthly budget at 80%",
                    organization_id=ORG_A_ID,
                ),
                ActivityEvent(
                    id=uuid4(),
                    event_type="system.error.budget",
                    message="[WARNING] Org B monthly budget at 90%",
                    organization_id=ORG_B_ID,
                ),
                ActivityEvent(
                    id=uuid4(),
                    event_type="system.error.circuit_breaker",
                    message="[WARNING] Circuit breaker 'openrouter' opened",
                    organization_id=None,  # platform-wide
                ),
                # Non-error event must never show up in either org's log
                ActivityEvent(
                    id=uuid4(),
                    event_type="agent.message",
                    message="Hello",
                    organization_id=ORG_A_ID,
                ),
            ]
        )
        await session.commit()


def _build_app(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    org_id: UUID,
    role: str = "admin",
) -> FastAPI:
    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        yield

    app = FastAPI(lifespan=_lifespan)
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(cost_tracker_router)
    app.include_router(api_v1)

    async def _override_org_member() -> OrganizationContext:
        org = Organization(id=org_id, name=f"Org {org_id}")
        member = OrganizationMember(
            id=uuid4(),
            organization_id=org_id,
            user_id=uuid4(),
            role=role,
            all_boards_read=True,
            all_boards_write=True,
        )
        return OrganizationContext(organization=org, member=member)

    async def _override_rate_limit() -> None:
        return None

    async def _override_feature() -> None:
        return None

    app.dependency_overrides[require_org_member] = _override_org_member
    # require_org_admin is captured at module load in cost_tracker.py, so the
    # test override here matches the same key the router resolved at import.
    app.dependency_overrides[require_org_admin] = _override_org_member
    app.dependency_overrides[check_org_rate_limit] = _override_rate_limit
    # Router-level require_feature("cost_tracker") is also a captured-factory dep,
    # but it's invoked at router definition time. Override its underlying check.
    from app.api.cost_tracker import router as ct_router

    for dep in ct_router.dependencies:
        if hasattr(dep, "dependency"):
            app.dependency_overrides[dep.dependency] = _override_feature

    return app


@pytest_asyncio.fixture
async def session_maker_with_errors():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await _seed_errors(maker)

    # Patch async_session_maker imported by cost_tracker.py
    import app.api.cost_tracker as ct_mod

    original = ct_mod.async_session_maker
    ct_mod.async_session_maker = maker  # type: ignore[assignment]
    try:
        yield maker
    finally:
        ct_mod.async_session_maker = original  # type: ignore[assignment]
        await engine.dispose()


class TestErrorLogReadIsolation:
    async def test_org_a_sees_only_own_and_platform_errors(
        self, session_maker_with_errors
    ) -> None:
        app = _build_app(session_maker_with_errors, org_id=ORG_A_ID)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/api/v1/cost-tracker/errors")
            assert r.status_code == 200
            rows = r.json()
            messages = sorted(row["message"] for row in rows)
            assert any("Org A" in m for m in messages)
            assert any("Circuit breaker" in m for m in messages)
            assert not any("Org B" in m for m in messages), (
                f"Org A leaked Org B's errors: {messages}"
            )

    async def test_org_b_sees_only_own_and_platform_errors(
        self, session_maker_with_errors
    ) -> None:
        app = _build_app(session_maker_with_errors, org_id=ORG_B_ID)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/api/v1/cost-tracker/errors")
            assert r.status_code == 200
            rows = r.json()
            messages = [row["message"] for row in rows]
            assert any("Org B" in m for m in messages)
            assert any("Circuit breaker" in m for m in messages)
            assert not any("Org A monthly budget" in m for m in messages), (
                f"Org B leaked Org A's errors: {messages}"
            )

    async def test_response_includes_organization_id_field(
        self, session_maker_with_errors
    ) -> None:
        app = _build_app(session_maker_with_errors, org_id=ORG_A_ID)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/api/v1/cost-tracker/errors")
            rows = r.json()
            for row in rows:
                assert "organization_id" in row
            # Org A's row has org_id, platform row has None
            org_ids = {row["organization_id"] for row in rows}
            assert str(ORG_A_ID) in org_ids
            assert None in org_ids

    async def test_non_error_events_excluded(self, session_maker_with_errors) -> None:
        """The 'agent.message' row in seed must never appear in error log."""
        app = _build_app(session_maker_with_errors, org_id=ORG_A_ID)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/api/v1/cost-tracker/errors")
            messages = [row["message"] for row in r.json()]
            assert not any("Hello" in m for m in messages)


class TestErrorLogClearIsolation:
    async def test_org_a_admin_clears_only_org_a_errors(
        self, session_maker_with_errors
    ) -> None:
        app = _build_app(session_maker_with_errors, org_id=ORG_A_ID, role="admin")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.delete("/api/v1/cost-tracker/errors")
            assert r.status_code == 200
            assert r.json()["cleared"] == 1  # only Org A's row, not platform-wide

        # Verify Org B still has its row + platform row still exists
        async with session_maker_with_errors() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(ActivityEvent).where(
                    ActivityEvent.event_type.startswith("system.error")
                )
            )
            remaining = list(result.scalars().all())
            messages = sorted(r.message or "" for r in remaining)
            assert any("Org B" in m for m in messages), (
                f"Org A's clear deleted Org B's data: {messages}"
            )
            assert any("Circuit breaker" in m for m in messages), (
                f"Platform-wide error was wiped — must only age out via retention: {messages}"
            )

    async def test_clear_does_not_touch_platform_wide_rows(
        self, session_maker_with_errors
    ) -> None:
        """Admins cannot clear NULL-org rows — those age out via retention."""
        app = _build_app(session_maker_with_errors, org_id=ORG_A_ID, role="admin")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            await c.delete("/api/v1/cost-tracker/errors")

        async with session_maker_with_errors() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(ActivityEvent).where(ActivityEvent.organization_id.is_(None))
            )
            assert len(result.scalars().all()) == 1  # circuit_breaker survives
