"""Invoice management — list invoices and generate PDFs."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.api.deps import ORG_MEMBER_DEP
from app.services.organizations import OrganizationContext

from app.core.config import settings
from app.core.logging import get_logger
from app.services.invoice_pdf import generate_invoice_pdf

logger = get_logger(__name__)
router = APIRouter(prefix="/invoices", tags=["invoices"])

DEFAULT_COMPANY = {
    "name": "Vantage Solutions",
    "address": "Alberta, Canada",
    "email": "info@vantagesolutions.ca",
    "phone": "",
    "gst_number": "",
}

BOOKKEEPING_BASE = "http://bookkeeping-api:8080"
BOOKKEEPING_TENANT_KEY = "24006b9258aa8ac47ccb07d6323d419da3f07b25fb8339156eddaf1108f27527"


async def _fetch_invoice(invoice_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BOOKKEEPING_BASE}/api/invoices/{invoice_id}",
            headers={"X-Tenant-Key": BOOKKEEPING_TENANT_KEY},
        )
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Invoice not found")
        resp.raise_for_status()
        return resp.json()


async def _fetch_client_from_invoice(invoice_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": invoice_data.get("client_name", ""),
        "contact_name": invoice_data.get("contact_name", ""),
        "contact_email": invoice_data.get("contact_email", ""),
        "address": invoice_data.get("address", ""),
    }


@router.get(
    "",
    summary="List all invoices",
)
async def list_invoices(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> list[dict[str, Any]]:
    """List all invoices from the bookkeeping system."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BOOKKEEPING_BASE}/api/invoices",
            headers={"X-Tenant-Key": BOOKKEEPING_TENANT_KEY},
        )
        resp.raise_for_status()
        return resp.json()


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

    invoice_data = await _fetch_invoice(invoice_id)
    client_data = await _fetch_client_from_invoice(invoice_data)

    company = DEFAULT_COMPANY.copy()
    if company_name:
        company["name"] = company_name
    if company_email:
        company["email"] = company_email

    pdf_bytes = generate_invoice_pdf(
        invoice=invoice_data,
        client=client_data,
        company=company,
        lines=invoice_data.get("lines"),
    )

    filename = f"invoice-{invoice_data.get('invoice_number') or invoice_id[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
