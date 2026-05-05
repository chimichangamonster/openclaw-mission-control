"""Unauthenticated public snapshot endpoint for the regulatory tracker.

Item 101 v2 Phase 1b.2. Lives in its own module so the auth surface is
unambiguous: this router has NO ``Depends(...)`` for membership, role,
agent token, or feature gate. The token IS the only credential. Wrong
token → 404 (never leak existence of the org or token shape).

The marketing site (``magnetik-solutions/public/internal/tracker``) will
SSR-fetch this endpoint in Phase 3 to render Canada's published progress
to the public web.

Scope (operator-confirmed): only Canada is published in v2. The endpoint
returns the org's Canada country, its streams, phases, tasks, and
priority notes — sanitized to exclude per-task notes, assignee, due date,
and threaded task notes. Tags are returned for color-coding.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.db.session import get_session
from app.models.organization_settings import OrganizationSettings
from app.models.regulatory import (
    RegulatoryCountry,
    RegulatoryPhase,
    RegulatoryPriorityNote,
    RegulatoryStream,
    RegulatoryTag,
    RegulatoryTask,
    RegulatoryTaskTag,
)

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

router = APIRouter(prefix="/regulatory/snapshot/public", tags=["regulatory-public"])

SESSION_DEP = Depends(get_session)


@router.get("/{token}")
async def get_public_snapshot(
    token: str,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """Return the published Canada snapshot for the org owning ``token``.

    Returns 404 for any unknown token. Returned shape is stable for the
    marketing site to SSR-fetch:

    .. code-block:: json

        {
          "country": {"code": "CA", "display_label": "Canada (Alberta Pilot)"},
          "totals": {"tasks": 90, "completed": 12, "percent": 13},
          "streams": [
            {
              "slug": "navy",
              "name": "Corporate Foundation",
              "color_token": "navy",
              "totals": {"tasks": 20, "completed": 5, "percent": 25},
              "phases": [
                {
                  "name": "...",
                  "badge_kind": "corp",
                  "timing_label": "Days 1-10",
                  "default_open": true,
                  "priority_notes": [{"body": "...", "severity": "critical"}],
                  "tasks": [
                    {"body": "...", "completed": false, "tags": [{"slug": "abca", "label": "ABCA"}]}
                  ]
                }
              ]
            }
          ]
        }
    """
    if not token or len(token) < 16:
        # Reject obviously-invalid tokens without a DB hit.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    settings = (
        await session.execute(
            select(OrganizationSettings).where(
                OrganizationSettings.regulatory_public_snapshot_token == token,
            )
        )
    ).scalar_one_or_none()
    if settings is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    org_id = settings.organization_id

    # Hardcoded Canada for v2 — operator confirmed.
    country = (
        await session.execute(
            select(RegulatoryCountry).where(
                RegulatoryCountry.organization_id == org_id,
                RegulatoryCountry.code == "CA",
            )
        )
    ).scalar_one_or_none()
    if country is None:
        # Token exists but no Canada country published yet.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    streams_q = (
        await session.execute(
            select(RegulatoryStream)
            .where(
                RegulatoryStream.organization_id == org_id,
                RegulatoryStream.archived.is_(False),  # type: ignore[union-attr]
            )
            .order_by(RegulatoryStream.sort_order, RegulatoryStream.name)
        )
    ).scalars().all()

    payload_streams: list[dict[str, Any]] = []
    grand_total = 0
    grand_done = 0

    for stream in streams_q:
        phases_q = (
            await session.execute(
                select(RegulatoryPhase)
                .where(
                    RegulatoryPhase.stream_id == stream.id,
                    RegulatoryPhase.country_id == country.id,
                )
                .order_by(RegulatoryPhase.sort_order, RegulatoryPhase.name)
            )
        ).scalars().all()

        payload_phases: list[dict[str, Any]] = []
        stream_total = 0
        stream_done = 0

        for phase in phases_q:
            notes_q = (
                await session.execute(
                    select(RegulatoryPriorityNote)
                    .where(RegulatoryPriorityNote.phase_id == phase.id)
                    .order_by(
                        RegulatoryPriorityNote.sort_order,
                        RegulatoryPriorityNote.created_at,
                    )
                )
            ).scalars().all()
            tasks_q = (
                await session.execute(
                    select(RegulatoryTask)
                    .where(RegulatoryTask.phase_id == phase.id)
                    .order_by(RegulatoryTask.sort_order, RegulatoryTask.created_at)
                )
            ).scalars().all()

            payload_tasks: list[dict[str, Any]] = []
            for task in tasks_q:
                tag_rows = (
                    await session.execute(
                        select(RegulatoryTag)
                        .join(
                            RegulatoryTaskTag,
                            RegulatoryTaskTag.tag_id == RegulatoryTag.id,
                        )
                        .where(
                            RegulatoryTaskTag.task_id == task.id,
                            # Defense-in-depth: only this org's tags.
                            RegulatoryTag.organization_id == org_id,
                        )
                    )
                ).scalars().all()
                payload_tasks.append(
                    {
                        "body": task.body,
                        "completed": task.completed,
                        "tags": [
                            {"slug": t.slug, "label": t.label, "color_token": t.color_token}
                            for t in tag_rows
                        ],
                    }
                )

            stream_total += len(tasks_q)
            stream_done += sum(1 for t in tasks_q if t.completed)

            payload_phases.append(
                {
                    "name": phase.name,
                    "badge_kind": phase.badge_kind,
                    "timing_label": phase.timing_label,
                    "default_open": phase.default_open,
                    "priority_notes": [
                        {"body": n.body, "severity": n.severity} for n in notes_q
                    ],
                    "tasks": payload_tasks,
                }
            )

        grand_total += stream_total
        grand_done += stream_done
        payload_streams.append(
            {
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


def _percent(done: int, total: int) -> int:
    if total == 0:
        return 0
    return round(done * 100 / total)


__all__ = ["router"]
