"""Generate professional PDF invoices from bookkeeping API data."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any


def generate_invoice_pdf(
    invoice: dict[str, Any],
    client: dict[str, Any],
    company: dict[str, str],
    lines: list[dict[str, Any]] | None = None,
) -> bytes:
    """Render an invoice as a PDF using reportlab.

    Args:
        invoice: Invoice data (subtotal, gst_amount, total, due_date, invoice_number, notes)
        client: Client data (name, contact_name, contact_email, address)
        company: Your company info (name, address, email, phone, gst_number)
        lines: Optional line items (description, quantity, unit_price, amount)

    Returns:
        PDF file bytes.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
    styles = getSampleStyleSheet()
    elements: list[Any] = []

    # Styles
    title_style = ParagraphStyle(
        "InvTitle",
        parent=styles["Heading1"],
        fontSize=28,
        textColor=colors.HexColor("#1a1a2e"),
        spaceAfter=4,
    )
    heading_style = ParagraphStyle(
        "InvHeading",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#555555"),
        spaceAfter=2,
    )
    normal_style = ParagraphStyle("InvNormal", parent=styles["Normal"], fontSize=10, leading=14)
    ParagraphStyle(
        "InvBold", parent=styles["Normal"], fontSize=10, leading=14, fontName="Helvetica-Bold"
    )  # registered in stylesheet, not referenced directly
    small_style = ParagraphStyle(
        "InvSmall",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#888888"),
        leading=11,
    )

    # Header — Company name and INVOICE label
    inv_number = invoice.get("invoice_number") or invoice.get("id", "")[:8].upper()
    header_data = [
        [
            Paragraph(company.get("name", ""), title_style),
            Paragraph(
                "INVOICE",
                ParagraphStyle(
                    "InvLabel",
                    parent=styles["Heading1"],
                    fontSize=28,
                    alignment=2,
                    textColor=colors.HexColor("#e63946"),
                ),
            ),
        ],
        [
            Paragraph(company.get("address", "").replace("\n", "<br/>"), small_style),
            Paragraph(
                f"<b>Invoice #:</b> {inv_number}",
                ParagraphStyle("Right", parent=normal_style, alignment=2),
            ),
        ],
        [
            Paragraph(f"{company.get('email', '')}  |  {company.get('phone', '')}", small_style),
            Paragraph(
                f"<b>Date:</b> {invoice.get('issued_date') or datetime.now().strftime('%B %d, %Y')}",
                ParagraphStyle("Right", parent=normal_style, alignment=2),
            ),
        ],
        [
            Paragraph(f"GST #: {company.get('gst_number', 'N/A')}", small_style),
            Paragraph(
                f"<b>Due:</b> {invoice.get('due_date', 'N/A')}",
                ParagraphStyle("Right", parent=normal_style, alignment=2),
            ),
        ],
    ]
    header_table = Table(header_data, colWidths=[3.5 * inch, 3.5 * inch])
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    elements.append(header_table)
    elements.append(Spacer(1, 0.3 * inch))

    # Divider
    divider = Table([[""]], colWidths=[7 * inch], rowHeights=[2])
    divider.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e63946")),
                ("LINEBELOW", (0, 0), (-1, -1), 0, colors.white),
            ]
        )
    )
    elements.append(divider)
    elements.append(Spacer(1, 0.2 * inch))

    # Bill To
    elements.append(Paragraph("BILL TO", heading_style))
    client_name = client.get("name", "")
    contact = client.get("contact_name", "")
    client_email = client.get("contact_email", "")
    client_address = client.get("address", "")
    bill_to = f"<b>{client_name}</b>"
    if contact:
        bill_to += f"<br/>Attn: {contact}"
    if client_email:
        bill_to += f"<br/>{client_email}"
    if client_address:
        bill_to += f"<br/>{client_address}"
    elements.append(Paragraph(bill_to, normal_style))
    elements.append(Spacer(1, 0.3 * inch))

    # Line items table
    if lines:
        table_data = [["Description", "Qty", "Unit Price", "Amount"]]
        for line in lines:
            table_data.append(
                [
                    line.get("description", ""),
                    str(line.get("quantity", "")),
                    f"${float(line.get('unit_price', 0)):,.2f}",
                    f"${float(line.get('amount', 0)):,.2f}",
                ]
            )
    else:
        # Single line item from invoice total
        table_data = [["Description", "Qty", "Unit Price", "Amount"]]
        table_data.append(
            [
                invoice.get("notes", "Professional services"),
                "1",
                f"${float(invoice.get('subtotal', 0)):,.2f}",
                f"${float(invoice.get('subtotal', 0)):,.2f}",
            ]
        )

    item_table = Table(table_data, colWidths=[3.5 * inch, 0.8 * inch, 1.2 * inch, 1.5 * inch])
    item_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("FONTSIZE", (0, 1), (-1, -1), 10),
                ("TOPPADDING", (0, 1), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#dddddd")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f8f8")]),
            ]
        )
    )
    elements.append(item_table)
    elements.append(Spacer(1, 0.2 * inch))

    # Totals
    subtotal = float(invoice.get("subtotal", 0))
    gst = float(invoice.get("gst_amount", 0))
    total = float(invoice.get("total", 0))

    totals_data = [
        ["", "Subtotal:", f"${subtotal:,.2f}"],
        ["", "GST (5%):", f"${gst:,.2f}"],
        ["", "TOTAL:", f"${total:,.2f}"],
    ]
    totals_table = Table(totals_data, colWidths=[3.5 * inch, 2 * inch, 1.5 * inch])
    totals_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("FONTNAME", (1, 2), (-1, 2), "Helvetica-Bold"),
                ("FONTSIZE", (1, 2), (-1, 2), 12),
                ("LINEABOVE", (1, 2), (-1, 2), 1, colors.HexColor("#1a1a2e")),
                ("TOPPADDING", (1, 2), (-1, 2), 8),
                ("TEXTCOLOR", (1, 2), (-1, 2), colors.HexColor("#e63946")),
            ]
        )
    )
    elements.append(totals_table)
    elements.append(Spacer(1, 0.5 * inch))

    # Notes / Payment terms
    if invoice.get("notes"):
        elements.append(Paragraph("NOTES", heading_style))
        elements.append(Paragraph(invoice["notes"], normal_style))
        elements.append(Spacer(1, 0.2 * inch))

    elements.append(Paragraph("PAYMENT TERMS", heading_style))
    elements.append(
        Paragraph(
            "Payment is due within 30 days of invoice date. Please include the invoice number with your payment.",
            normal_style,
        )
    )
    elements.append(Spacer(1, 0.3 * inch))

    # Footer
    elements.append(
        Paragraph(
            "Thank you for your business!",
            ParagraphStyle(
                "Thanks",
                parent=styles["Normal"],
                fontSize=11,
                fontName="Helvetica-Oblique",
                textColor=colors.HexColor("#555555"),
                alignment=1,
            ),
        )
    )

    doc.build(elements)
    return buf.getvalue()
