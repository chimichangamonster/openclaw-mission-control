"""Skill config resolution API — resolve portfolio/board names to UUIDs at runtime.

Skills call GET /skill-config/resolve at startup to get org-specific IDs
instead of hardcoding UUIDs. This makes skills portable across tenants.
"""


from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlmodel import select

from app.api.deps import ORG_ACTOR_DEP
from app.db.session import async_session_maker
from app.models.boards import Board
from app.models.paper_trading import PaperPortfolio
from app.services.organizations import OrganizationContext

router = APIRouter(prefix="/skill-config", tags=["skill-config"])


@router.get("/resolve")
async def resolve_skill_config(
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
    portfolios: list[str] = Query(default=[]),
    boards: list[str] = Query(default=[]),
) -> Any:
    """Resolve portfolio and board names to UUIDs for the calling org.

    Skills call this once at startup instead of hardcoding IDs.

    Example:
        GET /skill-config/resolve?portfolios=Stocks&portfolios=Sports+Betting&boards=Stock+Watchlist
    """
    org_id = org_ctx.organization.id
    result: dict[str, Any] = {"portfolios": {}, "boards": {}}

    async with async_session_maker() as session:
        if portfolios:
            rows = await session.execute(
                select(PaperPortfolio).where(
                    PaperPortfolio.organization_id == org_id,
                )
            )
            for p in rows.scalars().all():
                if p.name in portfolios:
                    result["portfolios"][p.name] = str(p.id)

        if boards:
            rows = await session.execute(
                select(Board).where(
                    Board.organization_id == org_id,
                )
            )
            for b in rows.scalars().all():
                if b.name in boards:
                    result["boards"][b.name] = str(b.id)

    return result
