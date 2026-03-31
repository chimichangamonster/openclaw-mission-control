# ruff: noqa: INP001
"""Tests for the onboarding checklist PDF generation and readiness check."""

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

from app.models.organization_members import OrganizationMember
from app.models.organization_settings import OrganizationSettings
from app.models.organizations import Organization
from app.models.users import User

# ---------------------------------------------------------------------------
# Test IDs
# ---------------------------------------------------------------------------

ORG_ID = uuid4()
USER_ID = uuid4()

# ---------------------------------------------------------------------------
# DB + app setup
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


# ---------------------------------------------------------------------------
# PDF checklist tests (no auth required — public endpoint)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def legal_app():
    from fastapi import FastAPI, APIRouter
    from app.api.legal import router as legal_router

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app = FastAPI(lifespan=noop_lifespan)
    api = APIRouter(prefix="/api/v1")
    api.include_router(legal_router)
    app.include_router(api)
    yield app


@pytest.mark.asyncio
async def test_onboarding_checklist_html(legal_app):
    async with AsyncClient(transport=ASGITransport(app=legal_app), base_url="http://test") as c:
        resp = await c.get("/api/v1/legal/onboarding-checklist")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Cost Code Structure" in resp.text
    assert "VantageClaw" in resp.text


@pytest.mark.asyncio
async def test_onboarding_checklist_pdf_generic(legal_app):
    """Generic PDF (no industry) should generate successfully."""
    async with AsyncClient(transport=ASGITransport(app=legal_app), base_url="http://test") as c:
        resp = await c.get("/api/v1/legal/onboarding-checklist.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["content-disposition"] == 'inline; filename="vantageclaw-onboarding-checklist.pdf"'
    assert resp.content[:5] == b"%PDF-"
    assert len(resp.content) > 2000


@pytest.mark.asyncio
async def test_onboarding_checklist_pdf_with_industry(legal_app):
    """PDF with industry param should include industry-specific sections."""
    async with AsyncClient(transport=ASGITransport(app=legal_app), base_url="http://test") as c:
        resp = await c.get("/api/v1/legal/onboarding-checklist.pdf?industry=construction")
        generic_resp = await c.get("/api/v1/legal/onboarding-checklist.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "construction" in resp.headers["content-disposition"]
    assert resp.content[:5] == b"%PDF-"
    # Industry-specific PDF should be larger (more sections)
    assert len(resp.content) > len(generic_resp.content)


@pytest.mark.asyncio
async def test_onboarding_checklist_pdf_unknown_industry(legal_app):
    """Unknown industry param should fall back to generic checklist."""
    async with AsyncClient(transport=ASGITransport(app=legal_app), base_url="http://test") as c:
        resp = await c.get("/api/v1/legal/onboarding-checklist.pdf?industry=nonexistent")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "vantageclaw-onboarding-checklist.pdf" in resp.headers["content-disposition"]


# ---------------------------------------------------------------------------
# Readiness check tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def readiness_app():
    engine = await _make_engine()
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        org = Organization(id=ORG_ID, name="Test Org", slug="test-org")
        session.add(org)

        user = User(id=USER_ID, clerk_user_id="test-admin", platform_role="owner")
        session.add(user)

        member = OrganizationMember(
            id=uuid4(), organization_id=ORG_ID, user_id=USER_ID, role="owner",
        )
        session.add(member)

        settings = OrganizationSettings(
            id=uuid4(),
            organization_id=ORG_ID,
            feature_flags_json=json.dumps({"bookkeeping": True, "email": True}),
            industry_template_id="construction",
        )
        session.add(settings)
        await session.commit()

    from fastapi import FastAPI, APIRouter
    from app.api.platform_admin import router as platform_router
    from app.api.deps import get_session
    from app.core.platform_auth import require_platform_admin

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app = FastAPI(lifespan=noop_lifespan)
    api = APIRouter(prefix="/api/v1")
    api.include_router(platform_router)
    app.include_router(api)

    async def override_session():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_platform_admin] = lambda: user

    # Monkeypatch audit to use test DB
    import app.services.audit as audit_mod
    audit_mod.async_session_maker = session_maker

    yield app, session_maker


@pytest.mark.asyncio
async def test_readiness_check_returns_checks(readiness_app):
    app, _ = readiness_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/platform/orgs/{ORG_ID}/readiness")
    assert resp.status_code == 200
    data = resp.json()
    assert data["org"] == "Test Org"
    assert "checks" in data
    assert "passed" in data
    assert "total" in data
    assert isinstance(data["checks"], list)
    assert len(data["checks"]) >= 8


@pytest.mark.asyncio
async def test_readiness_check_settings_pass(readiness_app):
    app, _ = readiness_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/platform/orgs/{ORG_ID}/readiness")
    data = resp.json()
    checks = {c["check"]: c for c in data["checks"]}

    # These should pass based on our seed data
    assert checks["org_settings_exist"]["passed"] is True
    assert checks["feature_flags_set"]["passed"] is True
    assert checks["members_exist"]["passed"] is True
    assert checks["has_owner"]["passed"] is True
    assert checks["industry_template"]["passed"] is True
    assert checks["slug_set"]["passed"] is True


@pytest.mark.asyncio
async def test_readiness_check_missing_items(readiness_app):
    """Without gateway or budget, those checks should fail."""
    app, _ = readiness_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/platform/orgs/{ORG_ID}/readiness")
    data = resp.json()
    checks = {c["check"]: c for c in data["checks"]}

    # No gateway seeded, no budget seeded, no LLM key seeded
    assert checks["gateway_connected"]["passed"] is False
    assert checks["budget_configured"]["passed"] is False
    assert checks["llm_access"]["passed"] is False


@pytest.mark.asyncio
async def test_readiness_check_nonexistent_org(readiness_app):
    app, _ = readiness_app
    fake_id = uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/platform/orgs/{fake_id}/readiness")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_readiness_check_reports_score(readiness_app):
    app, _ = readiness_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"/api/v1/platform/orgs/{ORG_ID}/readiness")
    data = resp.json()
    assert data["passed"] <= data["total"]
    assert data["ready"] == (data["passed"] == data["total"])
    # With our seed data, we should have some passes but not all (no gateway/budget/LLM)
    assert data["ready"] is False
    assert data["passed"] >= 5  # settings, flags, members, owner, template, slug
