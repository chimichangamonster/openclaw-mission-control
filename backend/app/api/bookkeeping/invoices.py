"""Bookkeeping invoices — CRUD, generate from timesheets, status updates."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import ORG_ACTOR_DEP
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.bookkeeping import BkInvoice, BkInvoiceLine, BkTimesheet, BkPlacement, BkWorker, BkClient
from app.services.organizations import OrganizationContext

router = APIRouter(prefix="/invoices")

GST_RATE = 0.05  # Alberta: 5% GST


class InvoiceCreate(BaseModel):
    client_id: str
    invoice_number: str | None = None
    subtotal: float = 0.0
    gst_amount: float = 0.0
    total: float = 0.0
    due_date: date | None = None
    notes: str | None = None


class InvoiceFromTimesheets(BaseModel):
    client_id: str
    job_id: str
    from_date: date | None = None
    to_date: date | None = None
    notes: str | None = None


class StatusUpdate(BaseModel):
    status: str


@router.post("", status_code=201)
async def create_invoice(payload: InvoiceCreate, org_ctx: OrganizationContext = ORG_ACTOR_DEP):
    async with async_session_maker() as session:
        invoice = BkInvoice(
            id=uuid4(),
            organization_id=org_ctx.organization.id,
            client_id=payload.client_id,
            invoice_number=payload.invoice_number,
            subtotal=payload.subtotal,
            gst_amount=payload.gst_amount,
            total=payload.total,
            due_date=payload.due_date,
            notes=payload.notes,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(invoice)
        await session.commit()
        await session.refresh(invoice)
        return _serialize_invoice(invoice)


@router.post("/from-timesheets", status_code=201)
async def create_from_timesheets(payload: InvoiceFromTimesheets, org_ctx: OrganizationContext = ORG_ACTOR_DEP):
    """Generate an invoice from approved timesheets for a job/client.

    Calculates line items from timesheet hours x placement bill rates.
    Regular hours at bill_rate, overtime at 1.5x bill_rate. 5% GST (Alberta).
    """
    org_id = org_ctx.organization.id
    to_dt = payload.to_date or date.today()

    async with async_session_maker() as session:
        # Get approved timesheets with placements and worker names
        stmt = (
            select(BkTimesheet, BkPlacement, BkWorker)
            .join(BkPlacement, BkTimesheet.placement_id == BkPlacement.id)
            .join(BkWorker, BkTimesheet.worker_id == BkWorker.id)
            .where(
                BkTimesheet.organization_id == org_id,
                BkTimesheet.job_id == payload.job_id,
                BkTimesheet.status == "approved",
                BkTimesheet.work_date <= to_dt,  # type: ignore[operator]
            )
        )
        if payload.from_date:
            stmt = stmt.where(BkTimesheet.work_date >= payload.from_date)  # type: ignore[operator]
        stmt = stmt.order_by(BkTimesheet.work_date)  # type: ignore[union-attr]

        result = await session.execute(stmt)
        rows = result.all()

        if not rows:
            raise HTTPException(status_code=404, detail="No approved timesheets found for the given criteria")

        # Build line items
        lines = []
        subtotal = 0.0
        for ts, pl, worker in rows:
            reg_amount = ts.regular_hours * pl.bill_rate
            ot_amount = ts.overtime_hours * pl.bill_rate * 1.5
            line_total = reg_amount + ot_amount

            desc = f"{worker.name} - {ts.work_date}"
            if ts.regular_hours > 0:
                desc += f" ({ts.regular_hours}h reg)"
            if ts.overtime_hours > 0:
                desc += f" ({ts.overtime_hours}h OT)"

            lines.append({
                "description": desc,
                "quantity": ts.regular_hours + ts.overtime_hours * 1.5,
                "unit_price": pl.bill_rate,
                "amount": line_total,
                "timesheet_id": ts.id,
            })
            subtotal += line_total

        gst_amount = round(subtotal * GST_RATE, 2)
        total = round(subtotal + gst_amount, 2)

        # Create invoice
        invoice = BkInvoice(
            id=uuid4(),
            organization_id=org_id,
            client_id=payload.client_id,
            subtotal=round(subtotal, 2),
            gst_amount=gst_amount,
            total=total,
            issued_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            notes=payload.notes or f"Timesheet invoice for job {payload.job_id}",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(invoice)
        await session.flush()  # get invoice.id

        # Create line items
        for line in lines:
            session.add(BkInvoiceLine(
                id=uuid4(),
                organization_id=org_id,
                invoice_id=invoice.id,
                description=line["description"],
                quantity=line["quantity"],
                unit_price=line["unit_price"],
                amount=line["amount"],
                timesheet_id=line["timesheet_id"],
                created_at=utcnow(),
            ))

        await session.commit()
        await session.refresh(invoice)

        return {
            "invoice": _serialize_invoice(invoice),
            "line_count": len(lines),
            "subtotal": round(subtotal, 2),
            "gst_amount": gst_amount,
            "total": total,
        }


@router.get("")
async def list_invoices(
    status: str | None = None,
    client_id: str | None = None,
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
):
    async with async_session_maker() as session:
        stmt = (
            select(BkInvoice, BkClient.name)
            .join(BkClient, BkInvoice.client_id == BkClient.id)
            .where(BkInvoice.organization_id == org_ctx.organization.id)
        )
        if status:
            stmt = stmt.where(BkInvoice.status == status)
        if client_id:
            stmt = stmt.where(BkInvoice.client_id == client_id)
        stmt = stmt.order_by(BkInvoice.created_at.desc())  # type: ignore[union-attr]
        result = await session.execute(stmt)
        return [{**_serialize_invoice(inv), "client_name": name} for inv, name in result.all()]


@router.get("/{invoice_id}")
async def get_invoice(invoice_id: str, org_ctx: OrganizationContext = ORG_ACTOR_DEP):
    async with async_session_maker() as session:
        inv_result = await session.execute(
            select(BkInvoice, BkClient.name)
            .join(BkClient, BkInvoice.client_id == BkClient.id)
            .where(BkInvoice.id == invoice_id, BkInvoice.organization_id == org_ctx.organization.id)
        )
        row = inv_result.first()
        if not row:
            raise HTTPException(status_code=404, detail="Invoice not found")
        invoice, client_name = row

        lines_result = await session.execute(
            select(BkInvoiceLine)
            .where(BkInvoiceLine.invoice_id == invoice_id)
            .order_by(BkInvoiceLine.created_at)
        )
        lines = [
            {
                "id": str(l.id),
                "description": l.description,
                "quantity": l.quantity,
                "unit_price": l.unit_price,
                "amount": l.amount,
                "timesheet_id": str(l.timesheet_id) if l.timesheet_id else None,
            }
            for l in lines_result.scalars().all()
        ]

        return {**_serialize_invoice(invoice), "client_name": client_name, "lines": lines}


@router.put("/{invoice_id}/status")
async def update_invoice_status(invoice_id: str, payload: StatusUpdate, org_ctx: OrganizationContext = ORG_ACTOR_DEP):
    async with async_session_maker() as session:
        result = await session.execute(
            select(BkInvoice).where(BkInvoice.id == invoice_id, BkInvoice.organization_id == org_ctx.organization.id)
        )
        invoice = result.scalars().first()
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")

        invoice.status = payload.status
        invoice.updated_at = utcnow()
        if payload.status == "paid":
            invoice.paid_date = date.today()
        if payload.status == "sent" and not invoice.issued_date:
            invoice.issued_date = date.today()
        await session.commit()
        await session.refresh(invoice)
        return _serialize_invoice(invoice)


def _serialize_invoice(inv: BkInvoice) -> dict:
    return {
        "id": str(inv.id),
        "client_id": str(inv.client_id),
        "invoice_number": inv.invoice_number,
        "status": inv.status,
        "subtotal": inv.subtotal,
        "gst_amount": inv.gst_amount,
        "total": inv.total,
        "issued_date": str(inv.issued_date) if inv.issued_date else None,
        "due_date": str(inv.due_date) if inv.due_date else None,
        "paid_date": str(inv.paid_date) if inv.paid_date else None,
        "exported_at": inv.exported_at.isoformat() if inv.exported_at else None,
        "notes": inv.notes,
        "created_at": inv.created_at.isoformat(),
        "updated_at": inv.updated_at.isoformat(),
    }
