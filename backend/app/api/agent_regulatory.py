"""Agent-scoped regulatory tracker endpoint (item 101 v2 Phase 1b.2).

Mirrors ``agent_org_context.py`` shape — separate router so the agent
auth surface is decoupled from the user CRUD surface and the
unauthenticated public snapshot. Currently exposes one read endpoint
that surfaces actionable tasks for chat reply contexts (the agent
typically asks "what's blocking us this week?" before drafting a
status update).

Returns incomplete tasks tagged ``critical`` OR with an overdue
``due_date``. Defense-in-depth filters all rows through the org's
FK chain (Task → Phase → Stream → org) — even though the agent's
board is org-scoped, the SQL never trusts the agent context alone.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select

from app.core.agent_auth import AgentAuthContext, get_agent_auth_context
from app.core.logging import get_logger
from app.db.session import get_session
from app.models.boards import Board
from app.models.organization_settings import DEFAULT_FEATURE_FLAGS, OrganizationSettings
from app.models.regulatory import (
    RegulatoryPhase,
    RegulatoryStream,
    RegulatoryTag,
    RegulatoryTask,
    RegulatoryTaskTag,
)

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)
router = APIRouter(prefix="/agent/regulatory", tags=["agent"])

SESSION_DEP = Depends(get_session)
AGENT_CTX_DEP = Depends(get_agent_auth_context)


async def _resolve_org_id(agent_ctx: AgentAuthContext, session: AsyncSession) -> UUID:
    """Resolve organization_id from the agent's linked board."""
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


async def _require_regulatory(org_id: UUID, session: AsyncSession) -> None:
    result = await session.execute(
        select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
    )
    settings = result.scalars().first()
    flags = settings.feature_flags if settings else dict(DEFAULT_FEATURE_FLAGS)
    if not flags.get("regulatory", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Feature 'regulatory' is not enabled for this organization.",
        )


@router.get("/active-tasks")
async def list_active_tasks(
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[dict[str, Any]]:
    """Return incomplete tasks tagged ``critical`` OR with an overdue due_date.

    Joins through Phase → Stream to scope by org. Returns a flat list
    ranked by overdue-first then by stream sort_order — the calling skill
    composes this into a chat reply.
    """
    org_id = await _resolve_org_id(agent_ctx, session)
    await _require_regulatory(org_id, session)

    now = datetime.now(timezone.utc)

    # The OR clause: tagged "critical" OR overdue.
    # Subquery for tag-based filter — tag slug "critical" within this org.
    critical_task_ids_subq = (
        select(RegulatoryTaskTag.task_id)
        .join(RegulatoryTag, RegulatoryTag.id == RegulatoryTaskTag.tag_id)
        .where(
            RegulatoryTag.organization_id == org_id,
            RegulatoryTag.slug == "critical",
        )
    )

    stmt = (
        select(RegulatoryTask, RegulatoryPhase, RegulatoryStream)
        .join(RegulatoryPhase, RegulatoryPhase.id == RegulatoryTask.phase_id)
        .join(RegulatoryStream, RegulatoryStream.id == RegulatoryPhase.stream_id)
        .where(
            RegulatoryStream.organization_id == org_id,
            RegulatoryTask.completed.is_(False),  # type: ignore[union-attr]
            or_(
                RegulatoryTask.id.in_(critical_task_ids_subq),  # type: ignore[attr-defined]
                RegulatoryTask.due_date < now,  # type: ignore[operator]
            ),
        )
        .order_by(
            RegulatoryStream.sort_order,
            RegulatoryPhase.sort_order,
            RegulatoryTask.sort_order,
        )
    )
    result = await session.execute(stmt)
    rows = result.all()

    return [
        {
            "task_id": str(task.id),
            "body": task.body,
            "note": task.note,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "overdue": bool(task.due_date and task.due_date < now),
            "phase_name": phase.name,
            "phase_badge_kind": phase.badge_kind,
            "stream_slug": stream.slug,
            "stream_name": stream.name,
            "stream_color_token": stream.color_token,
        }
        for task, phase, stream in rows
    ]


__all__ = ["router"]
