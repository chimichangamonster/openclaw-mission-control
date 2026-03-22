"""Document generation service — simple (reportlab) and complex (Adobe PDF Services)."""

from __future__ import annotations

import io
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates" / "documents"


def generate_simple_pdf(
    title: str,
    sections: list[dict[str, Any]],
    *,
    company: dict[str, str] | None = None,
    page_size: str = "letter",
) -> bytes:
    """Generate a simple PDF using reportlab.

    Args:
        title: Document title.
        sections: List of dicts, each with "heading" and "content" (str or list of dicts for tables).
        company: Optional company branding (name, address, email).
        page_size: "letter" or "a4".

    Returns:
        PDF bytes.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, letter
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
    ps = A4 if page_size == "a4" else letter
    doc = SimpleDocTemplate(buf, pagesize=ps, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
    styles = getSampleStyleSheet()
    elements: list[Any] = []

    title_style = ParagraphStyle(
        "DocTitle", parent=styles["Heading1"], fontSize=24,
        textColor=colors.HexColor("#1a1a2e"), spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "DocHeading", parent=styles["Heading2"], fontSize=14,
        textColor=colors.HexColor("#333333"), spaceAfter=6, spaceBefore=12,
    )
    normal_style = ParagraphStyle(
        "DocNormal", parent=styles["Normal"], fontSize=10, leading=14,
    )

    # Title
    elements.append(Paragraph(title, title_style))

    # Company branding
    if company:
        brand = company.get("name", "")
        if company.get("address"):
            brand += f" | {company['address']}"
        if company.get("email"):
            brand += f" | {company['email']}"
        elements.append(Paragraph(brand, ParagraphStyle(
            "Brand", parent=styles["Normal"], fontSize=8,
            textColor=colors.HexColor("#888888"),
        )))

    elements.append(Spacer(1, 0.3 * inch))

    # Divider
    divider = Table([[""]], colWidths=[7 * inch], rowHeights=[2])
    divider.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1a1a2e")),
    ]))
    elements.append(divider)
    elements.append(Spacer(1, 0.2 * inch))

    for section in sections:
        heading = section.get("heading", "")
        content = section.get("content", "")

        if heading:
            elements.append(Paragraph(heading, heading_style))

        if isinstance(content, str):
            # Text content — split by newlines for paragraphs
            for para in content.split("\n"):
                if para.strip():
                    elements.append(Paragraph(para.strip(), normal_style))
            elements.append(Spacer(1, 0.15 * inch))

        elif isinstance(content, list):
            # Table content — list of dicts
            if content and isinstance(content[0], dict):
                headers = list(content[0].keys())
                table_data = [headers]
                for row in content:
                    table_data.append([str(row.get(h, "")) for h in headers])

                col_width = 7 * inch / len(headers)
                t = Table(table_data, colWidths=[col_width] * len(headers))
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f8f8")]),
                    ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#dddddd")),
                ]))
                elements.append(t)
                elements.append(Spacer(1, 0.15 * inch))

    doc.build(elements)
    return buf.getvalue()


def _render_html_template(
    template_name: str,
    data: dict[str, Any],
) -> str:
    """Render a Jinja2 HTML template with the given data."""
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    template = env.get_template(f"{template_name}.html")
    return template.render(**data)


async def generate_complex_pdf_adobe(
    html_content: str,
    *,
    client_id: str,
    client_secret: str,
    page_width: float = 8.5,
    page_height: float = 11.0,
) -> bytes:
    """Generate a PDF from HTML using Adobe PDF Services API.

    Args:
        html_content: Full HTML string (with inline CSS/SVG).
        client_id: Adobe PDF Services client ID.
        client_secret: Adobe PDF Services client secret.
        page_width: Page width in inches.
        page_height: Page height in inches.

    Returns:
        PDF bytes.
    """
    from adobe.pdfservices.operation.auth.service_principal_credentials import (
        ServicePrincipalCredentials,
    )
    from adobe.pdfservices.operation.pdf_services import PDFServices
    from adobe.pdfservices.operation.pdf_services_media_type import PDFServicesMediaType
    from adobe.pdfservices.operation.pdfjobs.jobs.html_to_pdf_job import HTMLtoPDFJob
    from adobe.pdfservices.operation.pdfjobs.params.html_to_pdf.html_to_pdf_params import (
        HTMLtoPDFParams,
    )
    from adobe.pdfservices.operation.pdfjobs.params.html_to_pdf.page_layout import PageLayout
    from adobe.pdfservices.operation.pdfjobs.result.html_to_pdf_result import HTMLtoPDFResult

    credentials = ServicePrincipalCredentials(
        client_id=client_id,
        client_secret=client_secret,
    )
    pdf_services = PDFServices(credentials=credentials)

    # Adobe expects a ZIP with index.html inside
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.html", html_content)
    zip_bytes = zip_buf.getvalue()

    input_asset = pdf_services.upload(
        input_stream=zip_bytes, mime_type=PDFServicesMediaType.ZIP
    )

    page_layout = PageLayout(page_height=page_height, page_width=page_width)
    params = HTMLtoPDFParams(page_layout=page_layout, include_header_footer=True)

    job = HTMLtoPDFJob(input_asset=input_asset, html_to_pdf_params=params)
    location = pdf_services.submit(job)
    response = pdf_services.get_job_result(location, HTMLtoPDFResult)

    result_asset = response.get_result().get_asset()
    stream_asset = pdf_services.get_content(result_asset)
    return stream_asset.get_input_stream()


async def generate_complex_pdf_fallback(html_content: str) -> bytes:
    """Fallback: save HTML and return it as-is (no PDF conversion).

    When Adobe credentials are not configured, return the HTML content
    as bytes so it can be saved and served via file-serve.
    """
    return html_content.encode("utf-8")
