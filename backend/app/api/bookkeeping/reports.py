"""Bookkeeping reports — daily snapshot, margin analysis, worker performance."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Query
from sqlmodel import select

from app.api.deps import ORG_ACTOR_DEP
from app.db.session import async_session_maker
from app.models.bookkeeping import BkExpense, BkPlacement, BkTimesheet
from app.services.organizations import OrganizationContext

router = APIRouter(prefix="/reports")


@router.get("/daily")
async def daily_report(
    report_date: date = Query(alias="date", default=None),
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> Any:
    """Daily snapshot: hours by job, expenses by job, total workers."""
    d = report_date or date.today()
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        # Timesheets for this date
        ts_result = await session.execute(
            select(BkTimesheet).where(
                BkTimesheet.organization_id == org_id,
                BkTimesheet.work_date == d,
            )
        )
        timesheets = ts_result.scalars().all()

        hours_by_job: dict[str, dict[str, Any]] = {}
        workers_today = set()
        for ts in timesheets:
            jid = str(ts.job_id)
            if jid not in hours_by_job:
                hours_by_job[jid] = {"regular": 0.0, "overtime": 0.0}
            hours_by_job[jid]["regular"] += ts.regular_hours
            hours_by_job[jid]["overtime"] += ts.overtime_hours
            workers_today.add(str(ts.worker_id))

        # Expenses for this date
        exp_result = await session.execute(
            select(BkExpense).where(
                BkExpense.organization_id == org_id,
                BkExpense.expense_date == d,
            )
        )
        expenses = exp_result.scalars().all()

        expenses_by_job: dict[str, float] = {}
        for e in expenses:
            jid = str(e.job_id) if e.job_id else "unassigned"
            expenses_by_job[jid] = expenses_by_job.get(jid, 0) + e.amount

        return {
            "date": str(d),
            "total_workers": len(workers_today),
            "hours_by_job": hours_by_job,
            "expenses_by_job": expenses_by_job,
        }


@router.get("/margins")
async def margin_report(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> Any:
    """Margin analysis by job: bill vs pay rates, margin $, margin %."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        stmt = (
            select(BkTimesheet, BkPlacement)
            .join(BkPlacement, BkTimesheet.placement_id == BkPlacement.id)  # type: ignore[arg-type]
            .where(BkTimesheet.organization_id == org_id)
        )
        if from_date:
            stmt = stmt.where(BkTimesheet.work_date >= from_date)
        if to_date:
            stmt = stmt.where(BkTimesheet.work_date <= to_date)

        result = await session.execute(stmt)

        by_job: dict[str, dict[str, Any]] = {}
        for ts, pl in result.all():
            jid = str(ts.job_id)
            if jid not in by_job:
                by_job[jid] = {"bill": 0.0, "pay": 0.0, "hours": 0.0}
            total_hours = ts.regular_hours + ts.overtime_hours
            by_job[jid]["hours"] += total_hours
            by_job[jid]["bill"] += (
                ts.regular_hours * pl.bill_rate + ts.overtime_hours * pl.bill_rate * 1.5
            )
            by_job[jid]["pay"] += (
                ts.regular_hours * pl.pay_rate + ts.overtime_hours * pl.pay_rate * 1.5
            )

        return [
            {
                "job_id": jid,
                "total_hours": round(v["hours"], 2),
                "billable": round(v["bill"], 2),
                "labour_cost": round(v["pay"], 2),
                "margin_dollars": round(v["bill"] - v["pay"], 2),
                "margin_pct": (
                    round((v["bill"] - v["pay"]) / v["bill"] * 100, 1) if v["bill"] > 0 else 0
                ),
            }
            for jid, v in by_job.items()
        ]


@router.get("/workers")
async def worker_report(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> Any:
    """Worker performance: jobs worked, total hours, days worked."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        stmt = select(BkTimesheet).where(BkTimesheet.organization_id == org_id)
        if from_date:
            stmt = stmt.where(BkTimesheet.work_date >= from_date)
        if to_date:
            stmt = stmt.where(BkTimesheet.work_date <= to_date)

        result = await session.execute(stmt)
        timesheets = result.scalars().all()

        by_worker: dict[str, dict[str, Any]] = {}
        for ts in timesheets:
            wid = str(ts.worker_id)
            if wid not in by_worker:
                by_worker[wid] = {"jobs": set(), "regular": 0.0, "overtime": 0.0, "days": set()}
            by_worker[wid]["jobs"].add(str(ts.job_id))
            by_worker[wid]["regular"] += ts.regular_hours
            by_worker[wid]["overtime"] += ts.overtime_hours
            by_worker[wid]["days"].add(str(ts.work_date))

        return [
            {
                "worker_id": wid,
                "jobs_worked": len(v["jobs"]),
                "regular_hours": round(v["regular"], 2),
                "overtime_hours": round(v["overtime"], 2),
                "total_hours": round(v["regular"] + v["overtime"], 2),
                "days_worked": len(v["days"]),
            }
            for wid, v in by_worker.items()
        ]
