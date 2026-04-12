"""Invoice management — list invoices and generate PDFs from local bookkeeping models."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlmodel import select

from app.api.deps import ORG_ACTOR_DEP
from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import async_session_maker
from app.models.bookkeeping import BkClient, BkInvoice, BkInvoiceLine
from app.services.invoice_pdf import generate_invoice_pdf
from app.services.organizations import OrganizationContext

logger = get_logger(__name__)
router = APIRouter(prefix="/invoices", tags=["invoices"])

DEFAULT_COMPANY = {
    "name": "Vantage Solutions",
    "address": "Alberta, Canada",
    "email": "info@vantagesolutions.ca",
    "phone": "",
    "gst_number": "",
}


@router.get(
    "",
    summary="List all invoices",
)
async def list_invoices(
    ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> list[dict[str, Any]]:
    """List all invoices for the organization."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(BkInvoice, BkClient.name)
            .join(BkClient, BkInvoice.client_id == BkClient.id)  # type: ignore[arg-type]
            .where(BkInvoice.organization_id == ctx.organization.id)
            .order_by(BkInvoice.created_at.desc())  # type: ignore[attr-defined]
        )
        return [
            {
                "id": str(inv.id),
                "client_id": str(inv.client_id),
                "client_name": client_name,
                "invoice_number": inv.invoice_number,
                "status": inv.status,
                "subtotal": inv.subtotal,
                "gst_amount": inv.gst_amount,
                "total": inv.total,
                "issued_date": str(inv.issued_date) if inv.issued_date else None,
                "due_date": str(inv.due_date) if inv.due_date else None,
                "paid_date": str(inv.paid_date) if inv.paid_date else None,
                "notes": inv.notes,
                "created_at": inv.created_at.isoformat(),
            }
            for inv, client_name in result.all()
        ]


@router.get(
    "/{invoice_id}/pdf",
    summary="Generate invoice PDF",
    response_class=Response,
)
async def get_invoice_pdf(
    invoice_id: str,
    token: str = Query(..., description="Auth token"),
    company_name: str = Query(default=None),
    company_email: str = Query(default=None),
) -> Response:
    """Generate a PDF for the given invoice. Auth via ?token= query param."""
    if token != settings.local_auth_token:
        raise HTTPException(status_code=401, detail="Invalid token")

    async with async_session_maker() as session:
        # Fetch invoice
        inv_result = await session.execute(select(BkInvoice).where(BkInvoice.id == invoice_id))
        invoice = inv_result.scalars().first()
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")

        # Fetch client
        client_result = await session.execute(
            select(BkClient).where(BkClient.id == invoice.client_id)
        )
        client = client_result.scalars().first()

        # Fetch line items
        lines_result = await session.execute(
            select(BkInvoiceLine)
            .where(BkInvoiceLine.invoice_id == invoice.id)
            .order_by(BkInvoiceLine.created_at)  # type: ignore[arg-type]
        )
        lines = lines_result.scalars().all()

    # Build dicts for PDF generator
    invoice_data = {
        "id": str(invoice.id),
        "invoice_number": invoice.invoice_number,
        "subtotal": invoice.subtotal,
        "gst_amount": invoice.gst_amount,
        "total": invoice.total,
        "issued_date": str(invoice.issued_date) if invoice.issued_date else None,
        "due_date": str(invoice.due_date) if invoice.due_date else None,
        "notes": invoice.notes,
    }

    client_data = {
        "name": client.name if client else "",
        "contact_name": client.contact_name if client else "",
        "contact_email": client.contact_email if client else "",
        "address": client.address if client else "",
    }

    line_items = (
        [
            {
                "description": l.description,
                "quantity": l.quantity,
                "unit_price": l.unit_price,
                "amount": l.amount,
            }
            for l in lines  # noqa: E741
        ]
        if lines
        else None
    )

    company = DEFAULT_COMPANY.copy()
    if company_name:
        company["name"] = company_name
    if company_email:
        company["email"] = company_email

    pdf_bytes = generate_invoice_pdf(
        invoice=invoice_data,
        client=client_data,
        company=company,
        lines=line_items,
    )

    filename = f"invoice-{invoice.invoice_number or str(invoice.id)[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
