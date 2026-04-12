"""Bookkeeping exports — QuickBooks CSV/IIF, expense reports, GST summaries."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlmodel import select

from app.api.deps import ORG_ACTOR_DEP
from app.db.session import async_session_maker
from app.models.bookkeeping import BkExpense, BkTransaction
from app.services.bookkeeping_exports import generate_csv, generate_expense_summary, generate_iif
from app.services.organizations import OrganizationContext

router = APIRouter(prefix="/exports")


@router.get("/quickbooks/csv")
async def export_csv(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> Any:
    """Export transactions as QuickBooks Online-compatible CSV."""
    async with async_session_maker() as session:
        stmt = select(BkTransaction).where(BkTransaction.organization_id == org_ctx.organization.id)
        if from_date:
            stmt = stmt.where(BkTransaction.txn_date >= from_date)
        if to_date:
            stmt = stmt.where(BkTransaction.txn_date <= to_date)
        stmt = stmt.order_by(BkTransaction.txn_date)  # type: ignore[arg-type]
        result = await session.execute(stmt)

        transactions = [
            {
                "date": str(t.txn_date),
                "type": t.type,
                "amount": t.amount,
                "gst_amount": t.gst_amount,
                "description": t.description,
                "job_id": str(t.job_id) if t.job_id else "",
                "category": t.category or "",
            }
            for t in result.scalars().all()
        ]

    csv_content = generate_csv(transactions)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=quickbooks-export.csv"},
    )


@router.get("/quickbooks/iif")
async def export_iif(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> Any:
    """Export transactions as QuickBooks Desktop IIF format."""
    async with async_session_maker() as session:
        stmt = select(BkTransaction).where(BkTransaction.organization_id == org_ctx.organization.id)
        if from_date:
            stmt = stmt.where(BkTransaction.txn_date >= from_date)
        if to_date:
            stmt = stmt.where(BkTransaction.txn_date <= to_date)
        stmt = stmt.order_by(BkTransaction.txn_date)  # type: ignore[arg-type]
        result = await session.execute(stmt)

        transactions = [
            {
                "date": str(t.txn_date),
                "type": t.type,
                "amount": t.amount,
                "gst_amount": t.gst_amount,
                "description": t.description,
                "category": t.category,
            }
            for t in result.scalars().all()
        ]

    iif_content = generate_iif(transactions)
    return Response(
        content=iif_content,
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=quickbooks-export.iif"},
    )


@router.get("/expense-report")
async def export_expense_report(
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> Any:
    """Plain text expense report with summary and category breakdown."""
    async with async_session_maker() as session:
        stmt = select(BkExpense).where(BkExpense.organization_id == org_ctx.organization.id)
        if from_date:
            stmt = stmt.where(BkExpense.expense_date >= from_date)
        if to_date:
            stmt = stmt.where(BkExpense.expense_date <= to_date)
        stmt = stmt.order_by(BkExpense.expense_date)  # type: ignore[arg-type]
        result = await session.execute(stmt)
        expenses = result.scalars().all()

    summary = generate_expense_summary(
        [
            {
                "amount": e.amount,
                "gst_amount": e.gst_amount,
                "category": e.category,
                "job_id": str(e.job_id) if e.job_id else None,
            }
            for e in expenses
        ]
    )

    lines = [
        f"EXPENSE REPORT",
        f"Period: {from_date or 'all'} to {to_date or 'present'}",
        f"",
        f"SUMMARY",
        f"  Total: ${summary['total']:,.2f}",
        f"  GST:   ${summary['total_gst']:,.2f}",
        f"  Count: {len(expenses)}",
        f"",
        f"BY CATEGORY",
    ]
    for cat, data in summary["by_category"].items():
        lines.append(
            f"  {cat}: {data['count']} expenses, ${data['total']:,.2f} (GST ${data['gst']:,.2f})"
        )

    lines.extend(["", "DETAIL"])
    for e in expenses:
        lines.append(
            f"  {e.expense_date} | ${e.amount:,.2f} | {e.vendor or '-'} | {e.category or '-'} | {e.description or '-'}"
        )

    return Response(
        content="\n".join(lines),
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=expense-report.txt"},
    )
