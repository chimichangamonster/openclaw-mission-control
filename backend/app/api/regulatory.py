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

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
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


async def _phase_for_org(
    phase_id: UUID, org_id: UUID, session: AsyncSession
) -> RegulatoryPhase:
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


async def _task_for_org(
    task_id: UUID, org_id: UUID, session: AsyncSession
) -> RegulatoryTask:
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
    existing = await session.get(
        RegulatoryTaskTag, (payload.task_id, payload.tag_id)
    )
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
