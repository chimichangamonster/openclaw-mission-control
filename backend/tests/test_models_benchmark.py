# ruff: noqa: INP001
"""Tests for GET /models/benchmark — Phase 3c Step 3.

Aggregates model_call_log rows across a configurable time window and optional
skill_name filter. Returns per-(model, skill) reliability, latency, and cost.

Seeds a temp DB with a mix of success/error/timeout rows across two models and
two skills, then asserts the response shape and the math.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.api.deps import (
    ORG_RATE_LIMIT_DEP,
    check_org_rate_limit,
    get_session,
    require_org_from_actor,
    require_org_member,
)
from app.api.model_registry import router as model_registry_router
from app.core.time import utcnow
from app.models.model_call_log import ModelCallLog
from app.models.organization_members import OrganizationMember
from app.models.organizations import Organization
from app.models.users import User
from app.services.organizations import OrganizationContext

ORG_ID = uuid4()
USER_ID = uuid4()


async def _make_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


async def _seed_base(session) -> dict:
    now = utcnow()
    org = Organization(id=ORG_ID, name="Bench Test Org", created_at=now, updated_at=now)
    session.add(org)
    user = User(
        id=USER_ID,
        clerk_user_id="bench-clerk",
        email="bench@test.com",
        name="Bench Tester",
        active_organization_id=ORG_ID,
    )
    session.add(user)
    member = OrganizationMember(
        id=uuid4(),
        organization_id=ORG_ID,
        user_id=USER_ID,
        role="owner",
        all_boards_read=True,
        all_boards_write=True,
        created_at=now,
        updated_at=now,
    )
    session.add(member)
    await session.commit()
    return {"org": org, "user": user, "member": member}


async def _seed_calls(session, org_id: UUID) -> None:
    """Three models × mixed statuses + one old row (48h ago) to test window filter."""
    now = utcnow()

    rows = [
        # model-A / session_titler — 4 success, 1 error, 1 timeout = 66.7%
        ModelCallLog(
            organization_id=org_id,
            model="model-A",
            provider="openrouter",
            skill_name="session_titler",
            status="success",
            http_status=200,
            latency_ms=100,
            tokens_in=10,
            tokens_out=5,
            cost_usd=0.001,
            created_at=now - timedelta(hours=1),
        ),
        ModelCallLog(
            organization_id=org_id,
            model="model-A",
            provider="openrouter",
            skill_name="session_titler",
            status="success",
            http_status=200,
            latency_ms=200,
            tokens_in=12,
            tokens_out=6,
            cost_usd=0.0015,
            created_at=now - timedelta(hours=2),
        ),
        ModelCallLog(
            organization_id=org_id,
            model="model-A",
            provider="openrouter",
            skill_name="session_titler",
            status="success",
            http_status=200,
            latency_ms=300,
            tokens_in=8,
            tokens_out=4,
            cost_usd=0.0008,
            created_at=now - timedelta(hours=3),
        ),
        ModelCallLog(
            organization_id=org_id,
            model="model-A",
            provider="openrouter",
            skill_name="session_titler",
            status="success",
            http_status=200,
            latency_ms=400,
            tokens_in=11,
            tokens_out=5,
            cost_usd=0.0012,
            created_at=now - timedelta(hours=4),
        ),
        ModelCallLog(
            organization_id=org_id,
            model="model-A",
            provider="openrouter",
            skill_name="session_titler",
            status="error",
            http_status=500,
            error_type="server_error",
            latency_ms=50,
            created_at=now - timedelta(hours=5),
        ),
        ModelCallLog(
            organization_id=org_id,
            model="model-A",
            provider="openrouter",
            skill_name="session_titler",
            status="timeout",
            http_status=None,
            error_type="timeout",
            latency_ms=10000,
            created_at=now - timedelta(hours=6),
        ),
        # model-B / embedding — 2 success = 100%
        ModelCallLog(
            organization_id=org_id,
            model="model-B",
            provider="openrouter",
            skill_name="embedding",
            status="success",
            http_status=200,
            latency_ms=80,
            tokens_in=100,
            cost_usd=0.0001,
            created_at=now - timedelta(hours=1),
        ),
        ModelCallLog(
            organization_id=org_id,
            model="model-B",
            provider="openrouter",
            skill_name="embedding",
            status="success",
            http_status=200,
            latency_ms=90,
            tokens_in=150,
            cost_usd=0.00015,
            created_at=now - timedelta(hours=2),
        ),
        # model-A / embedding — 1 success so we can test skill_filter
        ModelCallLog(
            organization_id=org_id,
            model="model-A",
            provider="openrouter",
            skill_name="embedding",
            status="success",
            http_status=200,
            latency_ms=120,
            tokens_in=50,
            cost_usd=0.0005,
            created_at=now - timedelta(hours=2),
        ),
        # OLD row outside a 24h window — must be excluded when days=1
        ModelCallLog(
            organization_id=org_id,
            model="model-A",
            provider="openrouter",
            skill_name="session_titler",
            status="error",
            http_status=500,
            error_type="server_error",
            latency_ms=50,
            created_at=now - timedelta(hours=48),
        ),
    ]
    for r in rows:
        session.add(r)
    await session.commit()


def _build_app(maker: async_sessionmaker, org_ctx: OrganizationContext) -> FastAPI:
    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        yield

    app = FastAPI(lifespan=_lifespan)
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(model_registry_router)
    app.include_router(api_v1)

    async def _override_session():
        async with maker() as session:
            yield session

    async def _override_org_member() -> OrganizationContext:
        return org_ctx

    async def _override_rate_limit() -> None:
        return None

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[require_org_member] = _override_org_member
    app.dependency_overrides[require_org_from_actor] = _override_org_member
    app.dependency_overrides[check_org_rate_limit] = _override_rate_limit
    # ORG_RATE_LIMIT_DEP is a Depends(check_org_rate_limit); the override above
    # handles it, but FastAPI doesn't overwrite Depends instances by default —
    # make sure check_org_rate_limit dependency is the overridden one.
    _ = ORG_RATE_LIMIT_DEP  # noqa: F841 — imported for side-effect reference
    return app


@pytest_asyncio.fixture
async def env():
    engine = await _make_engine()
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        data = await _seed_base(session)
        await _seed_calls(session, ORG_ID)
    ctx = OrganizationContext(organization=data["org"], member=data["member"])
    app = _build_app(maker, ctx)
    yield {"app": app, "maker": maker, "data": data}
    await engine.dispose()


class TestModelsBenchmark:
    @pytest.mark.asyncio
    async def test_default_window_returns_per_model_per_skill_rows(self, env) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://test"
        ) as c:
            resp = await c.get("/api/v1/models/benchmark")
            assert resp.status_code == 200
            body = resp.json()

        assert "window_days" in body
        assert "generated_at" in body
        assert "rows" in body
        rows = body["rows"]
        # 3 combinations in last 24h:
        # (model-A, session_titler), (model-B, embedding), (model-A, embedding)
        assert len(rows) == 3

        by_key = {(r["model"], r["skill_name"]): r for r in rows}
        assert ("model-A", "session_titler") in by_key
        assert ("model-B", "embedding") in by_key
        assert ("model-A", "embedding") in by_key

    @pytest.mark.asyncio
    async def test_reliability_and_latency_math(self, env) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://test"
        ) as c:
            resp = await c.get("/api/v1/models/benchmark")
            rows = resp.json()["rows"]

        ma_titler = next(
            r for r in rows if r["model"] == "model-A" and r["skill_name"] == "session_titler"
        )
        # 4 success / 6 total = 0.6667
        assert ma_titler["total_calls"] == 6
        assert ma_titler["success_count"] == 4
        assert ma_titler["error_count"] == 1
        assert ma_titler["timeout_count"] == 1
        assert ma_titler["success_rate"] == pytest.approx(4 / 6, abs=0.001)
        # Average latency across all non-null rows: (100+200+300+400+50+10000)/6
        # Endpoint rounds to 2 decimals, so tolerate that.
        assert ma_titler["avg_latency_ms"] == pytest.approx(
            (100 + 200 + 300 + 400 + 50 + 10000) / 6, abs=0.01
        )
        # p95 should be the high outlier (10000)
        assert ma_titler["p95_latency_ms"] >= 400

    @pytest.mark.asyncio
    async def test_cost_aggregation(self, env) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://test"
        ) as c:
            resp = await c.get("/api/v1/models/benchmark")
            rows = resp.json()["rows"]

        ma_titler = next(
            r for r in rows if r["model"] == "model-A" and r["skill_name"] == "session_titler"
        )
        # Cost sum: 0.001 + 0.0015 + 0.0008 + 0.0012 = 0.0045 (error + timeout have null cost)
        assert ma_titler["total_cost_usd"] == pytest.approx(0.0045, abs=0.0001)
        assert ma_titler["total_tokens_in"] == 10 + 12 + 8 + 11  # 41
        assert ma_titler["total_tokens_out"] == 5 + 6 + 4 + 5  # 20

    @pytest.mark.asyncio
    async def test_skill_filter(self, env) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://test"
        ) as c:
            resp = await c.get("/api/v1/models/benchmark?skill=embedding")
            rows = resp.json()["rows"]

        # Only embedding rows: (model-A, embedding) and (model-B, embedding)
        assert len(rows) == 2
        skills = {r["skill_name"] for r in rows}
        assert skills == {"embedding"}

    @pytest.mark.asyncio
    async def test_days_window_excludes_older_rows(self, env) -> None:
        """days=1 must exclude the 48h-old row."""
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://test"
        ) as c:
            resp = await c.get("/api/v1/models/benchmark?days=1")
            rows = resp.json()["rows"]

        ma_titler = next(
            r for r in rows if r["model"] == "model-A" and r["skill_name"] == "session_titler"
        )
        # Without the 48h-old error row: 6 calls (not 7)
        assert ma_titler["total_calls"] == 6
        assert ma_titler["error_count"] == 1

    @pytest.mark.asyncio
    async def test_days_window_includes_older_rows_when_wider(self, env) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://test"
        ) as c:
            resp = await c.get("/api/v1/models/benchmark?days=7")
            rows = resp.json()["rows"]

        ma_titler = next(
            r for r in rows if r["model"] == "model-A" and r["skill_name"] == "session_titler"
        )
        # Adds the 48h error row: 7 calls total, 2 errors
        assert ma_titler["total_calls"] == 7
        assert ma_titler["error_count"] == 2

    @pytest.mark.asyncio
    async def test_days_validation(self, env) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://test"
        ) as c:
            resp_low = await c.get("/api/v1/models/benchmark?days=0")
            assert resp_low.status_code == 422
            resp_high = await c.get("/api/v1/models/benchmark?days=400")
            assert resp_high.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_rows(self) -> None:
        engine = await _make_engine()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            data = await _seed_base(session)
        ctx = OrganizationContext(organization=data["org"], member=data["member"])
        app = _build_app(maker, ctx)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.get("/api/v1/models/benchmark")
                assert resp.status_code == 200
                body = resp.json()
                assert body["rows"] == []
        finally:
            await engine.dispose()
