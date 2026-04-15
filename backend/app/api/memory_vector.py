"""User-facing vector memory endpoints — list, search, delete.

Org-scoped via standard user auth. Gated by ``agent_memory`` feature flag.
Complements the agent-only endpoints in ``agent_memory_vector.py``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import ORG_MEMBER_DEP, require_feature
from app.core.logging import get_logger
from app.db.session import get_session
from app.models.vector_memory import VectorMemory
from app.schemas.vector_memory import VectorMemoryRead, VectorMemorySearch
from app.services.organizations import OrganizationContext

logger = get_logger(__name__)

router = APIRouter(
    prefix="/memory/vector",
    tags=["memory"],
    dependencies=[Depends(require_feature("agent_memory"))],
)

SESSION_DEP = Depends(get_session)


@router.get("")
async def list_memories(
    org_ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
    source: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List vector memories for the current org with pagination."""
    org_id = org_ctx.organization.id

    source_filter = col(VectorMemory.source).startswith(source) if source else None

    count_q = (
        select(func.count()).select_from(VectorMemory).where(VectorMemory.organization_id == org_id)
    )
    if source_filter is not None:
        count_q = count_q.where(source_filter)
    count_result = await session.execute(count_q)
    total = count_result.scalar() or 0

    q = (
        select(VectorMemory)
        .where(VectorMemory.organization_id == org_id)
        .order_by(col(VectorMemory.created_at).desc())
        .offset(offset)
        .limit(limit)
    )
    if source_filter is not None:
        q = q.where(source_filter)
    result = await session.execute(q)
    rows = result.scalars().all()

    return {
        "items": [
            {
                "id": str(m.id),
                "content": m.content,
                "source": m.source,
                "agent_id": m.agent_id,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "expires_at": m.expires_at.isoformat() if m.expires_at else None,
            }
            for m in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/search", response_model=list[VectorMemoryRead])
async def search_memories(
    body: VectorMemorySearch,
    org_ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[dict[str, Any]]:
    """Semantic search across vector memories for the current org."""
    from app.services.embedding import search_memory

    return await search_memory(
        org_id=org_ctx.organization.id,
        query=body.query,
        limit=body.limit,
        source_filter=body.source_filter,
    )


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: UUID,
    org_ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, bool]:
    """Delete a specific memory by ID."""
    from app.services.embedding import forget_memory

    deleted = await forget_memory(
        org_id=org_ctx.organization.id,
        memory_id=memory_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found.",
        )
    return {"deleted": True}


@router.get("/stats")
async def memory_stats(
    org_ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """Get summary statistics for the org's vector memories."""
    org_id = org_ctx.organization.id

    total_q = (
        select(func.count()).select_from(VectorMemory).where(VectorMemory.organization_id == org_id)
    )
    total = (await session.execute(total_q)).scalar() or 0

    sources_q = (
        select(VectorMemory.source, func.count().label("count"))
        .where(VectorMemory.organization_id == org_id)
        .group_by(VectorMemory.source)
        .order_by(func.count().desc())
        .limit(20)
    )
    sources_result = await session.execute(sources_q)
    sources = [{"source": r[0], "count": r[1]} for r in sources_result.all()]

    return {
        "total_memories": total,
        "sources": sources,
    }
