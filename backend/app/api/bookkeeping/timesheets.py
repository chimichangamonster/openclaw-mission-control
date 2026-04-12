"""Bookkeeping timesheets — hours logging, approval, weekly summaries."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import ORG_ACTOR_DEP
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.bookkeeping import BkTimesheet
from app.services.organizations import OrganizationContext

router = APIRouter(prefix="/timesheets")


class TimesheetCreate(BaseModel):
    placement_id: str | None = None
    worker_id: str
    job_id: str
    work_date: date
    regular_hours: float = 0.0
    overtime_hours: float = 0.0
    notes: str | None = None


@router.post("", status_code=201)
async def create_timesheet(
    payload: TimesheetCreate, org_ctx: OrganizationContext = ORG_ACTOR_DEP
) -> Any:
    async with async_session_maker() as session:
        ts = BkTimesheet(
            id=uuid4(),
            organization_id=org_ctx.organization.id,
            placement_id=payload.placement_id,
            worker_id=payload.worker_id,
            job_id=payload.job_id,
            work_date=payload.work_date,
            regular_hours=payload.regular_hours,
            overtime_hours=payload.overtime_hours,
            notes=payload.notes,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(ts)
        await session.commit()
        await session.refresh(ts)
        return _serialize(ts)


@router.get("")
async def list_timesheets(
    worker_id: str | None = None,
    job_id: str | None = None,
    status: str | None = None,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> Any:
    async with async_session_maker() as session:
        stmt = select(BkTimesheet).where(BkTimesheet.organization_id == org_ctx.organization.id)
        if worker_id:
            stmt = stmt.where(BkTimesheet.worker_id == worker_id)
        if job_id:
            stmt = stmt.where(BkTimesheet.job_id == job_id)
        if status:
            stmt = stmt.where(BkTimesheet.status == status)
        if from_date:
            stmt = stmt.where(BkTimesheet.work_date >= from_date)
        if to_date:
            stmt = stmt.where(BkTimesheet.work_date <= to_date)
        stmt = stmt.order_by(BkTimesheet.work_date.desc())  # type: ignore[attr-defined]
        result = await session.execute(stmt)
        return [_serialize(ts) for ts in result.scalars().all()]


@router.put("/{timesheet_id}/approve")
async def approve_timesheet(timesheet_id: str, org_ctx: OrganizationContext = ORG_ACTOR_DEP) -> Any:
    async with async_session_maker() as session:
        result = await session.execute(
            select(BkTimesheet).where(
                BkTimesheet.id == timesheet_id,
                BkTimesheet.organization_id == org_ctx.organization.id,
            )
        )
        ts = result.scalars().first()
        if not ts:
            raise HTTPException(status_code=404, detail="Timesheet not found")
        if ts.status != "pending":
            raise HTTPException(
                status_code=400, detail=f"Cannot approve timesheet with status '{ts.status}'"
            )

        ts.status = "approved"
        ts.approved_at = utcnow()
        ts.updated_at = utcnow()
        await session.commit()
        await session.refresh(ts)
        return _serialize(ts)


@router.put("/{timesheet_id}/reject")
async def reject_timesheet(timesheet_id: str, org_ctx: OrganizationContext = ORG_ACTOR_DEP) -> Any:
    async with async_session_maker() as session:
        result = await session.execute(
            select(BkTimesheet).where(
                BkTimesheet.id == timesheet_id,
                BkTimesheet.organization_id == org_ctx.organization.id,
            )
        )
        ts = result.scalars().first()
        if not ts:
            raise HTTPException(status_code=404, detail="Timesheet not found")
        if ts.status != "pending":
            raise HTTPException(
                status_code=400, detail=f"Cannot reject timesheet with status '{ts.status}'"
            )

        ts.status = "rejected"
        ts.updated_at = utcnow()
        await session.commit()
        await session.refresh(ts)
        return _serialize(ts)


@router.get("/summary/weekly")
async def weekly_summary(
    from_date: date = Query(alias="from"),
    to_date: date = Query(alias="to"),
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> Any:
    """Weekly summary: hours and worker count by job."""
    async with async_session_maker() as session:
        stmt = select(BkTimesheet).where(
            BkTimesheet.organization_id == org_ctx.organization.id,
            BkTimesheet.work_date >= from_date,
            BkTimesheet.work_date <= to_date,
        )
        result = await session.execute(stmt)
        timesheets = result.scalars().all()

        by_job: dict[str, dict[str, Any]] = {}
        for ts in timesheets:
            jid = str(ts.job_id)
            if jid not in by_job:
                by_job[jid] = {
                    "job_id": jid,
                    "workers": set(),
                    "regular_hours": 0.0,
                    "overtime_hours": 0.0,
                }
            by_job[jid]["workers"].add(str(ts.worker_id))
            by_job[jid]["regular_hours"] += ts.regular_hours
            by_job[jid]["overtime_hours"] += ts.overtime_hours

        return [
            {
                "job_id": v["job_id"],
                "worker_count": len(v["workers"]),
                "regular_hours": round(v["regular_hours"], 2),
                "overtime_hours": round(v["overtime_hours"], 2),
                "total_hours": round(v["regular_hours"] + v["overtime_hours"], 2),
            }
            for v in by_job.values()
        ]


def _serialize(ts: BkTimesheet) -> dict[str, Any]:
    return {
        "id": str(ts.id),
        "placement_id": str(ts.placement_id) if ts.placement_id else None,
        "worker_id": str(ts.worker_id),
        "job_id": str(ts.job_id),
        "date": str(ts.work_date),
        "regular_hours": ts.regular_hours,
        "overtime_hours": ts.overtime_hours,
        "notes": ts.notes,
        "status": ts.status,
        "approved_by": ts.approved_by,
        "approved_at": ts.approved_at.isoformat() if ts.approved_at else None,
        "created_at": ts.created_at.isoformat(),
        "updated_at": ts.updated_at.isoformat(),
    }
