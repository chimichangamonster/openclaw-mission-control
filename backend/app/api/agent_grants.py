"""Agent-scoped grants tracker endpoint (item 107 v2 Phase 1).

Mirrors ``agent_regulatory.py`` shape — separate router so the agent
auth surface is decoupled from the user CRUD surface. Currently exposes
one read endpoint that surfaces upcoming reporting deadlines + overdue
draws for chat reply contexts (the agent typically asks "what's coming
up that we'd lose money on if we missed?").
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.core.agent_auth import AgentAuthContext, get_agent_auth_context
from app.core.logging import get_logger
from app.db.session import get_session
from app.models.boards import Board
from app.models.grants import Grant, GrantReportingDeadline
from app.models.organization_settings import DEFAULT_FEATURE_FLAGS, OrganizationSettings
from app.schemas.grants import AgentUpcomingDeadline

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)
router = APIRouter(prefix="/agent/grants", tags=["agent"])

SESSION_DEP = Depends(get_session)
AGENT_CTX_DEP = Depends(get_agent_auth_context)


async def _resolve_org_id(agent_ctx: AgentAuthContext, session: AsyncSession) -> UUID:
    agent = agent_ctx.agent
    if agent.board_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent has no board — cannot resolve organization.",
        )
    board = await session.get(Board, agent.board_id)
    if not board or not board.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent's board has no organization.",
        )
    return board.organization_id


async def _require_grants(org_id: UUID, session: AsyncSession) -> None:
    result = await session.execute(
        select(OrganizationSettings).where(
            OrganizationSettings.organization_id == org_id  # type: ignore[arg-type]
        )
    )
    settings = result.scalars().first()
    flags = settings.feature_flags if settings else dict(DEFAULT_FEATURE_FLAGS)
    if not flags.get("grants_tracker", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Feature 'grants_tracker' is not enabled for this organization.",
        )


@router.get("/upcoming-deadlines", response_model=list[AgentUpcomingDeadline])
async def list_upcoming_deadlines(
    horizon_days: int = Query(default=60, ge=1, le=365),
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[AgentUpcomingDeadline]:
    """Return grant reporting deadlines within ``horizon_days``.

    Includes past-due deadlines (status="upcoming" but date < today) so
    the agent can flag missed reports — those are the high-liability
    cases (claw-back risk per determinism-first memory).

    Ordered by deadline_date ascending: most-urgent first.
    """
    org_id = await _resolve_org_id(agent_ctx, session)
    await _require_grants(org_id, session)

    today = date.today()
    horizon = today + timedelta(days=horizon_days)

    stmt = (
        select(GrantReportingDeadline, Grant)
        .join(Grant, Grant.id == GrantReportingDeadline.grant_id)  # type: ignore[arg-type]
        .where(
            Grant.organization_id == org_id,  # type: ignore[arg-type]
            GrantReportingDeadline.deadline_date <= horizon,  # type: ignore[arg-type]
            GrantReportingDeadline.status == "upcoming",  # type: ignore[arg-type]
        )
        .order_by(GrantReportingDeadline.deadline_date)  # type: ignore[arg-type]
    )
    result = await session.execute(stmt)
    rows = result.all()

    return [
        AgentUpcomingDeadline(
            grant_id=grant.id,
            grant_program_name=grant.program_name,
            granting_body=grant.granting_body,
            deadline_date=dl.deadline_date,
            deadline_type=dl.deadline_type,
            description=dl.description,
            days_until=(dl.deadline_date - today).days,
            status=dl.status,
        )
        for dl, grant in rows
    ]


__all__ = ["router"]
