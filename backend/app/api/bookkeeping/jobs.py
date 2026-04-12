"""Bookkeeping jobs CRUD + cost breakdown."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import func, select

from app.api.deps import ORG_ACTOR_DEP
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.bookkeeping import BkExpense, BkJob, BkPlacement, BkTimesheet
from app.services.organizations import OrganizationContext

router = APIRouter(prefix="/jobs")


class JobCreate(BaseModel):
    client_id: str | None = None
    name: str
    site_address: str | None = None
    job_type: str | None = None
    status: str = "active"
    budget: float | None = None
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None


class JobUpdate(BaseModel):
    name: str | None = None
    site_address: str | None = None
    job_type: str | None = None
    status: str | None = None
    budget: float | None = None
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None


@router.post("", status_code=201)
async def create_job(payload: JobCreate, org_ctx: OrganizationContext = ORG_ACTOR_DEP) -> Any:
    async with async_session_maker() as session:
        job = BkJob(
            id=uuid4(),
            organization_id=org_ctx.organization.id,
            client_id=payload.client_id,
            name=payload.name,
            site_address=payload.site_address,
            job_type=payload.job_type,
            status=payload.status,
            budget=payload.budget,
            start_date=payload.start_date,
            end_date=payload.end_date,
            notes=payload.notes,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return _serialize(job)


@router.get("")
async def list_jobs(
    status: str | None = None,
    client_id: str | None = None,
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> Any:
    async with async_session_maker() as session:
        stmt = select(BkJob).where(BkJob.organization_id == org_ctx.organization.id)
        if status:
            stmt = stmt.where(BkJob.status == status)
        if client_id:
            stmt = stmt.where(BkJob.client_id == client_id)
        stmt = stmt.order_by(BkJob.created_at.desc())  # type: ignore[attr-defined]
        result = await session.execute(stmt)
        return [_serialize(j) for j in result.scalars().all()]


@router.get("/{job_id}")
async def get_job(job_id: str, org_ctx: OrganizationContext = ORG_ACTOR_DEP) -> Any:
    async with async_session_maker() as session:
        result = await session.execute(
            select(BkJob).where(
                BkJob.id == job_id, BkJob.organization_id == org_ctx.organization.id
            )
        )
        job = result.scalars().first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return _serialize(job)


@router.get("/{job_id}/costs")
async def get_job_costs(job_id: str, org_ctx: OrganizationContext = ORG_ACTOR_DEP) -> Any:
    """Cost breakdown for a job: expenses by category + labour costs by placement."""
    org_id = org_ctx.organization.id
    async with async_session_maker() as session:
        # Verify job exists
        job_result = await session.execute(
            select(BkJob).where(BkJob.id == job_id, BkJob.organization_id == org_id)
        )
        job = job_result.scalars().first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Expenses by category
        expense_result = await session.execute(
            select(BkExpense).where(BkExpense.job_id == job_id, BkExpense.organization_id == org_id)
        )
        expenses = expense_result.scalars().all()
        expense_by_cat: dict[str, float] = {}
        total_expenses = 0.0
        for e in expenses:
            cat = e.category or "uncategorized"
            expense_by_cat[cat] = expense_by_cat.get(cat, 0) + e.amount
            total_expenses += e.amount

        # Labour costs from timesheets + placements
        ts_result = await session.execute(
            select(BkTimesheet, BkPlacement)
            .join(BkPlacement, BkTimesheet.placement_id == BkPlacement.id, isouter=True)  # type: ignore[arg-type]
            .where(BkTimesheet.job_id == job_id, BkTimesheet.organization_id == org_id)
        )
        labour_cost = 0.0
        billable = 0.0
        for ts, pl in ts_result.all():
            if pl:
                reg = ts.regular_hours * pl.pay_rate
                ot = ts.overtime_hours * pl.pay_rate * 1.5
                labour_cost += reg + ot
                billable += ts.regular_hours * pl.bill_rate + ts.overtime_hours * pl.bill_rate * 1.5

        return {
            "job_id": str(job.id),
            "job_name": job.name,
            "budget": job.budget,
            "total_expenses": round(total_expenses, 2),
            "expenses_by_category": expense_by_cat,
            "labour_cost": round(labour_cost, 2),
            "billable_amount": round(billable, 2),
            "total_cost": round(total_expenses + labour_cost, 2),
            "margin": round(billable - labour_cost - total_expenses, 2) if billable else None,
        }


@router.put("/{job_id}")
async def update_job(
    job_id: str, payload: JobUpdate, org_ctx: OrganizationContext = ORG_ACTOR_DEP
) -> Any:
    async with async_session_maker() as session:
        result = await session.execute(
            select(BkJob).where(
                BkJob.id == job_id, BkJob.organization_id == org_ctx.organization.id
            )
        )
        job = result.scalars().first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(job, field, value)
        job.updated_at = utcnow()
        await session.commit()
        await session.refresh(job)
        return _serialize(job)


def _serialize(j: BkJob) -> dict[str, Any]:
    return {
        "id": str(j.id),
        "client_id": str(j.client_id) if j.client_id else None,
        "name": j.name,
        "site_address": j.site_address,
        "job_type": j.job_type,
        "status": j.status,
        "budget": j.budget,
        "start_date": str(j.start_date) if j.start_date else None,
        "end_date": str(j.end_date) if j.end_date else None,
        "notes": j.notes,
        "created_at": j.created_at.isoformat(),
        "updated_at": j.updated_at.isoformat(),
    }
