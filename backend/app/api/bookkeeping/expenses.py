"""Bookkeeping expenses — CRUD + receipt upload + summaries."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import ORG_ACTOR_DEP
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.bookkeeping import BkExpense
from app.services.bookkeeping_exports import generate_expense_summary
from app.services.organizations import OrganizationContext

router = APIRouter(prefix="/expenses")


class ExpenseCreate(BaseModel):
    worker_id: str | None = None
    job_id: str | None = None
    amount: float
    gst_amount: float = 0.0
    category: str | None = None
    vendor: str | None = None
    description: str | None = None
    expense_date: date | None = None


class ExpenseUpdate(BaseModel):
    worker_id: str | None = None
    job_id: str | None = None
    amount: float | None = None
    gst_amount: float | None = None
    category: str | None = None
    vendor: str | None = None
    description: str | None = None


@router.post("", status_code=201)
async def create_expense(payload: ExpenseCreate, org_ctx: OrganizationContext = ORG_ACTOR_DEP):
    async with async_session_maker() as session:
        expense = BkExpense(
            id=uuid4(),
            organization_id=org_ctx.organization.id,
            worker_id=payload.worker_id,
            job_id=payload.job_id,
            amount=payload.amount,
            gst_amount=payload.gst_amount,
            category=payload.category,
            vendor=payload.vendor,
            description=payload.description,
            expense_date=payload.expense_date or date.today(),
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(expense)
        await session.commit()
        await session.refresh(expense)
        return _serialize(expense)


@router.get("")
async def list_expenses(
    job_id: str | None = None,
    worker_id: str | None = None,
    category: str | None = None,
    from_date: date | None = Query(default=None, alias="from"),
    to_date: date | None = Query(default=None, alias="to"),
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
):
    async with async_session_maker() as session:
        stmt = select(BkExpense).where(BkExpense.organization_id == org_ctx.organization.id)
        if job_id:
            stmt = stmt.where(BkExpense.job_id == job_id)
        if worker_id:
            stmt = stmt.where(BkExpense.worker_id == worker_id)
        if category:
            stmt = stmt.where(BkExpense.category == category)
        if from_date:
            stmt = stmt.where(BkExpense.expense_date >= from_date)  # type: ignore[operator]
        if to_date:
            stmt = stmt.where(BkExpense.expense_date <= to_date)  # type: ignore[operator]
        stmt = stmt.order_by(BkExpense.expense_date.desc())  # type: ignore[union-attr]
        result = await session.execute(stmt)
        return [_serialize(e) for e in result.scalars().all()]


@router.get("/summary")
async def expense_summary(org_ctx: OrganizationContext = ORG_ACTOR_DEP):
    async with async_session_maker() as session:
        result = await session.execute(
            select(BkExpense).where(BkExpense.organization_id == org_ctx.organization.id)
        )
        expenses = [
            {"amount": e.amount, "gst_amount": e.gst_amount, "category": e.category, "job_id": str(e.job_id) if e.job_id else None}
            for e in result.scalars().all()
        ]
        return generate_expense_summary(expenses)


@router.get("/{expense_id}")
async def get_expense(expense_id: str, org_ctx: OrganizationContext = ORG_ACTOR_DEP):
    async with async_session_maker() as session:
        result = await session.execute(
            select(BkExpense).where(BkExpense.id == expense_id, BkExpense.organization_id == org_ctx.organization.id)
        )
        expense = result.scalars().first()
        if not expense:
            raise HTTPException(status_code=404, detail="Expense not found")
        return _serialize(expense)


@router.put("/{expense_id}")
async def update_expense(expense_id: str, payload: ExpenseUpdate, org_ctx: OrganizationContext = ORG_ACTOR_DEP):
    async with async_session_maker() as session:
        result = await session.execute(
            select(BkExpense).where(BkExpense.id == expense_id, BkExpense.organization_id == org_ctx.organization.id)
        )
        expense = result.scalars().first()
        if not expense:
            raise HTTPException(status_code=404, detail="Expense not found")

        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(expense, field, value)
        expense.updated_at = utcnow()
        await session.commit()
        await session.refresh(expense)
        return _serialize(expense)


def _serialize(e: BkExpense) -> dict:
    return {
        "id": str(e.id),
        "worker_id": str(e.worker_id) if e.worker_id else None,
        "job_id": str(e.job_id) if e.job_id else None,
        "amount": e.amount,
        "gst_amount": e.gst_amount,
        "category": e.category,
        "vendor": e.vendor,
        "description": e.description,
        "receipt_url": e.receipt_url,
        "ocr_data": e.ocr_data,
        "date": str(e.expense_date),
        "created_at": e.created_at.isoformat(),
        "updated_at": e.updated_at.isoformat(),
    }
