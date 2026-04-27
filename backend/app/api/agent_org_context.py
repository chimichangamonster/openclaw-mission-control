"""Agent-scoped org-context query endpoint.

Mirrors ``agent_memory_vector.py`` shape — separate router so the agent
auth surface is decoupled from the user CRUD surface. Currently exposes
search only (Phase 1); future phases may expose store/forget if agents
need to write context (likely never — context is human-curated).

Visibility scoping is strict: agents only ever see ``visibility="shared"``
rows. Private files are reserved for the human owner + org admins via the
user CRUD surface.
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
from app.schemas.org_context import OrgContextSearch, OrgContextSearchHit

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)
router = APIRouter(prefix="/agent/org-context", tags=["agent"])

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


async def _require_org_context(org_id: UUID, session: AsyncSession) -> None:
    """Check that the org_context feature flag is enabled for this org."""
    result = await session.execute(
        select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
    )
    settings = result.scalars().first()
    flags = settings.feature_flags if settings else dict(DEFAULT_FEATURE_FLAGS)
    if not flags.get("org_context", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Feature 'org_context' is not enabled for this organization.",
        )


@router.post("/search", response_model=list[OrgContextSearchHit])
async def search_org_context(
    body: OrgContextSearch,
    agent_ctx: AgentAuthContext = AGENT_CTX_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[dict[str, Any]]:
    """Semantic search across this org's shared context files.

    Returns ranked hits with full citation metadata (filename, snippet,
    age, living-data flag) so the calling skill can age-stamp citations
    and warn on stale-living-data combinations.
    """
    from app.services.embedding import search_org_context as _search

    org_id = await _resolve_org_id(agent_ctx, session)
    await _require_org_context(org_id, session)

    return await _search(
        org_id=org_id,
        query=body.query,
        limit=body.limit,
        category_filter=body.category_filter,
        include_private=False,  # Agents never see private files
    )
