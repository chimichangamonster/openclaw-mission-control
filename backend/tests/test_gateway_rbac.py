# ruff: noqa: INP001
"""Tests for gateway endpoint RBAC — operator role can use chat surface.

Locks in the 2026-05-03 fix that re-tiered gateway.py from blanket admin+ to
member+ for read endpoints and operator+ for mutating endpoints. Before this
fix, all 12 endpoints required admin role, which broke the dashboard's Gateway
Health panel and the /chat page entirely for operator users (Samir on Waste
Gurus + Magnetik in production).

The test asserts the contract directly at the dependency layer — what role
each endpoint admits — without needing the full gateway RPC stack.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import get_session
from app.api.gateway import router as gateway_router
from app.core.auth import AuthContext, get_auth_context
from app.core.time import utcnow
from app.models.organization_members import OrganizationMember
from app.models.organizations import Organization
from app.models.users import User


OPERATOR_USER_ID = uuid4()
ADMIN_USER_ID = uuid4()
MEMBER_USER_ID = uuid4()
VIEWER_USER_ID = uuid4()
ORG_ID = uuid4()


@pytest_asyncio.fixture
async def app_with_seed():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    now = utcnow()
    async with maker() as session:
        session.add(
            Organization(id=ORG_ID, name="Test Org", created_at=now, updated_at=now),
        )
        session.add_all(
            [
                User(
                    id=OPERATOR_USER_ID,
                    clerk_user_id="clerk_operator",
                    email="operator@test.local",
                    name="Operator",
                    active_organization_id=ORG_ID,
                    created_at=now,
                    updated_at=now,
                ),
                User(
                    id=ADMIN_USER_ID,
                    clerk_user_id="clerk_admin",
                    email="admin@test.local",
                    name="Admin",
                    active_organization_id=ORG_ID,
                    created_at=now,
                    updated_at=now,
                ),
                User(
                    id=MEMBER_USER_ID,
                    clerk_user_id="clerk_member",
                    email="member@test.local",
                    name="Member",
                    active_organization_id=ORG_ID,
                    created_at=now,
                    updated_at=now,
                ),
                User(
                    id=VIEWER_USER_ID,
                    clerk_user_id="clerk_viewer",
                    email="viewer@test.local",
                    name="Viewer",
                    active_organization_id=ORG_ID,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.add_all(
            [
                OrganizationMember(
                    id=uuid4(),
                    user_id=OPERATOR_USER_ID,
                    organization_id=ORG_ID,
                    role="operator",
                    all_boards_read=True,
                    all_boards_write=True,
                    created_at=now,
                    updated_at=now,
                ),
                OrganizationMember(
                    id=uuid4(),
                    user_id=ADMIN_USER_ID,
                    organization_id=ORG_ID,
                    role="admin",
                    all_boards_read=True,
                    all_boards_write=True,
                    created_at=now,
                    updated_at=now,
                ),
                OrganizationMember(
                    id=uuid4(),
                    user_id=MEMBER_USER_ID,
                    organization_id=ORG_ID,
                    role="member",
                    all_boards_read=True,
                    all_boards_write=True,
                    created_at=now,
                    updated_at=now,
                ),
                OrganizationMember(
                    id=uuid4(),
                    user_id=VIEWER_USER_ID,
                    organization_id=ORG_ID,
                    role="viewer",
                    all_boards_read=True,
                    all_boards_write=False,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await session.commit()

    app = FastAPI()
    app.include_router(gateway_router, prefix="/api/v1")

    async def _get_session():
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = _get_session

    # Auth override switches based on app.state so each test can pick its actor.
    async def _auth_override():
        user_id = getattr(app.state, "active_user_id", OPERATOR_USER_ID)
        async with maker() as s:
            user = await s.get(User, user_id)
            return AuthContext(actor_type="user", user=user)

    app.dependency_overrides[get_auth_context] = _auth_override

    yield app, maker
    await engine.dispose()


def _set_actor(app: FastAPI, user_id) -> None:
    app.state.active_user_id = user_id


@pytest.mark.asyncio
async def test_operator_can_read_gateway_status(app_with_seed) -> None:
    """Operator role must be able to GET /gateways/status (dashboard health)."""
    app, _ = app_with_seed
    _set_actor(app, OPERATOR_USER_ID)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # No board_id → resolver will fail downstream, but auth/RBAC must pass first.
        # We're asserting NOT 403. The dep layer is what we're locking in.
        response = await client.get("/api/v1/gateways/status")
    assert response.status_code != 403, (
        f"operator must not be blocked from /gateways/status; got {response.status_code} "
        f"body={response.text}"
    )


@pytest.mark.asyncio
async def test_operator_can_list_sessions(app_with_seed) -> None:
    """Operator role must be able to GET /gateways/sessions (chat sidebar)."""
    app, _ = app_with_seed
    _set_actor(app, OPERATOR_USER_ID)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/gateways/sessions")
    assert response.status_code != 403


@pytest.mark.asyncio
async def test_operator_can_send_message(app_with_seed) -> None:
    """Operator role must be able to POST /gateways/sessions/{id}/message (chat send)."""
    app, _ = app_with_seed
    _set_actor(app, OPERATOR_USER_ID)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/gateways/sessions/abc/message",
            json={"message": "hello"},
        )
    assert response.status_code != 403


@pytest.mark.asyncio
async def test_member_can_read_status_but_not_send_message(app_with_seed) -> None:
    """Member role: status read OK (member tier), message send blocked (operator tier)."""
    app, _ = app_with_seed
    _set_actor(app, MEMBER_USER_ID)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status_resp = await client.get("/api/v1/gateways/status")
        message_resp = await client.post(
            "/api/v1/gateways/sessions/abc/message",
            json={"message": "hello"},
        )
    assert status_resp.status_code != 403, (
        f"member must read /gateways/status; got {status_resp.status_code}"
    )
    assert message_resp.status_code == 403, (
        f"member must NOT send messages (operator+ only); got {message_resp.status_code}"
    )


@pytest.mark.asyncio
async def test_admin_can_send_message(app_with_seed) -> None:
    """Admin role retains full access (regression check — no role above operator broken)."""
    app, _ = app_with_seed
    _set_actor(app, ADMIN_USER_ID)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/gateways/sessions/abc/message",
            json={"message": "hello"},
        )
    assert response.status_code != 403


@pytest.mark.asyncio
async def test_viewer_can_read_status(app_with_seed) -> None:
    """Viewer role: dashboard health is the headline read-only surface for accountants/auditors.

    Locks in the role-contract.md commitment that viewer = honest read-only,
    not just "label without enforcement."
    """
    app, _ = app_with_seed
    _set_actor(app, VIEWER_USER_ID)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/gateways/status")
    assert response.status_code != 403, (
        f"viewer must read /gateways/status (dashboard); got {response.status_code}"
    )


@pytest.mark.asyncio
async def test_viewer_can_read_session_history(app_with_seed) -> None:
    """Viewer role: must read chat history (audit / oversight use case)."""
    app, _ = app_with_seed
    _set_actor(app, VIEWER_USER_ID)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/gateways/sessions/abc/history")
    assert response.status_code != 403


@pytest.mark.asyncio
async def test_viewer_cannot_send_message(app_with_seed) -> None:
    """Viewer role: must NOT send chat messages (no agent interaction)."""
    app, _ = app_with_seed
    _set_actor(app, VIEWER_USER_ID)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/gateways/sessions/abc/message",
            json={"message": "hello"},
        )
    assert response.status_code == 403, (
        f"viewer must NOT send messages; got {response.status_code}"
    )


@pytest.mark.asyncio
async def test_viewer_cannot_create_session(app_with_seed) -> None:
    """Viewer role: must NOT create new chat sessions."""
    app, _ = app_with_seed
    _set_actor(app, VIEWER_USER_ID)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/gateways/sessions",
            json={"label": "test"},
        )
    assert response.status_code == 403, (
        f"viewer must NOT create sessions; got {response.status_code}"
    )


@pytest.mark.asyncio
async def test_viewer_cannot_compact_or_reset(app_with_seed) -> None:
    """Viewer role: must NOT compact or reset session history (mutating ops)."""
    app, _ = app_with_seed
    _set_actor(app, VIEWER_USER_ID)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        compact_resp = await client.post("/api/v1/gateways/sessions/abc/compact")
        reset_resp = await client.post("/api/v1/gateways/sessions/abc/reset")
    assert compact_resp.status_code == 403, (
        f"viewer must NOT compact sessions; got {compact_resp.status_code}"
    )
    assert reset_resp.status_code == 403, (
        f"viewer must NOT reset sessions; got {reset_resp.status_code}"
    )
