"""Ecosystem intelligence API — list trending repos + manual refresh.

Gated by the `ecosystem_intel` feature flag (enabled per-org). All members of
an enabled org can read; only admin+ can trigger a manual refresh.
"""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import (
    AUTH_DEP,
    ORG_RATE_LIMIT_DEP,
    SESSION_DEP,
    require_feature,
    require_org_member,
    require_org_role,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.models.ecosystem_repos import EcosystemRepo
from app.schemas.ecosystem_intel import (
    EcosystemRefreshResult,
    EcosystemRepoRead,
    EcosystemStatus,
)
from app.services import ecosystem_intel as ecosystem_service
from app.services.organizations import OrganizationContext

logger = get_logger(__name__)


router = APIRouter(
    prefix="/ecosystem-intel",
    tags=["ecosystem-intel"],
    dependencies=[
        ORG_RATE_LIMIT_DEP,
        Depends(require_feature("ecosystem_intel")),
    ],
)

ORG_MEMBER_DEP = Depends(require_org_member)
ADMIN_DEP = Depends(require_org_role("admin"))

CategoryFilter = Literal["all", "ai_ml", "swe", "skills_ecosystem", "trending"]
SortField = Literal["stars", "forks", "growth_24h"]


def _parse_topics(topics_json: str) -> list[str]:
    try:
        data = json.loads(topics_json)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [t for t in data if isinstance(t, str)]


@router.get("", response_model=list[EcosystemRepoRead])
async def list_ecosystem_repos(
    category: CategoryFilter = "all",
    sort: SortField = "stars",
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=200, ge=1, le=500),
    session: AsyncSession = SESSION_DEP,
    _ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> list[EcosystemRepoRead]:
    """List trending repos with optional category filter, sort, and search."""
    stmt = select(EcosystemRepo)

    if category == "trending":
        # "Trending" is a synthetic bucket — include both *_trending categories.
        stmt = stmt.where(EcosystemRepo.category.in_(["ai_ml_trending", "swe_trending"]))  # type: ignore[attr-defined]
    elif category == "ai_ml":
        stmt = stmt.where(EcosystemRepo.category.in_(["ai_ml", "ai_ml_trending"]))  # type: ignore[attr-defined]
    elif category == "swe":
        stmt = stmt.where(EcosystemRepo.category.in_(["swe", "swe_trending"]))  # type: ignore[attr-defined]
    elif category == "skills_ecosystem":
        stmt = stmt.where(EcosystemRepo.category == "skills_ecosystem")
    # "all" — no filter

    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(EcosystemRepo.full_name.ilike(like))  # type: ignore[attr-defined]

    if sort == "forks":
        stmt = stmt.order_by(EcosystemRepo.forks.desc())  # type: ignore[attr-defined]
    else:
        # `growth_24h` requires a join we don't want in the list query — sort by
        # stars and let the response include `growth_24h` for client-side resort.
        stmt = stmt.order_by(EcosystemRepo.stars.desc())  # type: ignore[attr-defined]

    stmt = stmt.limit(limit)
    result = await session.exec(stmt)
    repos = list(result.all())

    deltas = await ecosystem_service.get_growth_deltas(
        session, [r.id for r in repos], hours=24
    )

    pinned_full_names = {f"{owner}/{name}" for owner, name in ecosystem_service.PINNED_REPOS}

    out: list[EcosystemRepoRead] = [
        EcosystemRepoRead(
            id=r.id,
            full_name=r.full_name,
            owner=r.owner,
            name=r.name,
            description=r.description,
            html_url=r.html_url,
            language=r.language,
            category=r.category,
            stars=r.stars,
            forks=r.forks,
            open_issues=r.open_issues,
            topics=_parse_topics(r.topics_json),
            pushed_at=r.pushed_at,
            repo_created_at=r.repo_created_at,
            first_seen_at=r.first_seen_at,
            last_synced_at=r.last_synced_at,
            growth_24h=deltas.get(str(r.id), 0),
            is_pinned=r.full_name in pinned_full_names,
        )
        for r in repos
    ]

    if sort == "growth_24h":
        out.sort(key=lambda x: x.growth_24h, reverse=True)

    return out


@router.get("/status", response_model=EcosystemStatus)
async def get_ecosystem_status(
    session: AsyncSession = SESSION_DEP,
    _ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> EcosystemStatus:
    """Return repo count + most-recent sync timestamp + token presence."""
    count_stmt = select(EcosystemRepo)
    count_result = await session.exec(count_stmt)
    repos = list(count_result.all())

    last_sync = max((r.last_synced_at for r in repos), default=None)
    return EcosystemStatus(
        repo_count=len(repos),
        last_synced_at=last_sync,
        has_token=bool(settings.github_api_token),
    )


@router.post("/refresh", response_model=EcosystemRefreshResult)
async def refresh_ecosystem(
    session: AsyncSession = SESSION_DEP,
    _ctx: OrganizationContext = ADMIN_DEP,
    _auth: object = AUTH_DEP,
) -> EcosystemRefreshResult:
    """Trigger a manual refresh of the ecosystem feed (admin+ only)."""
    result = await ecosystem_service.refresh_ecosystem(session)
    logger.info(
        "ecosystem_intel.manual_refresh fetched=%d upserted=%d error=%s",
        result.fetched,
        result.upserted,
        result.error,
    )
    return EcosystemRefreshResult(
        fetched=result.fetched,
        upserted=result.upserted,
        snapshots=result.snapshots,
        started_at=result.started_at,
        finished_at=result.finished_at,
        error=result.error,
    )
