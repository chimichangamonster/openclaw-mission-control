"""Grants tracker CRUD endpoints (item 107 v2 Phase 1).

Sibling substrate to ``app.api.regulatory``. Same auth / isolation /
feature-flag posture, mirrored deliberately so the two surfaces share a
mental model.

Auth tiers per planning doc item 107 v2 section 3:
  - admin+:    grant DELETE
  - operator+: grant create/edit, draws, deadlines, prerequisite linking
  - member+:   reads (no write)

Isolation contract:
  Direct-owned tables (Grant) filter by organization_id.
  Indirect-owned tables (GrantDrawSchedule, GrantReportingDeadline,
  GrantPrerequisiteTask) trace back to the org via FK chain on every
  read AND validate same-org-membership of all referenced rows on every
  write. The model layer permits cross-org mixing — only this module
  prevents it. M2M to RegulatoryTask is the silent-leak surface.

Determinism posture per ``feedback_determinism_first_for_high_liability.md``:
zero LLM in path. All amounts/dates/statuses are operator-entered SQL.
Audit trail via created_at/updated_at; mutations are operator+ role
(audit-logged through OrganizationContext).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import (
    ORG_MEMBER_DEP,
    ORG_RATE_LIMIT_DEP,
    SESSION_DEP,
    require_feature,
    require_org_role,
)
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.grants import (
    Grant,
    GrantDrawSchedule,
    GrantPrerequisiteTask,
    GrantReportingDeadline,
)
from app.models.regulatory import RegulatoryPhase, RegulatoryStream, RegulatoryTask
from app.schemas.grants import (
    GrantCreate,
    GrantDeadlineCreate,
    GrantDeadlineRead,
    GrantDeadlineUpdate,
    GrantDrawCreate,
    GrantDrawRead,
    GrantDrawUpdate,
    GrantPrerequisiteCreate,
    GrantPrerequisiteRead,
    GrantPrerequisiteStatus,
    GrantRead,
    GrantReadDetail,
    GrantUpdate,
)
from app.services.organizations import OrganizationContext

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)

# Closures captured at module load so tests can override via
# ``app.dependency_overrides[GRANTS_FEATURE_GATE] = ...``. Each call to
# require_*() returns a NEW closure; without these stable names tests would
# override different instances than the router uses (per
# feedback_capture_factory_deps_for_test_override.md).
_REQUIRE_ADMIN = require_org_role("admin")
_REQUIRE_OPERATOR = require_org_role("operator")
GRANTS_FEATURE_GATE = require_feature("grants_tracker")

ORG_ADMIN_DEP = Depends(_REQUIRE_ADMIN)
ORG_OPERATOR_DEP = Depends(_REQUIRE_OPERATOR)

router = APIRouter(
    prefix="/grants",
    tags=["grants"],
    dependencies=[ORG_RATE_LIMIT_DEP, Depends(GRANTS_FEATURE_GATE)],
)


# ---------------------------------------------------------------------------
# Internal helpers — FK-chain isolation walks
# ---------------------------------------------------------------------------


async def _grant_for_org(grant_id: UUID, org_id: UUID, session: AsyncSession) -> Grant:
    """Load a grant and verify it belongs to the calling org.

    Raises 404 on missing or cross-org access (never leak existence).
    """
    grant = await session.get(Grant, grant_id)
    if grant is None or grant.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return grant


async def _draw_for_org(draw_id: UUID, org_id: UUID, session: AsyncSession) -> GrantDrawSchedule:
    draw = await session.get(GrantDrawSchedule, draw_id)
    if draw is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await _grant_for_org(draw.grant_id, org_id, session)
    return draw


async def _deadline_for_org(
    deadline_id: UUID, org_id: UUID, session: AsyncSession
) -> GrantReportingDeadline:
    dl = await session.get(GrantReportingDeadline, deadline_id)
    if dl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await _grant_for_org(dl.grant_id, org_id, session)
    return dl


async def _regulatory_task_for_org(
    task_id: UUID, org_id: UUID, session: AsyncSession
) -> RegulatoryTask:
    """Walk RegulatoryTask → Phase → Stream → org. Mirrors regulatory.py
    helper. Same-org guard for the M2M silent-leak surface.
    """
    task = await session.get(RegulatoryTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    phase = await session.get(RegulatoryPhase, task.phase_id)
    if phase is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    stream = await session.get(RegulatoryStream, phase.stream_id)
    if stream is None or stream.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return task


# ---------------------------------------------------------------------------
# Grant CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[GrantRead])
async def list_grants(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[Grant]:
    stmt = (
        select(Grant)
        .where(Grant.organization_id == ctx.organization.id)  # type: ignore[arg-type]
        .order_by(Grant.granting_body, Grant.program_name)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{grant_id}", response_model=GrantReadDetail)
async def get_grant(
    grant_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> GrantReadDetail:
    grant = await _grant_for_org(grant_id, ctx.organization.id, session)

    draws_stmt = (
        select(GrantDrawSchedule)
        .where(GrantDrawSchedule.grant_id == grant_id)  # type: ignore[arg-type]
        .order_by(GrantDrawSchedule.sort_order, GrantDrawSchedule.target_date)  # type: ignore[arg-type]
    )
    draws = list((await session.execute(draws_stmt)).scalars().all())

    deadlines_stmt = (
        select(GrantReportingDeadline)
        .where(GrantReportingDeadline.grant_id == grant_id)  # type: ignore[arg-type]
        .order_by(GrantReportingDeadline.deadline_date)  # type: ignore[arg-type]
    )
    deadlines = list((await session.execute(deadlines_stmt)).scalars().all())

    prereq_stmt = select(GrantPrerequisiteTask).where(
        GrantPrerequisiteTask.grant_id == grant_id  # type: ignore[arg-type]
    )
    prereq_links = list((await session.execute(prereq_stmt)).scalars().all())

    # Hydrate task body + completion status for display.
    prerequisites: list[GrantPrerequisiteRead] = []
    for link in prereq_links:
        task = await session.get(RegulatoryTask, link.regulatory_task_id)
        prerequisites.append(
            GrantPrerequisiteRead(
                grant_id=link.grant_id,
                regulatory_task_id=link.regulatory_task_id,
                label_override=link.label_override,
                is_critical=link.is_critical,
                created_at=link.created_at,
                task_body=task.body if task else None,
                task_completed=task.completed if task else None,
            )
        )

    return GrantReadDetail(
        **GrantRead.model_validate(grant).model_dump(),
        draws=[GrantDrawRead.model_validate(d) for d in draws],
        deadlines=[GrantDeadlineRead.model_validate(d) for d in deadlines],
        prerequisites=prerequisites,
    )


@router.post("", response_model=GrantRead, status_code=status.HTTP_201_CREATED)
async def create_grant(
    payload: GrantCreate,
    ctx: OrganizationContext = ORG_OPERATOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> Grant:
    grant = Grant(
        organization_id=ctx.organization.id,
        **payload.model_dump(exclude_unset=False),
    )
    session.add(grant)
    await session.commit()
    await session.refresh(grant)
    return grant


@router.patch("/{grant_id}", response_model=GrantRead)
async def update_grant(
    grant_id: UUID,
    payload: GrantUpdate,
    ctx: OrganizationContext = ORG_OPERATOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> Grant:
    grant = await _grant_for_org(grant_id, ctx.organization.id, session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(grant, field, value)
    grant.updated_at = utcnow()
    session.add(grant)
    await session.commit()
    await session.refresh(grant)
    return grant


@router.delete("/{grant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_grant(
    grant_id: UUID,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    grant = await _grant_for_org(grant_id, ctx.organization.id, session)
    await session.delete(grant)
    await session.commit()


# ---------------------------------------------------------------------------
# Draw schedule (operator+)
# ---------------------------------------------------------------------------


@router.post(
    "/{grant_id}/draws",
    response_model=GrantDrawRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_draw(
    grant_id: UUID,
    payload: GrantDrawCreate,
    ctx: OrganizationContext = ORG_OPERATOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> GrantDrawSchedule:
    await _grant_for_org(grant_id, ctx.organization.id, session)
    draw = GrantDrawSchedule(grant_id=grant_id, **payload.model_dump())
    session.add(draw)
    await session.commit()
    await session.refresh(draw)
    return draw


@router.patch("/draws/{draw_id}", response_model=GrantDrawRead)
async def update_draw(
    draw_id: UUID,
    payload: GrantDrawUpdate,
    ctx: OrganizationContext = ORG_OPERATOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> GrantDrawSchedule:
    draw = await _draw_for_org(draw_id, ctx.organization.id, session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(draw, field, value)
    draw.updated_at = utcnow()
    session.add(draw)
    await session.commit()
    await session.refresh(draw)
    return draw


@router.delete("/draws/{draw_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draw(
    draw_id: UUID,
    ctx: OrganizationContext = ORG_OPERATOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    draw = await _draw_for_org(draw_id, ctx.organization.id, session)
    await session.delete(draw)
    await session.commit()


# ---------------------------------------------------------------------------
# Reporting deadline (operator+)
# ---------------------------------------------------------------------------


@router.post(
    "/{grant_id}/deadlines",
    response_model=GrantDeadlineRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_deadline(
    grant_id: UUID,
    payload: GrantDeadlineCreate,
    ctx: OrganizationContext = ORG_OPERATOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> GrantReportingDeadline:
    await _grant_for_org(grant_id, ctx.organization.id, session)
    dl = GrantReportingDeadline(grant_id=grant_id, **payload.model_dump())
    session.add(dl)
    await session.commit()
    await session.refresh(dl)
    return dl


@router.patch("/deadlines/{deadline_id}", response_model=GrantDeadlineRead)
async def update_deadline(
    deadline_id: UUID,
    payload: GrantDeadlineUpdate,
    ctx: OrganizationContext = ORG_OPERATOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> GrantReportingDeadline:
    dl = await _deadline_for_org(deadline_id, ctx.organization.id, session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(dl, field, value)
    dl.updated_at = utcnow()
    session.add(dl)
    await session.commit()
    await session.refresh(dl)
    return dl


@router.delete("/deadlines/{deadline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deadline(
    deadline_id: UUID,
    ctx: OrganizationContext = ORG_OPERATOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    dl = await _deadline_for_org(deadline_id, ctx.organization.id, session)
    await session.delete(dl)
    await session.commit()


# ---------------------------------------------------------------------------
# Prerequisite linking (operator+) — M2M to RegulatoryTask
# ---------------------------------------------------------------------------


@router.post(
    "/{grant_id}/prerequisites",
    response_model=GrantPrerequisiteRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_prerequisite(
    grant_id: UUID,
    payload: GrantPrerequisiteCreate,
    ctx: OrganizationContext = ORG_OPERATOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> GrantPrerequisiteRead:
    grant = await _grant_for_org(grant_id, ctx.organization.id, session)
    # Same-org guard for the M2M silent-leak surface.
    task = await _regulatory_task_for_org(payload.regulatory_task_id, ctx.organization.id, session)

    # Idempotent: if the link already exists, return it instead of failing.
    existing = await session.get(GrantPrerequisiteTask, (grant.id, task.id))
    if existing is not None:
        return GrantPrerequisiteRead(
            grant_id=existing.grant_id,
            regulatory_task_id=existing.regulatory_task_id,
            label_override=existing.label_override,
            is_critical=existing.is_critical,
            created_at=existing.created_at,
            task_body=task.body,
            task_completed=task.completed,
        )

    link = GrantPrerequisiteTask(
        grant_id=grant.id,
        regulatory_task_id=task.id,
        label_override=payload.label_override,
        is_critical=payload.is_critical,
    )
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return GrantPrerequisiteRead(
        grant_id=link.grant_id,
        regulatory_task_id=link.regulatory_task_id,
        label_override=link.label_override,
        is_critical=link.is_critical,
        created_at=link.created_at,
        task_body=task.body,
        task_completed=task.completed,
    )


@router.delete(
    "/{grant_id}/prerequisites/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_prerequisite(
    grant_id: UUID,
    task_id: UUID,
    ctx: OrganizationContext = ORG_OPERATOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    await _grant_for_org(grant_id, ctx.organization.id, session)
    link = await session.get(GrantPrerequisiteTask, (grant_id, task_id))
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await session.delete(link)
    await session.commit()


@router.get(
    "/{grant_id}/prerequisites/status",
    response_model=GrantPrerequisiteStatus,
)
async def prerequisite_status(
    grant_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> GrantPrerequisiteStatus:
    await _grant_for_org(grant_id, ctx.organization.id, session)
    stmt = select(GrantPrerequisiteTask).where(
        GrantPrerequisiteTask.grant_id == grant_id  # type: ignore[arg-type]
    )
    links = list((await session.execute(stmt)).scalars().all())

    total = len(links)
    complete = 0
    blocking_critical = 0
    for link in links:
        task = await session.get(RegulatoryTask, link.regulatory_task_id)
        if task is None:
            continue
        if task.completed:
            complete += 1
        elif link.is_critical:
            blocking_critical += 1

    percent = (complete / total) if total > 0 else 0.0
    return GrantPrerequisiteStatus(
        total=total,
        complete=complete,
        blocking_critical=blocking_critical,
        percent=round(percent, 4),
    )
