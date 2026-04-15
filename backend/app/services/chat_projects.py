"""Chat project service — CRUD + session-to-project assignment.

Projects themselves live in the `chat_projects` table. Assignments (which
session belongs to which project) live in OrgConfigData under category
`session_project_assignments`, key `assignments`, with value_json holding a
`{session_key: project_id}` dict. This avoids FK-dangling with gateway-owned
session keys.

See docs/technical/chat-reorganization-plan.md Tier 1.4 for rationale.
"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.time import utcnow
from app.models.chat_projects import ChatProject
from app.models.org_config import OrgConfigData
from app.schemas.chat_projects import (
    ChatProjectCreate,
    ChatProjectRead,
    ChatProjectUpdate,
)

_ASSIGNMENTS_CATEGORY = "session_project_assignments"
_ASSIGNMENTS_KEY = "assignments"


async def list_projects(
    session: AsyncSession,
    organization_id: UUID,
    *,
    include_archived: bool = False,
) -> list[ChatProjectRead]:
    """List all projects for an org, with session counts."""
    stmt = select(ChatProject).where(ChatProject.organization_id == organization_id)
    if not include_archived:
        stmt = stmt.where(~ChatProject.archived)
    stmt = stmt.order_by(ChatProject.sort_order, ChatProject.created_at)

    result = await session.exec(stmt)
    projects = result.all()

    assignments = await _get_assignments(session, organization_id)
    counts: dict[str, int] = {}
    for _session_key, project_id in assignments.items():
        counts[project_id] = counts.get(project_id, 0) + 1

    return [
        ChatProjectRead(
            id=p.id,
            name=p.name,
            description=p.description,
            color=p.color,
            sort_order=p.sort_order,
            archived=p.archived,
            session_count=counts.get(str(p.id), 0),
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in projects
    ]


async def create_project(
    session: AsyncSession,
    organization_id: UUID,
    payload: ChatProjectCreate,
) -> ChatProjectRead:
    """Create a new chat project."""
    project = ChatProject(
        organization_id=organization_id,
        name=payload.name,
        description=payload.description,
        color=payload.color,
        sort_order=payload.sort_order,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return _to_read(project, session_count=0)


async def update_project(
    session: AsyncSession,
    organization_id: UUID,
    project_id: UUID,
    payload: ChatProjectUpdate,
) -> ChatProjectRead:
    """Update an existing chat project."""
    project = await _get_or_404(session, organization_id, project_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(project, field, value)
    project.updated_at = utcnow()
    session.add(project)
    await session.commit()
    await session.refresh(project)

    count = await _count_sessions(session, organization_id, project_id)
    return _to_read(project, session_count=count)


async def delete_project(
    session: AsyncSession,
    organization_id: UUID,
    project_id: UUID,
) -> None:
    """Soft-delete a project (archived=True) + unassign all its sessions."""
    project = await _get_or_404(session, organization_id, project_id)
    project.archived = True
    project.updated_at = utcnow()
    session.add(project)

    assignments = await _get_assignments(session, organization_id)
    pid_str = str(project_id)
    changed = [k for k, v in assignments.items() if v == pid_str]
    for k in changed:
        del assignments[k]
    if changed:
        await _save_assignments(session, organization_id, assignments)

    await session.commit()


async def assign_session(
    session: AsyncSession,
    organization_id: UUID,
    session_key: str,
    project_id: UUID | None,
) -> None:
    """Assign a session to a project, or clear the assignment if project_id is None."""
    if project_id is not None:
        # Validate the project exists and belongs to this org.
        await _get_or_404(session, organization_id, project_id)

    assignments = await _get_assignments(session, organization_id)
    if project_id is None:
        assignments.pop(session_key, None)
    else:
        assignments[session_key] = str(project_id)

    await _save_assignments(session, organization_id, assignments)
    await session.commit()


async def get_assignments(
    session: AsyncSession,
    organization_id: UUID,
) -> dict[str, str]:
    """Public helper to load session→project assignments for the org."""
    return await _get_assignments(session, organization_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_or_404(
    session: AsyncSession, organization_id: UUID, project_id: UUID
) -> ChatProject:
    result = await session.exec(
        select(ChatProject).where(
            ChatProject.id == project_id,
            ChatProject.organization_id == organization_id,
        )
    )
    project = result.first()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat project not found",
        )
    return project


async def _count_sessions(session: AsyncSession, organization_id: UUID, project_id: UUID) -> int:
    assignments = await _get_assignments(session, organization_id)
    pid_str = str(project_id)
    return sum(1 for v in assignments.values() if v == pid_str)


async def _get_assignments(session: AsyncSession, organization_id: UUID) -> dict[str, str]:
    result = await session.exec(
        select(OrgConfigData).where(
            OrgConfigData.organization_id == organization_id,
            OrgConfigData.category == _ASSIGNMENTS_CATEGORY,
            OrgConfigData.key == _ASSIGNMENTS_KEY,
        )
    )
    row = result.first()
    if row is None:
        return {}
    try:
        data = json.loads(row.value_json)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


async def _save_assignments(
    session: AsyncSession,
    organization_id: UUID,
    assignments: dict[str, str],
) -> None:
    payload = json.dumps(assignments)
    result = await session.exec(
        select(OrgConfigData).where(
            OrgConfigData.organization_id == organization_id,
            OrgConfigData.category == _ASSIGNMENTS_CATEGORY,
            OrgConfigData.key == _ASSIGNMENTS_KEY,
        )
    )
    row = result.first()
    if row is None:
        session.add(
            OrgConfigData(
                organization_id=organization_id,
                category=_ASSIGNMENTS_CATEGORY,
                key=_ASSIGNMENTS_KEY,
                label="Session Project Assignments",
                value_json=payload,
            )
        )
    else:
        row.value_json = payload
        row.updated_at = utcnow()
        session.add(row)


def _to_read(project: ChatProject, *, session_count: int) -> ChatProjectRead:
    return ChatProjectRead(
        id=project.id,
        name=project.name,
        description=project.description,
        color=project.color,
        sort_order=project.sort_order,
        archived=project.archived,
        session_count=session_count,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )
