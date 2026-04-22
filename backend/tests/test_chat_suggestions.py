# ruff: noqa: INP001
"""Tests for chat suggestions cascade: org config > industry template > fallback."""

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

from app.api.deps import require_org_from_actor
from app.api.org_config import router as org_config_router
from app.models.org_config import OrgConfigData
from app.models.organization_members import OrganizationMember
from app.models.organization_settings import OrganizationSettings
from app.models.organizations import Organization
from app.services.organizations import OrganizationContext

ORG_ID = uuid4()
USER_ID = uuid4()


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
async def make_app():
    """Factory: returns a function that builds an app with the given template_id / org_items seed."""

    async def _build(template_id: str | None = None, org_items: list[dict] | None = None):
        engine = await _make_engine()
        session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with session_maker() as session:
            org = Organization(id=ORG_ID, name="Test Org", slug="test-org")
            session.add(org)
            settings = OrganizationSettings(
                id=uuid4(),
                organization_id=ORG_ID,
                industry_template_id=template_id,
                feature_flags_json=json.dumps({}),
            )
            session.add(settings)
            for item in org_items or []:
                session.add(
                    OrgConfigData(
                        id=uuid4(),
                        organization_id=ORG_ID,
                        category="chat_suggestions",
                        key=item["key"],
                        label=item["label"],
                        value_json=json.dumps(item.get("value", {})),
                        sort_order=item.get("sort_order", 0),
                        is_active=item.get("is_active", True),
                    )
                )
            await session.commit()

        member = OrganizationMember(
            id=uuid4(),
            organization_id=ORG_ID,
            user_id=USER_ID,
            role="owner",
        )
        org_ctx = OrganizationContext(organization=org, member=member)

        from fastapi import APIRouter, FastAPI

        @asynccontextmanager
        async def noop_lifespan(app):
            yield

        app = FastAPI(lifespan=noop_lifespan)
        api = APIRouter(prefix="/api/v1")
        api.include_router(org_config_router)
        app.include_router(api)

        app.dependency_overrides[require_org_from_actor] = lambda: org_ctx

        import app.api.org_config as cfg_mod

        cfg_mod.async_session_maker = session_maker

        return app

    return _build


@pytest.mark.asyncio
async def test_fallback_when_no_org_config_and_no_template(make_app):
    """Layer 3: no org rows, no template → generic fallback."""
    app = await make_app(template_id=None, org_items=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/org-config/chat-suggestions/resolved")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "fallback"
    assert len(data["suggestions"]) >= 3
    # Fallback shape: each entry has key/label/prompt
    for s in data["suggestions"]:
        assert "key" in s and "label" in s and "prompt" in s


@pytest.mark.asyncio
async def test_template_used_when_org_config_absent(make_app):
    """Layer 2: no org rows but industry_template_id set → template defaults."""
    app = await make_app(template_id="construction", org_items=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/org-config/chat-suggestions/resolved")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "template"
    assert data["template_id"] == "construction"
    # Construction template includes a "Today's job costs" suggestion
    keys = {s["key"] for s in data["suggestions"]}
    assert "job_costs" in keys


@pytest.mark.asyncio
async def test_org_config_wins_over_template(make_app):
    """Layer 1: org rows override template defaults even when template is set."""
    app = await make_app(
        template_id="construction",
        org_items=[
            {
                "key": "custom_one",
                "label": "Custom One",
                "value": {"prompt": "Do the custom thing"},
                "sort_order": 0,
            },
            {
                "key": "custom_two",
                "label": "Custom Two",
                "value": {"prompt": "Do the other thing"},
                "sort_order": 1,
            },
        ],
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/org-config/chat-suggestions/resolved")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "org"
    assert len(data["suggestions"]) == 2
    assert data["suggestions"][0]["key"] == "custom_one"
    assert data["suggestions"][0]["prompt"] == "Do the custom thing"
    # Template defaults should NOT leak in
    assert all(s["key"] not in {"job_costs", "invoice_status"} for s in data["suggestions"])


@pytest.mark.asyncio
async def test_inactive_org_config_rows_ignored(make_app):
    """Inactive rows fall through to template/fallback as if they weren't there."""
    app = await make_app(
        template_id="construction",
        org_items=[
            {
                "key": "disabled",
                "label": "Disabled",
                "value": {"prompt": "Never shown"},
                "is_active": False,
            },
        ],
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/org-config/chat-suggestions/resolved")
    assert resp.status_code == 200
    data = resp.json()
    # Inactive row shouldn't trigger Layer 1 → template applies instead
    assert data["source"] == "template"


@pytest.mark.asyncio
async def test_missing_prompt_value_falls_back_to_label(make_app):
    """If an admin adds a row with empty value, prompt defaults to the label."""
    app = await make_app(
        template_id=None,
        org_items=[
            {
                "key": "bare",
                "label": "Just the label",
                "value": {},
                "sort_order": 0,
            },
        ],
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/org-config/chat-suggestions/resolved")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "org"
    assert data["suggestions"][0]["prompt"] == "Just the label"


@pytest.mark.asyncio
async def test_unknown_template_id_falls_through_to_fallback(make_app):
    """Stale/deleted template_id in settings should not crash — falls to fallback."""
    app = await make_app(template_id="nonexistent_template", org_items=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/v1/org-config/chat-suggestions/resolved")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "fallback"
