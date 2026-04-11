# ruff: noqa: INP001
"""Integration tests for industry template API endpoints.

Covers: list, detail, apply, onboarding status, and step completion.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import ORG_MEMBER_DEP, require_org_role
from app.api.industry_templates import router as templates_router
from app.models.organization_members import OrganizationMember
from app.models.organization_settings import OrganizationSettings
from app.models.organizations import Organization
from app.models.users import User
from app.services.organizations import OrganizationContext

# ---------------------------------------------------------------------------
# Test IDs
# ---------------------------------------------------------------------------

ORG_ID = uuid4()
USER_ID = uuid4()

# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------


async def _make_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


@pytest_asyncio.fixture
async def test_app():
    engine = await _make_engine()
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Seed org + settings
    async with session_maker() as session:
        org = Organization(id=ORG_ID, name="Test Construction Co", slug="test-construction")
        session.add(org)

        settings = OrganizationSettings(
            id=uuid4(),
            organization_id=ORG_ID,
            feature_flags_json=json.dumps({"email": True}),
        )
        session.add(settings)
        await session.commit()

    # Override dependencies
    member = OrganizationMember(
        id=uuid4(),
        organization_id=ORG_ID,
        user_id=USER_ID,
        role="owner",
    )
    org_ctx = OrganizationContext(organization=org, member=member)

    admin_dep = require_org_role("admin")

    from fastapi import APIRouter, FastAPI

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app = FastAPI(lifespan=noop_lifespan)
    api = APIRouter(prefix="/api/v1")
    api.include_router(templates_router)
    app.include_router(api)

    # Override auth deps to return our test org context
    app.dependency_overrides[ORG_MEMBER_DEP.dependency] = lambda: org_ctx
    app.dependency_overrides[admin_dep] = lambda: org_ctx

    # Monkeypatch session makers so endpoints use our in-memory DB
    import app.api.industry_templates as tmpl_mod
    import app.services.audit as audit_mod

    tmpl_mod.async_session_maker = session_maker
    audit_mod.async_session_maker = session_maker

    yield app, session_maker


# ---------------------------------------------------------------------------
# List templates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_templates(test_app):
    app, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/industry-templates")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 17
    ids = [t["id"] for t in data]
    assert "construction" in ids
    assert "waste_management" in ids


# ---------------------------------------------------------------------------
# Template detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_template_detail(test_app):
    app, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/industry-templates/construction")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "construction"
    assert data["name"] == "Construction & Trades"
    assert "feature_flags" in data
    assert "config_categories" in data
    assert "onboarding_steps" in data
    assert len(data["onboarding_steps"]) > 0


@pytest.mark.asyncio
async def test_get_template_detail_not_found(test_app):
    app, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/industry-templates/nonexistent")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auto-detect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_detect(test_app):
    app, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/industry-templates/auto-detect")
    assert resp.status_code == 200
    data = resp.json()
    # Org is named "Test Construction Co" so should detect construction
    assert data["template_id"] == "construction"
    assert data["confidence"] >= 0.4
    assert data["template_name"] == "Construction & Trades"


# ---------------------------------------------------------------------------
# Apply template
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_construction_template(test_app):
    app, session_maker = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/industry-templates/construction/apply")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["template_id"] == "construction"
    assert data["config_items_created"] > 0
    assert data["onboarding_steps"] > 0

    # Verify feature flags were merged in DB
    from sqlmodel import select

    from app.models.organization_settings import OrganizationSettings

    async with session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == ORG_ID)
        )
        settings = result.scalars().first()
        assert settings is not None
        flags = settings.feature_flags
        # Construction template should enable bookkeeping
        assert flags.get("bookkeeping") is True
        # Pre-existing flag should still be there
        assert flags.get("email") is True
        # Template ID should be set
        assert settings.industry_template_id == "construction"

    # Verify config data was seeded
    from app.models.org_config import OrgConfigData

    async with session_maker() as session:
        result = await session.execute(
            select(OrgConfigData).where(OrgConfigData.organization_id == ORG_ID)
        )
        items = result.scalars().all()
        assert len(items) > 0
        categories = {i.category for i in items}
        assert "cost_codes" in categories

    # Verify onboarding steps were created
    from app.models.org_config import OrgOnboardingStep

    async with session_maker() as session:
        result = await session.execute(
            select(OrgOnboardingStep).where(OrgOnboardingStep.organization_id == ORG_ID)
        )
        steps = result.scalars().all()
        assert len(steps) > 0
        assert all(s.template_id == "construction" for s in steps)
        assert all(s.completed is False for s in steps)


@pytest.mark.asyncio
async def test_apply_template_not_found(test_app):
    app, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/industry-templates/nonexistent/apply")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_apply_template_idempotent(test_app):
    """Re-applying a template should not duplicate config items."""
    app, session_maker = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp1 = await c.post("/api/v1/industry-templates/construction/apply")
        resp2 = await c.post("/api/v1/industry-templates/construction/apply")
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    # Second apply should create 0 new config items (already exist)
    assert resp2.json()["config_items_created"] == 0

    # Verify no duplicate config items
    from sqlmodel import select

    from app.models.org_config import OrgConfigData

    async with session_maker() as session:
        result = await session.execute(
            select(OrgConfigData).where(OrgConfigData.organization_id == ORG_ID)
        )
        items = result.scalars().all()
        keys = [(i.category, i.key) for i in items]
        assert len(keys) == len(set(keys)), "Duplicate config items found"


@pytest.mark.asyncio
async def test_apply_template_merges_flags_without_disabling(test_app):
    """Applying a template that doesn't include a flag should not disable it."""
    app, session_maker = test_app

    # Pre-enable a flag that construction template doesn't set
    from sqlmodel import select

    from app.models.organization_settings import OrganizationSettings

    async with session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == ORG_ID)
        )
        settings = result.scalars().first()
        settings.feature_flags_json = json.dumps({"email": True, "paper_trading": True})
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/api/v1/industry-templates/construction/apply")
    assert resp.status_code == 200

    async with session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == ORG_ID)
        )
        settings = result.scalars().first()
        flags = settings.feature_flags
        # Previously enabled flags must survive
        assert flags.get("email") is True
        assert flags.get("paper_trading") is True


# ---------------------------------------------------------------------------
# Onboarding status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_onboarding_status_empty(test_app):
    """No template applied yet — should return empty status."""
    app, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/industry-templates/onboarding/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["template_id"] is None
    assert data["steps"] == []
    assert data["progress_pct"] == 0


@pytest.mark.asyncio
async def test_onboarding_status_after_apply(test_app):
    """After applying a template, status should return steps."""
    app, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/api/v1/industry-templates/construction/apply")
        resp = await c.get("/api/v1/industry-templates/onboarding/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["template_id"] == "construction"
    assert len(data["steps"]) > 0
    assert data["progress_pct"] == 0
    # Verify step shape matches frontend expectations
    step = data["steps"][0]
    assert "step_key" in step
    assert "label" in step
    assert "description" in step
    assert "completed" in step
    assert step["completed"] is False


# ---------------------------------------------------------------------------
# Complete onboarding step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_onboarding_step(test_app):
    app, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # Apply template first
        await c.post("/api/v1/industry-templates/construction/apply")

        # Get steps
        status_resp = await c.get("/api/v1/industry-templates/onboarding/status")
        steps = status_resp.json()["steps"]
        first_key = steps[0]["step_key"]

        # Complete the first step
        resp = await c.patch(f"/api/v1/industry-templates/onboarding/{first_key}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["step_key"] == first_key

    # Verify progress updated
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        status_resp = await c.get("/api/v1/industry-templates/onboarding/status")
    data = status_resp.json()
    assert data["progress_pct"] > 0
    completed_step = next(s for s in data["steps"] if s["step_key"] == first_key)
    assert completed_step["completed"] is True
    assert completed_step["completed_at"] is not None


@pytest.mark.asyncio
async def test_complete_all_steps_reaches_100(test_app):
    app, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/api/v1/industry-templates/construction/apply")
        status_resp = await c.get("/api/v1/industry-templates/onboarding/status")
        steps = status_resp.json()["steps"]

        # Complete all steps
        for step in steps:
            resp = await c.patch(f"/api/v1/industry-templates/onboarding/{step['step_key']}")
            assert resp.status_code == 200

        # Check 100% progress
        final = await c.get("/api/v1/industry-templates/onboarding/status")
    assert final.json()["progress_pct"] == 100


@pytest.mark.asyncio
async def test_complete_nonexistent_step(test_app):
    app, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.patch("/api/v1/industry-templates/onboarding/nonexistent_step")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Cross-template apply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_different_template(test_app):
    """Applying a different template should create its own onboarding steps."""
    app, session_maker = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/api/v1/industry-templates/construction/apply")
        await c.post("/api/v1/industry-templates/waste_management/apply")

        # Onboarding status should show the latest template's steps
        resp = await c.get("/api/v1/industry-templates/onboarding/status")
    data = resp.json()
    # Should have steps from both templates (they're different template_ids)
    assert len(data["steps"]) > 0

    # Verify settings updated to latest template
    from sqlmodel import select

    from app.models.organization_settings import OrganizationSettings

    async with session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == ORG_ID)
        )
        settings = result.scalars().first()
        assert settings.industry_template_id == "waste_management"
