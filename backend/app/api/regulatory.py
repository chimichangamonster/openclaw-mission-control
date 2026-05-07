"""Regulatory tracker CRUD endpoints (item 101 v2 Phase 1b.1).

Mirrors the structure of magnetik-solutions/public/internal/equipment-tracker.html.

Auth tiers per planning doc item 101 v2 section 3:
  - admin+:    streams, countries, tags (taxonomy editing)
  - operator+: phases, tasks, notes, priority notes (day-to-day workflow)
  - member+:   reads (no write)

Isolation contract (locked by tests/test_regulatory_isolation.py):
  Direct-owned tables (Stream, Country, Tag) filter by organization_id.
  Indirect-owned tables (Phase, Task, TaskNote, PriorityNote, TaskTag)
  must trace back to the org via FK chain on every read AND validate
  same-org-membership of all referenced rows on every write. The model
  layer permits cross-org mixing — only this module prevents it.

Phase 1b.2 (next session) adds:
  - POST /regulatory/import-html (HTML parser for one-shot seed)
  - GET  /regulatory/snapshot/public/{token} (unauthenticated read-only)
  - POST /regulatory/snapshot/public/rotate-token
  - GET  /agent/regulatory/active-tasks (agent-token surface)
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
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
from app.models.organization_settings import OrganizationSettings
from app.models.regulatory import (
    RegulatoryCountry,
    RegulatoryPhase,
    RegulatoryPriorityNote,
    RegulatoryStream,
    RegulatoryTag,
    RegulatoryTask,
    RegulatoryTaskNote,
    RegulatoryTaskTag,
)
from app.schemas.regulatory import (
    RegulatoryCountryCreate,
    RegulatoryCountryRead,
    RegulatoryCountryUpdate,
    RegulatoryPhaseCreate,
    RegulatoryPhaseRead,
    RegulatoryPhaseUpdate,
    RegulatoryPriorityNoteCreate,
    RegulatoryPriorityNoteRead,
    RegulatoryPriorityNoteUpdate,
    RegulatoryStreamCreate,
    RegulatoryStreamRead,
    RegulatoryStreamUpdate,
    RegulatoryTagCreate,
    RegulatoryTagRead,
    RegulatoryTagUpdate,
    RegulatoryTaskCreate,
    RegulatoryTaskNoteCreate,
    RegulatoryTaskNoteRead,
    RegulatoryTaskRead,
    RegulatoryTaskTagCreate,
    RegulatoryTaskTagRead,
    RegulatoryTaskUpdate,
)
from app.services.organizations import OrganizationContext

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)

# Closures captured at module load so tests can override them via
# ``app.dependency_overrides[REGULATORY_FEATURE_GATE] = ...``. Each call to
# require_role/require_feature returns a NEW closure, so without these stable
# names tests would override different instances than the router uses.
_REQUIRE_ADMIN = require_org_role("admin")
_REQUIRE_OPERATOR = require_org_role("operator")
REGULATORY_FEATURE_GATE = require_feature("regulatory")

ORG_ADMIN_DEP = Depends(_REQUIRE_ADMIN)
ORG_OPERATOR_DEP = Depends(_REQUIRE_OPERATOR)

router = APIRouter(
    prefix="/regulatory",
    tags=["regulatory"],
    dependencies=[ORG_RATE_LIMIT_DEP, Depends(REGULATORY_FEATURE_GATE)],
)


# ---------------------------------------------------------------------------
# Internal helpers — FK-chain isolation walks
# ---------------------------------------------------------------------------


async def _phase_for_org(phase_id: UUID, org_id: UUID, session: AsyncSession) -> RegulatoryPhase:
    """Load a phase and verify it belongs to the calling org via Stream→org.

    Raises 404 on missing or cross-org access (intentional ambiguity — never
    leak existence).
    """
    phase = await session.get(RegulatoryPhase, phase_id)
    if phase is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    stream = await session.get(RegulatoryStream, phase.stream_id)
    if stream is None or stream.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return phase


async def _task_for_org(task_id: UUID, org_id: UUID, session: AsyncSession) -> RegulatoryTask:
    """Load a task and verify org via Phase→Stream→org chain."""
    task = await session.get(RegulatoryTask, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await _phase_for_org(task.phase_id, org_id, session)  # 404s if cross-org
    return task


# ---------------------------------------------------------------------------
# Streams (admin+)
# ---------------------------------------------------------------------------


@router.get("/streams", response_model=list[RegulatoryStreamRead])
async def list_streams(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
    include_archived: bool = Query(default=False),
) -> list[RegulatoryStream]:
    stmt = (
        select(RegulatoryStream)
        .where(RegulatoryStream.organization_id == ctx.organization.id)  # type: ignore[arg-type]
        .order_by(RegulatoryStream.sort_order, RegulatoryStream.name)
    )
    if not include_archived:
        stmt = stmt.where(RegulatoryStream.archived.is_(False))  # type: ignore[union-attr]
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "/streams",
    response_model=RegulatoryStreamRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[ORG_ADMIN_DEP],
)
async def create_stream(
    payload: RegulatoryStreamCreate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> RegulatoryStream:
    existing = (
        await session.execute(
            select(RegulatoryStream).where(
                RegulatoryStream.organization_id == ctx.organization.id,  # type: ignore[arg-type]
                RegulatoryStream.slug == payload.slug,  # type: ignore[arg-type]
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stream with slug '{payload.slug}' already exists.",
        )

    now = utcnow()
    stream = RegulatoryStream(
        id=uuid4(),
        organization_id=ctx.organization.id,
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
        color_token=payload.color_token,
        budget_estimate=payload.budget_estimate,
        regulator_label=payload.regulator_label,
        timeline_label=payload.timeline_label,
        sort_order=payload.sort_order,
        archived=False,
        created_at=now,
        updated_at=now,
    )
    session.add(stream)
    await session.commit()
    await session.refresh(stream)
    return stream


@router.patch(
    "/streams/{stream_id}",
    response_model=RegulatoryStreamRead,
    dependencies=[ORG_ADMIN_DEP],
)
async def update_stream(
    stream_id: UUID,
    payload: RegulatoryStreamUpdate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> RegulatoryStream:
    stream = await session.get(RegulatoryStream, stream_id)
    if stream is None or stream.organization_id != ctx.organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    for field in (
        "name",
        "description",
        "color_token",
        "budget_estimate",
        "regulator_label",
        "timeline_label",
        "sort_order",
        "archived",
    ):
        value = getattr(payload, field, None)
        if value is not None:
            setattr(stream, field, value)
    stream.updated_at = utcnow()
    session.add(stream)
    await session.commit()
    await session.refresh(stream)
    return stream


@router.delete(
    "/streams/{stream_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[ORG_ADMIN_DEP],
)
async def delete_stream(
    stream_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    stream = await session.get(RegulatoryStream, stream_id)
    if stream is None or stream.organization_id != ctx.organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await session.delete(stream)
    await session.commit()


# ---------------------------------------------------------------------------
# Countries (admin+)
# ---------------------------------------------------------------------------


@router.get("/countries", response_model=list[RegulatoryCountryRead])
async def list_countries(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[RegulatoryCountry]:
    result = await session.execute(
        select(RegulatoryCountry)
        .where(RegulatoryCountry.organization_id == ctx.organization.id)  # type: ignore[arg-type]
        .order_by(RegulatoryCountry.sort_order, RegulatoryCountry.name)
    )
    return list(result.scalars().all())


@router.post(
    "/countries",
    response_model=RegulatoryCountryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[ORG_ADMIN_DEP],
)
async def create_country(
    payload: RegulatoryCountryCreate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> RegulatoryCountry:
    existing = (
        await session.execute(
            select(RegulatoryCountry).where(
                RegulatoryCountry.organization_id == ctx.organization.id,  # type: ignore[arg-type]
                RegulatoryCountry.code == payload.code.upper(),  # type: ignore[arg-type]
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Country with code '{payload.code}' already exists.",
        )
    now = utcnow()
    country = RegulatoryCountry(
        id=uuid4(),
        organization_id=ctx.organization.id,
        code=payload.code.upper(),
        name=payload.name,
        status=payload.status,
        display_label=payload.display_label,
        sort_order=payload.sort_order,
        created_at=now,
        updated_at=now,
    )
    session.add(country)
    await session.commit()
    await session.refresh(country)
    return country


@router.patch(
    "/countries/{country_id}",
    response_model=RegulatoryCountryRead,
    dependencies=[ORG_ADMIN_DEP],
)
async def update_country(
    country_id: UUID,
    payload: RegulatoryCountryUpdate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> RegulatoryCountry:
    country = await session.get(RegulatoryCountry, country_id)
    if country is None or country.organization_id != ctx.organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    for field in ("name", "status", "display_label", "sort_order"):
        value = getattr(payload, field, None)
        if value is not None:
            setattr(country, field, value)
    country.updated_at = utcnow()
    session.add(country)
    await session.commit()
    await session.refresh(country)
    return country


# ---------------------------------------------------------------------------
# Tags (admin+)
# ---------------------------------------------------------------------------


@router.get("/tags", response_model=list[RegulatoryTagRead])
async def list_tags(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
    kind: str = Query(default=""),
) -> list[RegulatoryTag]:
    stmt = (
        select(RegulatoryTag)
        .where(RegulatoryTag.organization_id == ctx.organization.id)  # type: ignore[arg-type]
        .order_by(RegulatoryTag.kind, RegulatoryTag.label)
    )
    if kind:
        stmt = stmt.where(RegulatoryTag.kind == kind)  # type: ignore[arg-type]
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "/tags",
    response_model=RegulatoryTagRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[ORG_ADMIN_DEP],
)
async def create_tag(
    payload: RegulatoryTagCreate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> RegulatoryTag:
    existing = (
        await session.execute(
            select(RegulatoryTag).where(
                RegulatoryTag.organization_id == ctx.organization.id,  # type: ignore[arg-type]
                RegulatoryTag.slug == payload.slug,  # type: ignore[arg-type]
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tag with slug '{payload.slug}' already exists.",
        )
    tag = RegulatoryTag(
        id=uuid4(),
        organization_id=ctx.organization.id,
        slug=payload.slug,
        label=payload.label,
        color_token=payload.color_token,
        kind=payload.kind,
        created_at=utcnow(),
    )
    session.add(tag)
    await session.commit()
    await session.refresh(tag)
    return tag


@router.patch(
    "/tags/{tag_id}",
    response_model=RegulatoryTagRead,
    dependencies=[ORG_ADMIN_DEP],
)
async def update_tag(
    tag_id: UUID,
    payload: RegulatoryTagUpdate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> RegulatoryTag:
    tag = await session.get(RegulatoryTag, tag_id)
    if tag is None or tag.organization_id != ctx.organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    for field in ("label", "color_token", "kind"):
        value = getattr(payload, field, None)
        if value is not None:
            setattr(tag, field, value)
    session.add(tag)
    await session.commit()
    await session.refresh(tag)
    return tag


@router.delete(
    "/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[ORG_ADMIN_DEP],
)
async def delete_tag(
    tag_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    tag = await session.get(RegulatoryTag, tag_id)
    if tag is None or tag.organization_id != ctx.organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await session.delete(tag)
    await session.commit()


# ---------------------------------------------------------------------------
# Phases (operator+) — first cross-table boundary; same-org check on FKs
# ---------------------------------------------------------------------------


@router.get("/phases", response_model=list[RegulatoryPhaseRead])
async def list_phases(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
    stream_id: UUID | None = Query(default=None),
    country_id: UUID | None = Query(default=None),
) -> list[RegulatoryPhase]:
    # Inner-join on Stream restricts to phases whose stream is in this org.
    # Country FK is not joined for filtering — we already trust stream_id;
    # cross-org country FKs are blocked at create time.
    stmt = (
        select(RegulatoryPhase)
        .join(RegulatoryStream, RegulatoryStream.id == RegulatoryPhase.stream_id)
        .where(RegulatoryStream.organization_id == ctx.organization.id)  # type: ignore[arg-type]
        .order_by(RegulatoryPhase.sort_order, RegulatoryPhase.name)
    )
    if stream_id is not None:
        stmt = stmt.where(RegulatoryPhase.stream_id == stream_id)  # type: ignore[arg-type]
    if country_id is not None:
        stmt = stmt.where(RegulatoryPhase.country_id == country_id)  # type: ignore[arg-type]
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "/phases",
    response_model=RegulatoryPhaseRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[ORG_OPERATOR_DEP],
)
async def create_phase(
    payload: RegulatoryPhaseCreate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> RegulatoryPhase:
    # SAME-ORG CHECK: verify stream and country both belong to caller's org.
    # The model layer permits cross-org mixing; this is the only line of defense.
    stream = await session.get(RegulatoryStream, payload.stream_id)
    if stream is None or stream.organization_id != ctx.organization.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stream not found.",
        )
    country = await session.get(RegulatoryCountry, payload.country_id)
    if country is None or country.organization_id != ctx.organization.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Country not found.",
        )

    now = utcnow()
    phase = RegulatoryPhase(
        id=uuid4(),
        stream_id=payload.stream_id,
        country_id=payload.country_id,
        name=payload.name,
        badge_kind=payload.badge_kind,
        timing_label=payload.timing_label,
        sort_order=payload.sort_order,
        default_open=payload.default_open,
        created_at=now,
        updated_at=now,
    )
    session.add(phase)
    await session.commit()
    await session.refresh(phase)
    return phase


@router.patch(
    "/phases/{phase_id}",
    response_model=RegulatoryPhaseRead,
    dependencies=[ORG_OPERATOR_DEP],
)
async def update_phase(
    phase_id: UUID,
    payload: RegulatoryPhaseUpdate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> RegulatoryPhase:
    phase = await _phase_for_org(phase_id, ctx.organization.id, session)
    for field in ("name", "badge_kind", "timing_label", "sort_order", "default_open"):
        value = getattr(payload, field, None)
        if value is not None:
            setattr(phase, field, value)
    phase.updated_at = utcnow()
    session.add(phase)
    await session.commit()
    await session.refresh(phase)
    return phase


@router.delete(
    "/phases/{phase_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[ORG_OPERATOR_DEP],
)
async def delete_phase(
    phase_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    phase = await _phase_for_org(phase_id, ctx.organization.id, session)
    await session.delete(phase)
    await session.commit()


# ---------------------------------------------------------------------------
# Tasks (operator+)
# ---------------------------------------------------------------------------


@router.get("/tasks", response_model=list[RegulatoryTaskRead])
async def list_tasks(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
    phase_id: UUID | None = Query(default=None),
    completed: bool | None = Query(default=None),
) -> list[RegulatoryTask]:
    # Two-hop join: Task → Phase → Stream → org.
    stmt = (
        select(RegulatoryTask)
        .join(RegulatoryPhase, RegulatoryPhase.id == RegulatoryTask.phase_id)
        .join(RegulatoryStream, RegulatoryStream.id == RegulatoryPhase.stream_id)
        .where(RegulatoryStream.organization_id == ctx.organization.id)  # type: ignore[arg-type]
        .order_by(RegulatoryTask.sort_order, RegulatoryTask.created_at)
    )
    if phase_id is not None:
        stmt = stmt.where(RegulatoryTask.phase_id == phase_id)  # type: ignore[arg-type]
    if completed is not None:
        stmt = stmt.where(RegulatoryTask.completed.is_(completed))  # type: ignore[union-attr]
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post(
    "/tasks",
    response_model=RegulatoryTaskRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[ORG_OPERATOR_DEP],
)
async def create_task(
    payload: RegulatoryTaskCreate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> RegulatoryTask:
    # SAME-ORG CHECK on phase via FK chain.
    await _phase_for_org(payload.phase_id, ctx.organization.id, session)
    now = utcnow()
    task = RegulatoryTask(
        id=uuid4(),
        phase_id=payload.phase_id,
        body=payload.body,
        note=payload.note,
        completed=False,
        assignee_user_id=payload.assignee_user_id,
        due_date=payload.due_date,
        sort_order=payload.sort_order,
        created_at=now,
        updated_at=now,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


@router.patch(
    "/tasks/{task_id}",
    response_model=RegulatoryTaskRead,
    dependencies=[ORG_OPERATOR_DEP],
)
async def update_task(
    task_id: UUID,
    payload: RegulatoryTaskUpdate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> RegulatoryTask:
    task = await _task_for_org(task_id, ctx.organization.id, session)
    for field in ("body", "note", "assignee_user_id", "due_date", "sort_order"):
        value = getattr(payload, field, None)
        if value is not None:
            setattr(task, field, value)
    task.updated_at = utcnow()
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


@router.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[ORG_OPERATOR_DEP],
)
async def delete_task(
    task_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    task = await _task_for_org(task_id, ctx.organization.id, session)
    await session.delete(task)
    await session.commit()


@router.post(
    "/tasks/{task_id}/toggle",
    response_model=RegulatoryTaskRead,
    dependencies=[ORG_OPERATOR_DEP],
)
async def toggle_task(
    task_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> RegulatoryTask:
    task = await _task_for_org(task_id, ctx.organization.id, session)
    task.completed = not task.completed
    if task.completed:
        task.completed_at = utcnow()
        task.completed_by_user_id = ctx.member.user_id
    else:
        task.completed_at = None
        task.completed_by_user_id = None
    task.updated_at = utcnow()
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


# ---------------------------------------------------------------------------
# Task notes (operator+) — threaded notes attached to a task
# ---------------------------------------------------------------------------


@router.get("/tasks/{task_id}/notes", response_model=list[RegulatoryTaskNoteRead])
async def list_task_notes(
    task_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[RegulatoryTaskNote]:
    await _task_for_org(task_id, ctx.organization.id, session)
    result = await session.execute(
        select(RegulatoryTaskNote)
        .where(RegulatoryTaskNote.task_id == task_id)  # type: ignore[arg-type]
        .order_by(RegulatoryTaskNote.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "/tasks/{task_id}/notes",
    response_model=RegulatoryTaskNoteRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[ORG_OPERATOR_DEP],
)
async def create_task_note(
    task_id: UUID,
    payload: RegulatoryTaskNoteCreate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> RegulatoryTaskNote:
    await _task_for_org(task_id, ctx.organization.id, session)
    note = RegulatoryTaskNote(
        id=uuid4(),
        task_id=task_id,
        body=payload.body,
        author_user_id=ctx.member.user_id,
        created_at=utcnow(),
    )
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


@router.delete(
    "/tasks/{task_id}/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[ORG_OPERATOR_DEP],
)
async def delete_task_note(
    task_id: UUID,
    note_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    await _task_for_org(task_id, ctx.organization.id, session)
    note = await session.get(RegulatoryTaskNote, note_id)
    if note is None or note.task_id != task_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await session.delete(note)
    await session.commit()


# ---------------------------------------------------------------------------
# Priority notes (operator+) — banner notes on a phase
# ---------------------------------------------------------------------------


@router.get("/phases/{phase_id}/priority-notes", response_model=list[RegulatoryPriorityNoteRead])
async def list_priority_notes(
    phase_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[RegulatoryPriorityNote]:
    await _phase_for_org(phase_id, ctx.organization.id, session)
    result = await session.execute(
        select(RegulatoryPriorityNote)
        .where(RegulatoryPriorityNote.phase_id == phase_id)  # type: ignore[arg-type]
        .order_by(RegulatoryPriorityNote.sort_order, RegulatoryPriorityNote.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "/priority-notes",
    response_model=RegulatoryPriorityNoteRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[ORG_OPERATOR_DEP],
)
async def create_priority_note(
    payload: RegulatoryPriorityNoteCreate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> RegulatoryPriorityNote:
    await _phase_for_org(payload.phase_id, ctx.organization.id, session)
    note = RegulatoryPriorityNote(
        id=uuid4(),
        phase_id=payload.phase_id,
        body=payload.body,
        severity=payload.severity,
        sort_order=payload.sort_order,
        created_at=utcnow(),
    )
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


@router.patch(
    "/priority-notes/{note_id}",
    response_model=RegulatoryPriorityNoteRead,
    dependencies=[ORG_OPERATOR_DEP],
)
async def update_priority_note(
    note_id: UUID,
    payload: RegulatoryPriorityNoteUpdate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> RegulatoryPriorityNote:
    note = await session.get(RegulatoryPriorityNote, note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await _phase_for_org(note.phase_id, ctx.organization.id, session)
    for field in ("body", "severity", "sort_order"):
        value = getattr(payload, field, None)
        if value is not None:
            setattr(note, field, value)
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


@router.delete(
    "/priority-notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[ORG_OPERATOR_DEP],
)
async def delete_priority_note(
    note_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    note = await session.get(RegulatoryPriorityNote, note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await _phase_for_org(note.phase_id, ctx.organization.id, session)
    await session.delete(note)
    await session.commit()


# ---------------------------------------------------------------------------
# Task tags (operator+) — M2M, the silent-leak surface
# ---------------------------------------------------------------------------


@router.get("/tasks/{task_id}/tags", response_model=list[RegulatoryTagRead])
async def list_task_tags(
    task_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[RegulatoryTag]:
    await _task_for_org(task_id, ctx.organization.id, session)
    result = await session.execute(
        select(RegulatoryTag)
        .join(RegulatoryTaskTag, RegulatoryTaskTag.tag_id == RegulatoryTag.id)
        .where(
            RegulatoryTaskTag.task_id == task_id,  # type: ignore[arg-type]
            # Defense-in-depth: even if a cross-org link slipped past create,
            # filter by org on the tag side. Belt + suspenders.
            RegulatoryTag.organization_id == ctx.organization.id,  # type: ignore[arg-type]
        )
        .order_by(RegulatoryTag.kind, RegulatoryTag.label)
    )
    return list(result.scalars().all())


@router.post(
    "/task-tags",
    response_model=RegulatoryTaskTagRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[ORG_OPERATOR_DEP],
)
async def create_task_tag(
    payload: RegulatoryTaskTagCreate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> RegulatoryTaskTag:
    """Link a tag to a task. THE silent-leak surface.

    Both task and tag must belong to the caller's org. The model layer
    permits any (task_id, tag_id) pair; this check is the only thing
    preventing org A's tag from being attached to org B's task.
    """
    # Verify task belongs to org via FK chain.
    await _task_for_org(payload.task_id, ctx.organization.id, session)
    # Verify tag belongs to org directly.
    tag = await session.get(RegulatoryTag, payload.tag_id)
    if tag is None or tag.organization_id != ctx.organization.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found.",
        )
    # Idempotent: return existing link if already present.
    existing = await session.get(RegulatoryTaskTag, (payload.task_id, payload.tag_id))
    if existing is not None:
        return existing

    link = RegulatoryTaskTag(
        task_id=payload.task_id,
        tag_id=payload.tag_id,
        created_at=utcnow(),
    )
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return link


@router.delete(
    "/task-tags/{task_id}/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[ORG_OPERATOR_DEP],
)
async def delete_task_tag(
    task_id: UUID,
    tag_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    # Same-org check on task is sufficient — if you can reach the task,
    # you can unlink any tag from it.
    await _task_for_org(task_id, ctx.organization.id, session)
    link = await session.get(RegulatoryTaskTag, (task_id, tag_id))
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await session.delete(link)
    await session.commit()


# ---------------------------------------------------------------------------
# Phase 1b.2 — HTML import (admin+) + public snapshot token rotation (admin+)
# ---------------------------------------------------------------------------


_IMPORT_HTML_MAX_BYTES = 5 * 1024 * 1024  # 5 MB — equipment-tracker.html is ~80KB


@router.post(
    "/import-html",
    status_code=status.HTTP_201_CREATED,
    dependencies=[ORG_ADMIN_DEP],
)
async def import_tracker_html(
    file: UploadFile = File(...),  # noqa: B008
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, int]:
    """One-shot seed of the regulatory tracker from equipment-tracker.html.

    Idempotent on ``(organization_id, country_code, stream_slug, phase_name,
    task_body_hash)`` — re-running on the same HTML never duplicates rows.

    Streams + countries + tags are upserted on first sight; phases are
    upserted by ``(stream, country, name)``; tasks are deduplicated by
    body_hash within their phase. Priority notes dedupe on
    ``(phase, normalized body)`` to prevent re-import duplicates.

    Returns a counts summary so the operator can verify what changed.
    """
    from app.services.regulatory_html_parser import (
        kind_for_tag_slug,
        parse_tracker_html,
    )

    raw = await file.read()
    if len(raw) > _IMPORT_HTML_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"HTML file exceeds {_IMPORT_HTML_MAX_BYTES} bytes.",
        )
    try:
        html = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="HTML file must be UTF-8 encoded.",
        ) from exc

    tracker = parse_tracker_html(html)
    if not tracker.countries:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No published-country panels found in HTML.",
        )

    org_id = ctx.organization.id
    now = utcnow()

    summary = {
        "countries_created": 0,
        "streams_created": 0,
        "streams_skipped_existing": 0,
        "phases_created": 0,
        "phases_skipped_existing": 0,
        "tasks_created": 0,
        "tasks_skipped_duplicate": 0,
        "tags_created": 0,
        "priority_notes_created": 0,
    }

    # Tag cache keyed by slug — populated lazily as we encounter tags.
    tag_cache: dict[str, RegulatoryTag] = {}

    async def _get_or_create_tag(slug: str, label: str) -> RegulatoryTag:
        if slug in tag_cache:
            return tag_cache[slug]
        existing = (
            await session.execute(
                select(RegulatoryTag).where(
                    RegulatoryTag.organization_id == org_id,
                    RegulatoryTag.slug == slug,
                )
            )
        ).scalar_one_or_none()
        if existing:
            tag_cache[slug] = existing
            return existing
        tag = RegulatoryTag(
            id=uuid4(),
            organization_id=org_id,
            slug=slug,
            label=label,
            color_token=slug,
            kind=kind_for_tag_slug(slug),
            created_at=now,
        )
        session.add(tag)
        await session.flush()
        tag_cache[slug] = tag
        summary["tags_created"] += 1
        return tag

    for parsed_country in tracker.countries:
        country = (
            await session.execute(
                select(RegulatoryCountry).where(
                    RegulatoryCountry.organization_id == org_id,
                    RegulatoryCountry.code == parsed_country.code,
                )
            )
        ).scalar_one_or_none()
        if country is None:
            country = RegulatoryCountry(
                id=uuid4(),
                organization_id=org_id,
                code=parsed_country.code,
                name=parsed_country.display_label.split(" (")[0],
                status="active",
                display_label=parsed_country.display_label,
                created_at=now,
                updated_at=now,
            )
            session.add(country)
            await session.flush()
            summary["countries_created"] += 1

        for parsed_stream in parsed_country.streams:
            stream = (
                await session.execute(
                    select(RegulatoryStream).where(
                        RegulatoryStream.organization_id == org_id,
                        RegulatoryStream.slug == parsed_stream.slug,
                    )
                )
            ).scalar_one_or_none()
            if stream is None:
                stream = RegulatoryStream(
                    id=uuid4(),
                    organization_id=org_id,
                    slug=parsed_stream.slug,
                    name=parsed_stream.name,
                    description=parsed_stream.subtitle,
                    color_token=parsed_stream.color_token,
                    timeline_label=parsed_stream.budget_blob,
                    sort_order=0,
                    archived=False,
                    created_at=now,
                    updated_at=now,
                )
                session.add(stream)
                await session.flush()
                summary["streams_created"] += 1
            else:
                summary["streams_skipped_existing"] += 1

            for parsed_phase in parsed_stream.phases:
                phase = (
                    await session.execute(
                        select(RegulatoryPhase).where(
                            RegulatoryPhase.stream_id == stream.id,
                            RegulatoryPhase.country_id == country.id,
                            RegulatoryPhase.name == parsed_phase.name,
                        )
                    )
                ).scalar_one_or_none()
                if phase is None:
                    phase = RegulatoryPhase(
                        id=uuid4(),
                        stream_id=stream.id,
                        country_id=country.id,
                        name=parsed_phase.name,
                        badge_kind=parsed_phase.badge_kind,
                        timing_label=parsed_phase.timing_label,
                        sort_order=0,
                        default_open=parsed_phase.default_open,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(phase)
                    await session.flush()
                    summary["phases_created"] += 1
                else:
                    summary["phases_skipped_existing"] += 1

                # Priority notes — dedupe on (phase, body).
                existing_notes = (
                    (
                        await session.execute(
                            select(RegulatoryPriorityNote).where(
                                RegulatoryPriorityNote.phase_id == phase.id,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                existing_note_bodies = {n.body for n in existing_notes}
                for parsed_note in parsed_phase.priority_notes:
                    if parsed_note.body in existing_note_bodies:
                        continue
                    note = RegulatoryPriorityNote(
                        id=uuid4(),
                        phase_id=phase.id,
                        body=parsed_note.body,
                        severity=parsed_note.severity,
                        sort_order=0,
                        created_at=now,
                    )
                    session.add(note)
                    summary["priority_notes_created"] += 1

                # Tasks — dedupe on body_hash within phase.
                existing_tasks = (
                    (
                        await session.execute(
                            select(RegulatoryTask).where(
                                RegulatoryTask.phase_id == phase.id,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                existing_task_hashes = {_hash_for_dedup(t.body) for t in existing_tasks}
                for parsed_task in parsed_phase.tasks:
                    if parsed_task.body_hash in existing_task_hashes:
                        summary["tasks_skipped_duplicate"] += 1
                        continue
                    task = RegulatoryTask(
                        id=uuid4(),
                        phase_id=phase.id,
                        body=parsed_task.text,
                        note=parsed_task.note,
                        completed=False,
                        sort_order=0,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(task)
                    await session.flush()
                    summary["tasks_created"] += 1
                    existing_task_hashes.add(parsed_task.body_hash)

                    # Tags + task_tag links
                    for parsed_tag in parsed_task.tags:
                        tag = await _get_or_create_tag(parsed_tag.slug, parsed_tag.label)
                        # Link is unique on (task_id, tag_id) by composite PK,
                        # so no extra dedup query needed for new tasks.
                        link = RegulatoryTaskTag(task_id=task.id, tag_id=tag.id, created_at=now)
                        session.add(link)

    await session.commit()
    return summary


def _hash_for_dedup(stored_body: str) -> str:
    """Compute the body_hash for an already-stored task body so we can
    compare against parsed task hashes. Mirrors the parser's normalization."""
    from app.services.regulatory_html_parser import _hash_task_text

    return _hash_task_text(stored_body)


@router.post(
    "/snapshot/public/rotate-token",
    dependencies=[ORG_ADMIN_DEP],
)
async def rotate_public_snapshot_token(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, str]:
    """Generate a new public snapshot token, invalidating any previous one.

    The token is the only credential — anyone with it can read this org's
    published Canada snapshot via GET /regulatory/snapshot/public/{token}.
    Rotation is the cleanup mechanism if a token leaks.
    """
    settings = (
        await session.execute(
            select(OrganizationSettings).where(
                OrganizationSettings.organization_id == ctx.organization.id,
            )
        )
    ).scalar_one_or_none()
    if settings is None:
        settings = OrganizationSettings(
            id=uuid4(),
            organization_id=ctx.organization.id,
        )
        session.add(settings)

    new_token = secrets.token_urlsafe(32)
    settings.regulatory_public_snapshot_token = new_token
    settings.updated_at = utcnow()
    session.add(settings)
    await session.commit()
    return {"token": new_token}


# ---------------------------------------------------------------------------
# Item 115 — authored snapshot aggregator (admin /regulatory page)
# ---------------------------------------------------------------------------
#
# The `/regulatory` admin page needs the entire authored tree (streams →
# phases → tasks → tags + priority notes) to render edit affordances.
# Pre-item-115, the frontend walked the CRUD endpoints client-side: ~112
# round-trips on Magnetik (3 streams / 17 phases / 90 tasks), 10+ second
# load times.
#
# This endpoint returns the full tree in a single response with batched
# IN-queries internally (4 queries total: streams, phases, tasks-with-notes,
# task-tag links). Shape is a superset of regulatory_public.py — adds IDs
# at every level so PATCH/DELETE/toggle from the page can target rows
# directly, plus per-task `note`, `assignee_user_id`, `due_date` for
# detail-panel edits.
# ---------------------------------------------------------------------------


def _percent(done: int, total: int) -> int:
    if total == 0:
        return 0
    return round(done * 100 / total)


@router.get("/snapshot/authored/{country_code}")
async def get_authored_snapshot(
    country_code: str,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, object]:
    """Return the full authored snapshot for the caller's org + country.

    Single-round-trip aggregator backing the admin /regulatory page.
    Returns 404 if the org has no country with that code seeded.
    """
    org_id = ctx.organization.id

    country = (
        await session.execute(
            select(RegulatoryCountry).where(
                RegulatoryCountry.organization_id == org_id,
                RegulatoryCountry.code == country_code,
            )
        )
    ).scalar_one_or_none()
    if country is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    streams = list(
        (
            await session.execute(
                select(RegulatoryStream)
                .where(
                    RegulatoryStream.organization_id == org_id,
                    RegulatoryStream.archived.is_(False),  # type: ignore[union-attr]
                )
                .order_by(RegulatoryStream.sort_order, RegulatoryStream.name)
            )
        )
        .scalars()
        .all()
    )
    if not streams:
        return {
            "country": {
                "id": str(country.id),
                "code": country.code,
                "display_label": country.display_label,
            },
            "totals": {"tasks": 0, "completed": 0, "percent": 0},
            "streams": [],
        }

    stream_ids = [s.id for s in streams]
    phases = list(
        (
            await session.execute(
                select(RegulatoryPhase)
                .where(
                    RegulatoryPhase.stream_id.in_(stream_ids),  # type: ignore[attr-defined]
                    RegulatoryPhase.country_id == country.id,
                )
                .order_by(RegulatoryPhase.sort_order, RegulatoryPhase.name)
            )
        )
        .scalars()
        .all()
    )

    phase_ids = [p.id for p in phases]
    tasks: list[RegulatoryTask] = []
    priority_notes: list[RegulatoryPriorityNote] = []
    if phase_ids:
        tasks = list(
            (
                await session.execute(
                    select(RegulatoryTask)
                    .where(RegulatoryTask.phase_id.in_(phase_ids))  # type: ignore[attr-defined]
                    .order_by(RegulatoryTask.sort_order, RegulatoryTask.created_at)
                )
            )
            .scalars()
            .all()
        )
        priority_notes = list(
            (
                await session.execute(
                    select(RegulatoryPriorityNote)
                    .where(RegulatoryPriorityNote.phase_id.in_(phase_ids))  # type: ignore[attr-defined]
                    .order_by(
                        RegulatoryPriorityNote.sort_order,
                        RegulatoryPriorityNote.created_at,
                    )
                )
            )
            .scalars()
            .all()
        )

    # One join query for the whole task-tag link table for these tasks.
    task_ids = [t.id for t in tasks]
    tags_by_task: dict[UUID, list[RegulatoryTag]] = {}
    if task_ids:
        rows = (
            await session.execute(
                select(RegulatoryTaskTag.task_id, RegulatoryTag)
                .join(RegulatoryTag, RegulatoryTag.id == RegulatoryTaskTag.tag_id)
                .where(
                    RegulatoryTaskTag.task_id.in_(task_ids),  # type: ignore[attr-defined]
                    # Defense-in-depth: only this org's tags.
                    RegulatoryTag.organization_id == org_id,
                )
            )
        ).all()
        for task_id, tag in rows:
            tags_by_task.setdefault(task_id, []).append(tag)

    # Build O(1) lookups for the assembly pass.
    tasks_by_phase: dict[UUID, list[RegulatoryTask]] = {}
    for t in tasks:
        tasks_by_phase.setdefault(t.phase_id, []).append(t)

    notes_by_phase: dict[UUID, list[RegulatoryPriorityNote]] = {}
    for n in priority_notes:
        notes_by_phase.setdefault(n.phase_id, []).append(n)

    phases_by_stream: dict[UUID, list[RegulatoryPhase]] = {}
    for p in phases:
        phases_by_stream.setdefault(p.stream_id, []).append(p)

    payload_streams: list[dict[str, object]] = []
    grand_total = 0
    grand_done = 0

    for stream in streams:
        stream_phases = phases_by_stream.get(stream.id, [])
        payload_phases: list[dict[str, object]] = []
        stream_total = 0
        stream_done = 0

        for phase in stream_phases:
            phase_tasks = tasks_by_phase.get(phase.id, [])
            phase_notes = notes_by_phase.get(phase.id, [])

            payload_tasks: list[dict[str, object]] = []
            for task in phase_tasks:
                tag_rows = tags_by_task.get(task.id, [])
                payload_tasks.append(
                    {
                        "id": str(task.id),
                        "body": task.body,
                        "note": task.note,
                        "completed": task.completed,
                        "assignee_user_id": (
                            str(task.assignee_user_id) if task.assignee_user_id else None
                        ),
                        "due_date": (task.due_date.isoformat() if task.due_date else None),
                        "tags": [
                            {
                                "id": str(t.id),
                                "slug": t.slug,
                                "label": t.label,
                                "color_token": t.color_token,
                            }
                            for t in tag_rows
                        ],
                    }
                )

            stream_total += len(phase_tasks)
            stream_done += sum(1 for t in phase_tasks if t.completed)

            payload_phases.append(
                {
                    "id": str(phase.id),
                    "name": phase.name,
                    "badge_kind": phase.badge_kind,
                    "timing_label": phase.timing_label,
                    "default_open": phase.default_open,
                    "priority_notes": [
                        {
                            "id": str(n.id),
                            "body": n.body,
                            "severity": n.severity,
                        }
                        for n in phase_notes
                    ],
                    "tasks": payload_tasks,
                }
            )

        grand_total += stream_total
        grand_done += stream_done
        payload_streams.append(
            {
                "id": str(stream.id),
                "slug": stream.slug,
                "name": stream.name,
                "color_token": stream.color_token,
                "description": stream.description,
                "timeline_label": stream.timeline_label,
                "totals": {
                    "tasks": stream_total,
                    "completed": stream_done,
                    "percent": _percent(stream_done, stream_total),
                },
                "phases": payload_phases,
            }
        )

    return {
        "country": {
            "id": str(country.id),
            "code": country.code,
            "display_label": country.display_label,
        },
        "totals": {
            "tasks": grand_total,
            "completed": grand_done,
            "percent": _percent(grand_done, grand_total),
        },
        "streams": payload_streams,
    }
