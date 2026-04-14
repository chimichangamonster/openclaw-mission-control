"""Chat projects API — CRUD + session assignment.

Member role can list projects and read assignments. Operator+ role is required
to mutate (create, update, archive, assign). Projects are org-scoped.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AUTH_DEP,
    ORG_RATE_LIMIT_DEP,
    SESSION_DEP,
    require_org_member,
    require_org_role,
)
from app.core.logging import get_logger
from app.schemas.chat_projects import (
    ChatProjectCreate,
    ChatProjectRead,
    ChatProjectUpdate,
    SessionProjectAssignment,
)
from app.services import chat_projects as chat_projects_service
from app.services.organizations import OrganizationContext

logger = get_logger(__name__)

router = APIRouter(
    prefix="/chat-projects",
    tags=["chat-projects"],
    dependencies=[ORG_RATE_LIMIT_DEP],
)

ORG_MEMBER_DEP = Depends(require_org_member)
OPERATOR_DEP = Depends(require_org_role("operator"))


@router.get("", response_model=list[ChatProjectRead])
async def list_chat_projects(
    include_archived: bool = False,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> list[ChatProjectRead]:
    return await chat_projects_service.list_projects(
        session,
        ctx.organization.id,
        include_archived=include_archived,
    )


@router.post(
    "",
    response_model=ChatProjectRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat_project(
    payload: ChatProjectCreate,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = OPERATOR_DEP,
    _auth=AUTH_DEP,
) -> ChatProjectRead:
    return await chat_projects_service.create_project(
        session,
        ctx.organization.id,
        payload,
    )


@router.patch("/{project_id}", response_model=ChatProjectRead)
async def update_chat_project(
    project_id: UUID,
    payload: ChatProjectUpdate,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = OPERATOR_DEP,
    _auth=AUTH_DEP,
) -> ChatProjectRead:
    return await chat_projects_service.update_project(
        session,
        ctx.organization.id,
        project_id,
        payload,
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_project(
    project_id: UUID,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = OPERATOR_DEP,
    _auth=AUTH_DEP,
) -> None:
    await chat_projects_service.delete_project(
        session,
        ctx.organization.id,
        project_id,
    )


@router.get("/assignments", response_model=dict[str, str])
async def list_session_assignments(
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> dict[str, str]:
    """Return the full session_key -> project_id map for the current org."""
    return await chat_projects_service.get_assignments(session, ctx.organization.id)


@router.post(
    "/assignments/{session_key:path}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def assign_session_to_project(
    session_key: str,
    payload: SessionProjectAssignment,
    session: AsyncSession = SESSION_DEP,
    ctx: OrganizationContext = OPERATOR_DEP,
    _auth=AUTH_DEP,
) -> None:
    """Assign a session to a project, or clear the assignment if project_id is null."""
    await chat_projects_service.assign_session(
        session,
        ctx.organization.id,
        session_key,
        payload.project_id,
    )
