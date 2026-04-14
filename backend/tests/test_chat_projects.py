# ruff: noqa: INP001
"""Tests for chat project CRUD + session assignment.

Item 34d from chat-reorganization-plan.md. Covers:
- list/create/update lifecycle
- session assignment + unassignment
- project archival removes its session assignments
- org isolation (assignments from org A invisible to org B)
- session_count aggregation in list/update reads
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.schemas.chat_projects import ChatProjectCreate, ChatProjectUpdate
from app.services import chat_projects as svc


async def _make_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return maker()


@pytest.mark.asyncio
async def test_list_empty_then_create_then_list() -> None:
    org_id = uuid4()
    session = await _make_session()

    assert await svc.list_projects(session, org_id) == []

    created = await svc.create_project(
        session,
        org_id,
        ChatProjectCreate(name="Property Smart Pilot", color="#4f46e5"),
    )
    assert created.name == "Property Smart Pilot"
    assert created.color == "#4f46e5"
    assert created.session_count == 0
    assert created.archived is False

    projects = await svc.list_projects(session, org_id)
    assert len(projects) == 1
    assert projects[0].id == created.id


@pytest.mark.asyncio
async def test_update_project_fields() -> None:
    org_id = uuid4()
    session = await _make_session()
    p = await svc.create_project(session, org_id, ChatProjectCreate(name="Q2 Work"))

    updated = await svc.update_project(
        session,
        org_id,
        p.id,
        ChatProjectUpdate(name="Q2 Magnetik Work", color="#06b6d4", sort_order=5),
    )
    assert updated.name == "Q2 Magnetik Work"
    assert updated.color == "#06b6d4"
    assert updated.sort_order == 5


@pytest.mark.asyncio
async def test_assign_and_unassign_session() -> None:
    org_id = uuid4()
    session = await _make_session()
    p = await svc.create_project(session, org_id, ChatProjectCreate(name="Active"))
    session_key = "agent:mc-gateway-abc:chat-deadbeef"

    await svc.assign_session(session, org_id, session_key, p.id)
    assignments = await svc.get_assignments(session, org_id)
    assert assignments[session_key] == str(p.id)

    # session_count reflects the assignment
    projects = await svc.list_projects(session, org_id)
    assert projects[0].session_count == 1

    # Unassign
    await svc.assign_session(session, org_id, session_key, None)
    assignments = await svc.get_assignments(session, org_id)
    assert session_key not in assignments

    projects = await svc.list_projects(session, org_id)
    assert projects[0].session_count == 0


@pytest.mark.asyncio
async def test_delete_project_archives_and_clears_assignments() -> None:
    org_id = uuid4()
    session = await _make_session()
    p = await svc.create_project(session, org_id, ChatProjectCreate(name="Temp"))
    session_key = "agent:mc-gateway-abc:chat-aaaa"
    await svc.assign_session(session, org_id, session_key, p.id)

    await svc.delete_project(session, org_id, p.id)

    # Archived project is hidden by default
    projects = await svc.list_projects(session, org_id)
    assert projects == []

    # And visible again when include_archived=True
    projects = await svc.list_projects(session, org_id, include_archived=True)
    assert len(projects) == 1
    assert projects[0].archived is True

    # Its assignments are cleared
    assignments = await svc.get_assignments(session, org_id)
    assert session_key not in assignments


@pytest.mark.asyncio
async def test_org_isolation() -> None:
    org_a = uuid4()
    org_b = uuid4()
    session = await _make_session()

    pa = await svc.create_project(session, org_a, ChatProjectCreate(name="A Project"))
    pb = await svc.create_project(session, org_b, ChatProjectCreate(name="B Project"))
    session_key = "agent:mc-gateway-shared:chat-xxx"

    await svc.assign_session(session, org_a, session_key, pa.id)

    # Org A sees its project + assignment
    a_projects = await svc.list_projects(session, org_a)
    a_assignments = await svc.get_assignments(session, org_a)
    assert len(a_projects) == 1
    assert a_projects[0].id == pa.id
    assert a_assignments.get(session_key) == str(pa.id)

    # Org B sees its project only, no assignment
    b_projects = await svc.list_projects(session, org_b)
    b_assignments = await svc.get_assignments(session, org_b)
    assert len(b_projects) == 1
    assert b_projects[0].id == pb.id
    assert session_key not in b_assignments


@pytest.mark.asyncio
async def test_assigning_to_nonexistent_project_raises() -> None:
    org_id = uuid4()
    session = await _make_session()
    fake_id = uuid4()

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await svc.assign_session(
            session,
            org_id,
            "agent:mc-gateway-abc:chat-missing",
            fake_id,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_cross_org_project_assignment_rejected() -> None:
    """Org A cannot assign a session to org B's project."""
    org_a = uuid4()
    org_b = uuid4()
    session = await _make_session()

    pb = await svc.create_project(session, org_b, ChatProjectCreate(name="B Project"))

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await svc.assign_session(
            session,
            org_a,
            "agent:mc-gateway-a:chat-xx",
            pb.id,
        )
    assert exc.value.status_code == 404
