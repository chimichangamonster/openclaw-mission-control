"""Bookkeeping transactions — general ledger, cashflow, GST/HST summaries."""


from __future__ import annotations

from typing import Any

from datetime import date, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import ORG_ACTOR_DEP
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.bookkeeping import BkTransaction
from app.services.organizations import OrganizationContext

router = APIRouter(prefix="/transactions")


class TransactionCreate(BaseModel):
    type: str  # income, expense
    amount: float
    gst_amount: float = 0.0
    category: str | None = None
    description: str | None = None
    txn_date: date | None = None
    job_id: str | None = None
    expense_id: str | None = None
    invoice_id: str | None = None


@router.post("", status_code=201)
async def create_transaction(
    payload: TransactionCreate, org_ctx: OrganizationContext = ORG_ACTOR_DEP
) -> Any:
    if payload.type not in ("income", "expense"):
        raise HTTPException(status_code=400, detail="type must be 'income' or 'expense'")
    async with async_session_maker() as session:
        txn = BkTransaction(
            id=uuid4(),
            organization_id=org_ctx.organization.id,
            type=payload.type,
            amount=payload.amount,
            gst_amount=payload.gst_amount,
            category=payload.category,
            description=payload.description,
            txn_date=payload.txn_date or date.today(),
            job_id=payload.job_id,
            expense_id=payload.expense_id,
            invoice_id=payload.invoice_id,
            created_at=utcnow(),
        )
        session.add(txn)
        await session.commit()
        await session.refresh(txn)
        return _serialize(txn)


@router.get("")
async def list_transactions(
    type: str | None = None,
    category: str | None = None,
    job_id: str | None = None,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> Any:
    async with async_session_maker() as session:
        stmt = select(BkTransaction).where(BkTransaction.organization_id == org_ctx.organization.id)
        if type:
            stmt = stmt.where(BkTransaction.type == type)
        if category:
            stmt = stmt.where(BkTransaction.category == category)
        if job_id:
            stmt = stmt.where(BkTransaction.job_id == job_id)
        if from_date:
            stmt = stmt.where(BkTransaction.txn_date >= from_date)
        if to_date:
            stmt = stmt.where(BkTransaction.txn_date <= to_date)
        stmt = stmt.order_by(BkTransaction.txn_date.desc())  # type: ignore[attr-defined]
        result = await session.execute(stmt)
        return [_serialize(t) for t in result.scalars().all()]


@router.get("/cashflow")
async def cashflow_summary(
    period: str = Query(default="month"),  # week, month, quarter
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> Any:
    """Cashflow summary for a period: total income, expenses, net, GST."""
    from datetime import timedelta

    today = date.today()
    if period == "week":
        start = today - timedelta(days=7)
    elif period == "quarter":
        start = today - timedelta(days=90)
    else:
        start = today - timedelta(days=30)

    async with async_session_maker() as session:
        result = await session.execute(
            select(BkTransaction).where(
                BkTransaction.organization_id == org_ctx.organization.id,
                BkTransaction.txn_date >= start,
            )
        )
        transactions = result.scalars().all()

        income = sum(t.amount for t in transactions if t.type == "income")
        expenses = sum(t.amount for t in transactions if t.type == "expense")
        gst_collected = sum(t.gst_amount for t in transactions if t.type == "income")
        gst_paid = sum(t.gst_amount for t in transactions if t.type == "expense")

        return {
            "period": period,
            "from": str(start),
            "to": str(today),
            "total_income": round(income, 2),
            "total_expenses": round(expenses, 2),
            "net": round(income - expenses, 2),
            "gst_collected": round(gst_collected, 2),
            "gst_paid": round(gst_paid, 2),
            "count": len(transactions),
        }


@router.get("/hst")
async def hst_summary(
    quarter: str = Query(default="Q1"),  # Q1, Q2, Q3, Q4
    year: int = Query(default=2026),
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> Any:
    """Quarterly GST summary for CRA filing."""
    quarter_starts = {"Q1": 1, "Q2": 4, "Q3": 7, "Q4": 10}
    start_month = quarter_starts.get(quarter, 1)
    start = date(year, start_month, 1)
    end_month = start_month + 2
    end_year = year
    if end_month > 12:
        end_month -= 12
        end_year += 1
    # Last day of the quarter
    if end_month == 12:
        end = date(end_year, 12, 31)
    else:
        end = date(end_year, end_month + 1, 1) - timedelta(days=1)

    async with async_session_maker() as session:
        result = await session.execute(
            select(BkTransaction).where(
                BkTransaction.organization_id == org_ctx.organization.id,
                BkTransaction.txn_date >= start,
                BkTransaction.txn_date <= end,
            )
        )
        transactions = result.scalars().all()

        gst_collected = sum(t.gst_amount for t in transactions if t.type == "income")
        input_tax_credits = sum(t.gst_amount for t in transactions if t.type == "expense")

        return {
            "quarter": quarter,
            "year": year,
            "from": str(start),
            "to": str(end),
            "gst_collected": round(gst_collected, 2),
            "input_tax_credits": round(input_tax_credits, 2),
            "net_gst_owing": round(gst_collected - input_tax_credits, 2),
            "income_count": sum(1 for t in transactions if t.type == "income"),
            "expense_count": sum(1 for t in transactions if t.type == "expense"),
        }


def _serialize(t: BkTransaction) -> dict[str, Any]:
    return {
        "id": str(t.id),
        "type": t.type,
        "amount": t.amount,
        "gst_amount": t.gst_amount,
        "category": t.category,
        "description": t.description,
        "date": str(t.txn_date),
        "job_id": str(t.job_id) if t.job_id else None,
        "expense_id": str(t.expense_id) if t.expense_id else None,
        "invoice_id": str(t.invoice_id) if t.invoice_id else None,
        "created_at": t.created_at.isoformat(),
    }
