"""Bookkeeping invoices — CRUD, generate from timesheets, status updates, email send."""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import ORG_ACTOR_DEP
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.bookkeeping import BkInvoice, BkInvoiceLine, BkTimesheet, BkPlacement, BkWorker, BkClient
from app.services.organizations import OrganizationContext

logger = get_logger(__name__)
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


class InvoiceSendRequest(BaseModel):
    subject: str | None = None
    message: str | None = None
    company_name: str | None = None
    company_email: str | None = None
    delivery: str = "email"  # "email", "wecom", or "both"
    wecom_user_id: str | None = None  # required when delivery includes wecom


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


@router.post("/{invoice_id}/send", status_code=200)
async def send_invoice_email(
    invoice_id: str,
    payload: InvoiceSendRequest | None = None,
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
):
    """Generate the invoice PDF and email it to the client's contact email.

    Optionally customize the email subject and message body.  Updates the
    invoice status to ``"sent"`` on success.
    """
    body = payload or InvoiceSendRequest()
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        # Fetch invoice
        result = await session.execute(
            select(BkInvoice).where(
                BkInvoice.id == invoice_id,
                BkInvoice.organization_id == org_id,
            )
        )
        invoice = result.scalars().first()
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")

        # Fetch client
        client_result = await session.execute(
            select(BkClient).where(BkClient.id == invoice.client_id)
        )
        client = client_result.scalars().first()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        # Fetch line items
        lines_result = await session.execute(
            select(BkInvoiceLine)
            .where(BkInvoiceLine.invoice_id == invoice.id)
            .order_by(BkInvoiceLine.created_at)
        )
        lines = lines_result.scalars().all()

        # Generate PDF
        from app.services.invoice_pdf import generate_invoice_pdf

        invoice_data = {
            "id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "subtotal": invoice.subtotal,
            "gst_amount": invoice.gst_amount,
            "total": invoice.total,
            "issued_date": str(invoice.issued_date) if invoice.issued_date else str(date.today()),
            "due_date": str(invoice.due_date) if invoice.due_date else None,
            "notes": invoice.notes,
        }
        client_data = {
            "name": client.name,
            "contact_name": client.contact_name or "",
            "contact_email": client.contact_email or "",
            "address": client.address or "",
        }
        line_items = [
            {
                "description": l.description,
                "quantity": l.quantity,
                "unit_price": l.unit_price,
                "amount": l.amount,
            }
            for l in lines
        ] if lines else None

        company = {
            "name": body.company_name or "Vantage Solutions",
            "address": "Alberta, Canada",
            "email": body.company_email or "info@vantagesolutions.ca",
            "phone": "",
            "gst_number": "",
        }
        pdf_bytes = generate_invoice_pdf(
            invoice=invoice_data,
            client=client_data,
            company=company,
            lines=line_items,
        )

        inv_number = invoice.invoice_number or str(invoice.id)[:8].upper()
        filename = f"invoice-{inv_number}.pdf"
        subject = body.subject or f"Invoice {inv_number} from {company['name']}"
        message_body = body.message or (
            f"Please find attached invoice {inv_number} for ${invoice.total:,.2f}."
            f"\n\nDue date: {invoice.due_date or 'Upon receipt'}."
            f"\n\nThank you for your business."
        )
        message_html = (
            f"<p>Please find attached invoice <strong>{inv_number}</strong> "
            f"for <strong>${invoice.total:,.2f}</strong>.</p>"
            f"<p>Due date: {invoice.due_date or 'Upon receipt'}.</p>"
            f"<p>Thank you for your business.</p>"
        )
        if body.message:
            message_html = f"<p>{body.message}</p>"

        delivery = body.delivery or "email"
        sent_via: list[str] = []

        # ── Email delivery ─────────────────────────────────────────────
        if delivery in ("email", "both"):
            if not client.contact_email:
                raise HTTPException(
                    status_code=422,
                    detail="Client has no contact email address. Update the client record first.",
                )
            from app.services.email_send import NoEmailAccountError, get_org_shared_email_account, send_email

            try:
                email_account = await get_org_shared_email_account(session, org_id)
            except NoEmailAccountError:
                raise HTTPException(
                    status_code=422,
                    detail="No shared email account connected. Connect an email account first.",
                )

            await send_email(
                session,
                email_account,
                to=client.contact_email,
                subject=subject,
                body=message_body,
                body_html=message_html,
                attachments=[
                    {
                        "filename": filename,
                        "content_bytes": pdf_bytes,
                        "content_type": "application/pdf",
                    }
                ],
            )
            sent_via.append("email")

        # ── WeCom delivery ─────────────────────────────────────────────
        if delivery in ("wecom", "both"):
            if not body.wecom_user_id:
                raise HTTPException(
                    status_code=422,
                    detail="wecom_user_id is required for WeCom delivery.",
                )
            from app.services.wecom_send import NoWeComConnectionError, get_org_wecom_connection, send_wecom_news

            try:
                wecom_conn = await get_org_wecom_connection(session, org_id)
            except NoWeComConnectionError:
                raise HTTPException(
                    status_code=422,
                    detail="No active WeCom connection for this organization.",
                )

            # Generate HMAC-signed download URL for the PDF
            from app.core.file_tokens import create_file_token

            token_path = f"invoices/{filename}"
            # Store PDF to workspace so file_serve can find it
            from app.core.workspace import resolve_org_workspace

            workspace = resolve_org_workspace(org_ctx.organization)
            invoice_dir = workspace / "invoices"
            invoice_dir.mkdir(parents=True, exist_ok=True)
            (invoice_dir / filename).write_bytes(pdf_bytes)

            file_token = create_file_token(token_path, expires_hours=168)  # 7 days
            from app.core.config import settings
            download_url = f"{settings.base_url}/api/v1/files/download?token={file_token}"

            description = (
                f"Amount: ${invoice.total:,.2f}\n"
                f"Due: {invoice.due_date or 'Upon receipt'}\n"
                f"Client: {client.name}"
            )

            success = await send_wecom_news(
                session,
                wecom_conn,
                to_user=body.wecom_user_id,
                title=f"Invoice {inv_number}",
                description=description,
                url=download_url,
            )
            if not success:
                raise HTTPException(
                    status_code=502,
                    detail="Failed to deliver invoice via WeCom. Check WeCom connection.",
                )
            sent_via.append("wecom")

        # Update status to sent
        invoice.status = "sent"
        if not invoice.issued_date:
            invoice.issued_date = date.today()
        invoice.updated_at = utcnow()
        session.add(invoice)
        await session.commit()
        await session.refresh(invoice)

        logger.info(
            "invoice.sent",
            extra={
                "invoice_id": str(invoice.id),
                "delivery": delivery,
                "sent_via": sent_via,
            },
        )

        return {
            "ok": True,
            "invoice_id": str(invoice.id),
            "sent_via": sent_via,
            "status": "sent",
        }


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
