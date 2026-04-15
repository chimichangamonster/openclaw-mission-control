# ruff: noqa: INP001
"""Tests for GET /organizations/{org_id}/boards — cross-org boards listing.

Companion to test_gateway_status_cross_org.py. That fix let gateway status
RPC queries cross orgs; this endpoint lets the caller actually *discover*
the boards to query in orgs they belong to but aren't active in.

Used by the dashboard's cross-org Gateway Health aggregation — a multi-org
member (platform owner with 4 orgs) can load all their boards in one pass
without switching active orgs.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
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
from app.api.organizations import router as organizations_router
from app.core.auth import AuthContext, get_auth_context
from app.core.time import utcnow
from app.models.boards import Board
from app.models.organization_members import OrganizationMember
from app.models.organizations import Organization
from app.models.users import User


MEMBER_USER_ID = uuid4()
NONMEMBER_USER_ID = uuid4()
ORG_VANTAGE_ID = uuid4()  # User is a member
ORG_MAGNETIK_ID = uuid4()  # User is a member
ORG_OUTSIDER_ID = uuid4()  # User is NOT a member


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
        # Orgs
        session.add_all(
            [
                Organization(id=ORG_VANTAGE_ID, name="Vantage", created_at=now, updated_at=now),
                Organization(id=ORG_MAGNETIK_ID, name="Magnetik", created_at=now, updated_at=now),
                Organization(id=ORG_OUTSIDER_ID, name="Outsider", created_at=now, updated_at=now),
            ]
        )
        # Member user belongs to Vantage + Magnetik, not Outsider
        member = User(
            id=MEMBER_USER_ID,
            clerk_user_id="clerk_member",
            email="member@test.local",
            name="Member",
            active_organization_id=ORG_VANTAGE_ID,  # Active = Vantage
            created_at=now,
            updated_at=now,
        )
        nonmember = User(
            id=NONMEMBER_USER_ID,
            clerk_user_id="clerk_outsider",
            email="outsider@test.local",
            name="Outsider",
            created_at=now,
            updated_at=now,
        )
        session.add_all([member, nonmember])
        session.add_all(
            [
                OrganizationMember(
                    id=uuid4(),
                    user_id=MEMBER_USER_ID,
                    organization_id=ORG_VANTAGE_ID,
                    role="owner",
                    all_boards_read=True,
                    all_boards_write=True,
                    created_at=now,
                    updated_at=now,
                ),
                OrganizationMember(
                    id=uuid4(),
                    user_id=MEMBER_USER_ID,
                    organization_id=ORG_MAGNETIK_ID,
                    role="owner",
                    all_boards_read=True,
                    all_boards_write=True,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        # Boards in each org
        session.add_all(
            [
                Board(
                    id=uuid4(),
                    organization_id=ORG_VANTAGE_ID,
                    name="Vantage Board",
                    slug="vantage-board",
                    created_at=now,
                    updated_at=now,
                ),
                Board(
                    id=uuid4(),
                    organization_id=ORG_MAGNETIK_ID,
                    name="Magnetik Board A",
                    slug="magnetik-board-a",
                    created_at=now,
                    updated_at=now,
                ),
                Board(
                    id=uuid4(),
                    organization_id=ORG_MAGNETIK_ID,
                    name="Magnetik Board B",
                    slug="magnetik-board-b",
                    created_at=now,
                    updated_at=now,
                ),
                Board(
                    id=uuid4(),
                    organization_id=ORG_OUTSIDER_ID,
                    name="Outsider Board",
                    slug="outsider-board",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await session.commit()

    app = FastAPI()
    app.include_router(organizations_router, prefix="/api/v1")

    @asynccontextmanager
    async def _session_ctx():
        async with maker() as s:
            yield s

    async def _get_session_override():
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = _get_session_override

    return app, maker


@pytest.mark.asyncio
async def test_multi_org_member_can_list_non_active_org_boards(app_with_seed) -> None:
    """Vantage-active user can list Magnetik's boards via the cross-org endpoint."""
    app, maker = app_with_seed

    async with maker() as session:
        user = await session.get(User, MEMBER_USER_ID)
        assert user is not None

    async def _auth_override() -> AuthContext:
        return AuthContext(actor_type="user", user=user)

    app.dependency_overrides[get_auth_context] = _auth_override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/v1/organizations/{ORG_MAGNETIK_ID}/boards")

    assert response.status_code == 200
    boards = response.json()
    assert len(boards) == 2
    names = sorted(b["name"] for b in boards)
    assert names == ["Magnetik Board A", "Magnetik Board B"]


@pytest.mark.asyncio
async def test_non_member_gets_403_for_outsider_org(app_with_seed) -> None:
    """User who is not a member of Outsider org cannot list its boards."""
    app, maker = app_with_seed

    async with maker() as session:
        user = await session.get(User, MEMBER_USER_ID)
        assert user is not None

    async def _auth_override() -> AuthContext:
        return AuthContext(actor_type="user", user=user)

    app.dependency_overrides[get_auth_context] = _auth_override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/v1/organizations/{ORG_OUTSIDER_ID}/boards")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_request_gets_401(app_with_seed) -> None:
    """No auth → 401 (not leaking 403 which would imply org existence)."""
    app, _ = app_with_seed

    async def _auth_override() -> AuthContext:
        return AuthContext(actor_type="user", user=None)

    app.dependency_overrides[get_auth_context] = _auth_override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/v1/organizations/{ORG_VANTAGE_ID}/boards")

    assert response.status_code == 401
