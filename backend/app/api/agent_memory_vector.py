"""Agent-scoped vector memory endpoints — store, search, forget.

Agents call these endpoints to persist and recall semantic memories.
All operations are org-scoped via the agent's board → organization link.
Gated by the ``agent_memory`` feature flag.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select

from app.core.agent_auth import AgentAuthContext, get_agent_auth_context
from app.core.logging import get_logger
from app.db.session import get_session
from app.models.boards import Board
from app.models.organization_settings import DEFAULT_FEATURE_FLAGS, OrganizationSettings
from app.schemas.vector_memory import (
    VectorMemoryForget,
    VectorMemoryRead,
    VectorMemorySearch,
    VectorMemoryStore,
)

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)
router = APIRouter(prefix="/agent/memory/vector", tags=["agent"])

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


async def _require_agent_memory(org_id: UUID, session: AsyncSession) -> None:
    """Check that the agent_memory feature flag is enabled for this org."""
    result = await session.execute(
        select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
    )
    settings = result.scalars().first()
    flags = settings.feature_flags if settings else dict(DEFAULT_FEATURE_FLAGS)
    if not flags.get("agent_memory", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Feature 'agent_memory' is not enabled for this organization.",
        )


@router.post("/store", response_model=dict[str, Any])
async def store_memory(
    body: VectorMemoryStore,
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """Store a new semantic memory for this organization."""
    from app.services.embedding import store_memory as _store

    org_id = await _resolve_org_id(agent_ctx, session)
    await _require_agent_memory(org_id, session)

    memory = await _store(
        org_id=org_id,
        content=body.content,
        source=body.source,
        agent_id=agent_ctx.agent.name or str(agent_ctx.agent.id),
        metadata=body.extra,
        ttl_days=body.ttl_days,
    )

    return {
        "id": str(memory.id),
        "source": memory.source,
        "created_at": memory.created_at.isoformat(),
    }


@router.post("/search", response_model=list[VectorMemoryRead])
async def search_memory(
    body: VectorMemorySearch,
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[dict[str, Any]]:
    """Semantic search across this organization's memories."""
    from app.services.embedding import search_memory as _search

    org_id = await _resolve_org_id(agent_ctx, session)
    await _require_agent_memory(org_id, session)

    return await _search(
        org_id=org_id,
        query=body.query,
        limit=body.limit,
        source_filter=body.source_filter,
    )


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: UUID,
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, bool]:
    """Delete a specific memory by ID."""
    from app.services.embedding import forget_memory as _forget

    org_id = await _resolve_org_id(agent_ctx, session)
    await _require_agent_memory(org_id, session)

    deleted = await _forget(org_id=org_id, memory_id=memory_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found.",
        )
    return {"deleted": True}


@router.post("/forget")
async def forget_by_source(
    body: VectorMemoryForget,
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, int]:
    """Bulk delete memories by source prefix."""
    from app.services.embedding import forget_by_source as _forget_source

    org_id = await _resolve_org_id(agent_ctx, session)
    await _require_agent_memory(org_id, session)

    count = await _forget_source(org_id=org_id, source=body.source)
    return {"deleted": count}
