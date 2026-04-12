# ruff: noqa: INP001
"""Tests for per-user Google Calendar connection visibility scoping.

Verifies that private calendar connections are only visible to the owner
and org admins, and that multiple connections per org work correctly.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.time import utcnow
from app.models.google_calendar_connection import GoogleCalendarConnection

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ORG_ID = uuid4()
OWNER_USER_ID = uuid4()
MEMBER_USER_ID = uuid4()


async def _make_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return maker


async def _seed(session: AsyncSession) -> dict:
    """Seed one org with two calendar connections: one shared, one private."""
    shared_conn = GoogleCalendarConnection(
        id=uuid4(),
        organization_id=ORG_ID,
        user_id=OWNER_USER_ID,
        provider_account_id="google-owner-123",
        email_address="henry@gmail.com",
        visibility="shared",
        is_active=True,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    private_conn = GoogleCalendarConnection(
        id=uuid4(),
        organization_id=ORG_ID,
        user_id=MEMBER_USER_ID,
        provider_account_id="google-member-456",
        email_address="samir@gmail.com",
        visibility="private",
        is_active=True,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add_all([shared_conn, private_conn])
    await session.commit()
    return {"shared_conn": shared_conn, "private_conn": private_conn}


# ---------------------------------------------------------------------------
# Model defaults
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_visibility_is_shared():
    """New calendar connections default to 'shared' visibility."""
    conn = GoogleCalendarConnection(
        id=uuid4(),
        organization_id=ORG_ID,
        user_id=OWNER_USER_ID,
        provider_account_id="test",
        email_address="test@gmail.com",
    )
    assert conn.visibility == "shared"


# ---------------------------------------------------------------------------
# Multi-connection per org
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_connections_per_org():
    """Multiple users can connect their own Google accounts to the same org."""
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        stmt = select(GoogleCalendarConnection).where(
            GoogleCalendarConnection.organization_id == ORG_ID,
            GoogleCalendarConnection.is_active == True,  # noqa: E712
        )
        result = await session.execute(stmt)
        conns = list(result.scalars().all())
        assert len(conns) == 2


# ---------------------------------------------------------------------------
# Visibility filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shared_connections_visible_to_all():
    """Shared connections should be visible in filtered queries."""
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        stmt = select(GoogleCalendarConnection).where(
            GoogleCalendarConnection.organization_id == ORG_ID,
            GoogleCalendarConnection.is_active == True,  # noqa: E712
            GoogleCalendarConnection.visibility == "shared",
        )
        result = await session.execute(stmt)
        conns = list(result.scalars().all())
        assert len(conns) == 1
        assert conns[0].email_address == "henry@gmail.com"


@pytest.mark.asyncio
async def test_private_connection_hidden_from_non_owner():
    """Non-owner member query should not return private connections from other users."""
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        from sqlalchemy import or_

        # Simulate non-admin member who is OWNER_USER_ID (Henry)
        stmt = select(GoogleCalendarConnection).where(
            GoogleCalendarConnection.organization_id == ORG_ID,
            GoogleCalendarConnection.is_active == True,  # noqa: E712
            or_(
                GoogleCalendarConnection.visibility == "shared",
                GoogleCalendarConnection.user_id == OWNER_USER_ID,
            ),
        )
        result = await session.execute(stmt)
        conns = list(result.scalars().all())
        # Henry sees his shared connection but NOT Samir's private one
        assert len(conns) == 1
        assert conns[0].email_address == "henry@gmail.com"


@pytest.mark.asyncio
async def test_private_connection_visible_to_owner():
    """Connection owner should see their own private connection."""
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        from sqlalchemy import or_

        # Simulate member query for MEMBER_USER_ID (Samir)
        stmt = select(GoogleCalendarConnection).where(
            GoogleCalendarConnection.organization_id == ORG_ID,
            GoogleCalendarConnection.is_active == True,  # noqa: E712
            or_(
                GoogleCalendarConnection.visibility == "shared",
                GoogleCalendarConnection.user_id == MEMBER_USER_ID,
            ),
        )
        result = await session.execute(stmt)
        conns = list(result.scalars().all())
        # Samir sees shared + his own private
        assert len(conns) == 2
        emails = {c.email_address for c in conns}
        assert emails == {"henry@gmail.com", "samir@gmail.com"}


@pytest.mark.asyncio
async def test_admin_sees_all_connections():
    """Admin/owner sees all connections regardless of visibility."""
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        stmt = select(GoogleCalendarConnection).where(
            GoogleCalendarConnection.organization_id == ORG_ID,
            GoogleCalendarConnection.is_active == True,  # noqa: E712
        )
        result = await session.execute(stmt)
        conns = list(result.scalars().all())
        assert len(conns) == 2


# ---------------------------------------------------------------------------
# Visibility toggle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_visibility_roundtrip():
    """Toggling visibility from shared to private and back works."""
    maker = await _make_session()
    async with maker() as session:
        data = await _seed(session)
        conn = data["shared_conn"]
        assert conn.visibility == "shared"

        conn.visibility = "private"
        session.add(conn)
        await session.commit()
        await session.refresh(conn)
        assert conn.visibility == "private"

        # Now no shared connections
        stmt = select(GoogleCalendarConnection).where(
            GoogleCalendarConnection.organization_id == ORG_ID,
            GoogleCalendarConnection.is_active == True,  # noqa: E712
            GoogleCalendarConnection.visibility == "shared",
        )
        result = await session.execute(stmt)
        conns = list(result.scalars().all())
        assert len(conns) == 0

        # Toggle back
        conn.visibility = "shared"
        session.add(conn)
        await session.commit()
        await session.refresh(conn)
        assert conn.visibility == "shared"

        result = await session.execute(stmt)
        conns = list(result.scalars().all())
        assert len(conns) == 1
