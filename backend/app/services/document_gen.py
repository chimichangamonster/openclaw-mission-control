"""Document generation service — simple (reportlab) and complex (Adobe PDF Services)."""

from __future__ import annotations

import io
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
    logo_path: str | None = None,
    accent_color: str = "#1a1a2e",
    generated_date: str | None = None,
) -> bytes:
    """Generate a branded PDF using reportlab.

    Args:
        title: Document title.
        sections: List of dicts, each with "heading" and "content" (str or list of dicts for tables).
        company: Optional company branding (name, address, email).
        page_size: "letter" or "a4".
        logo_path: Absolute path to org logo file (PNG/JPG/SVG). SVG is skipped.
        accent_color: Hex color for header bar, headings, table headers. Defaults to dark blue.
        generated_date: Date string for the header. Auto-generated if not provided.

    Returns:
        PDF bytes.
    """
    from datetime import datetime, timezone

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

    accent = colors.HexColor(accent_color)
    accent_light = colors.HexColor(_lighten_hex(accent_color, 0.95))
    date_str = generated_date or datetime.now(timezone.utc).strftime("%B %d, %Y")

    buf = io.BytesIO()
    ps = A4 if page_size == "a4" else letter
    page_width = ps[0]
    content_width = page_width - 1.0 * inch  # 0.5in margins each side

    # Store branding info for header/footer callbacks
    doc_meta = {
        "accent": accent,
        "company_name": (company or {}).get("name", ""),
        "title": title,
    }

    doc = SimpleDocTemplate(
        buf,
        pagesize=ps,
        topMargin=0.8 * inch,
        bottomMargin=0.7 * inch,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    elements: list[Any] = []

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=accent,
        spaceAfter=4,
        fontName="Helvetica-Bold",
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#666666"),
        spaceAfter=2,
    )
    heading_style = ParagraphStyle(
        "DocHeading",
        parent=styles["Heading2"],
        fontSize=13,
        textColor=accent,
        spaceAfter=6,
        spaceBefore=16,
        fontName="Helvetica-Bold",
        borderPadding=(0, 0, 2, 0),  # type: ignore[arg-type]
    )
    normal_style = ParagraphStyle(
        "DocNormal",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
    )

    # --- Header block: logo + title + company info ---
    logo_img = _load_logo_image(logo_path, max_height=0.5 * inch)

    if logo_img:
        # Two-column header: logo left, title+company right
        company_lines = _format_company_lines(company)
        right_content = [Paragraph(title, title_style)]
        if company_lines:
            right_content.append(Paragraph(company_lines, subtitle_style))
        right_content.append(Paragraph(date_str, subtitle_style))

        header_table = Table(
            [[logo_img, right_content]],
            colWidths=[logo_img.drawWidth + 12, content_width - logo_img.drawWidth - 12],
        )
        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        elements.append(header_table)
    else:
        # No logo — title + company text
        elements.append(Paragraph(title, title_style))
        company_lines = _format_company_lines(company)
        if company_lines:
            elements.append(Paragraph(company_lines, subtitle_style))
        elements.append(Paragraph(date_str, subtitle_style))

    elements.append(Spacer(1, 0.15 * inch))

    # Accent divider bar
    divider = Table([[""]], colWidths=[content_width], rowHeights=[3])
    divider.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), accent),
                ("LINEBELOW", (0, 0), (-1, -1), 0, accent),
            ]
        )
    )
    elements.append(divider)
    elements.append(Spacer(1, 0.2 * inch))

    # --- Sections ---
    for section in sections:
        heading = section.get("heading", "")
        content = section.get("content", "")

        if heading:
            # Heading with left accent bar
            heading_with_bar = Table(
                [[Paragraph(heading, heading_style)]],
                colWidths=[content_width],
            )
            heading_with_bar.setStyle(
                TableStyle(
                    [
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("LINEBEFOREDECOR", (0, 0), (0, -1), 3, accent),
                    ]
                )
            )
            elements.append(heading_with_bar)

        if isinstance(content, str):
            for para in content.split("\n"):
                if para.strip():
                    elements.append(Paragraph(para.strip(), normal_style))
            elements.append(Spacer(1, 0.12 * inch))

        elif isinstance(content, list):
            if content and isinstance(content[0], dict):
                headers = list(content[0].keys())
                table_data = [headers]
                for row in content:
                    table_data.append([str(row.get(h, "")) for h in headers])

                col_width = content_width / len(headers)
                t = Table(table_data, colWidths=[col_width] * len(headers))
                t.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), accent),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, -1), 9),
                            ("TOPPADDING", (0, 0), (-1, -1), 6),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, accent_light]),
                            ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#dddddd")),
                            ("LINEBELOW", (0, -1), (-1, -1), 1, accent),
                        ]
                    )
                )
                elements.append(t)
                elements.append(Spacer(1, 0.12 * inch))

    def _draw_footer(canvas_obj: Any, doc_obj: Any) -> None:
        """Draw page number footer on every page."""
        canvas_obj.saveState()
        # Footer line
        canvas_obj.setStrokeColor(colors.HexColor("#dddddd"))
        canvas_obj.setLineWidth(0.5)
        y_line = 0.5 * inch
        canvas_obj.line(0.5 * inch, y_line, page_width - 0.5 * inch, y_line)
        # Page number right
        canvas_obj.setFont("Helvetica", 8)
        canvas_obj.setFillColor(colors.HexColor("#999999"))
        page_num = f"Page {doc_obj.page}"
        canvas_obj.drawRightString(page_width - 0.5 * inch, 0.35 * inch, page_num)
        # Company name left
        name = doc_meta.get("company_name", "")
        if name:
            canvas_obj.drawString(0.5 * inch, 0.35 * inch, name)
        canvas_obj.restoreState()

    doc.build(elements, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buf.getvalue()


def _load_logo_image(
    logo_path: str | None,
    max_height: float = 36,
) -> Any | None:
    """Load a logo image for reportlab. Returns an Image flowable or None."""
    if not logo_path:
        return None

    from pathlib import Path

    from reportlab.platypus import Image

    p = Path(logo_path)
    if not p.exists():
        logger.warning("document_gen.logo_not_found path=%s", logo_path)
        return None

    # Skip SVG — reportlab can't render it natively
    if p.suffix.lower() == ".svg":
        logger.info("document_gen.logo_svg_skipped path=%s", logo_path)
        return None

    try:
        img = Image(str(p))
        # Scale to max_height, preserving aspect ratio
        aspect = img.imageWidth / img.imageHeight if img.imageHeight else 1
        img.drawHeight = max_height
        img.drawWidth = max_height * aspect
        # Cap width so it doesn't dominate the header
        max_width = max_height * 4
        if img.drawWidth > max_width:
            img.drawWidth = max_width
            img.drawHeight = max_width / aspect
        return img
    except Exception as exc:
        logger.warning("document_gen.logo_load_failed path=%s error=%s", logo_path, exc)
        return None


def _format_company_lines(company: dict[str, str] | None) -> str:
    """Format company branding dict into a single display line."""
    if not company:
        return ""
    parts = []
    if company.get("name"):
        parts.append(company["name"])
    if company.get("address"):
        parts.append(company["address"])
    if company.get("email"):
        parts.append(company["email"])
    return " | ".join(parts)


def _lighten_hex(hex_color: str, factor: float = 0.95) -> str:
    """Lighten a hex color toward white. factor=0.95 gives a very light tint."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


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

    input_asset = pdf_services.upload(input_stream=zip_bytes, mime_type=PDFServicesMediaType.ZIP)

    page_layout = PageLayout(page_height=page_height, page_width=page_width)
    params = HTMLtoPDFParams(page_layout=page_layout, include_header_footer=True)

    job = HTMLtoPDFJob(input_asset=input_asset, html_to_pdf_params=params)
    location = pdf_services.submit(job)
    response = pdf_services.get_job_result(location, HTMLtoPDFResult)

    result_asset = response.get_result().get_asset()
    stream_asset = pdf_services.get_content(result_asset)
    return stream_asset.get_input_stream()  # type: ignore[no-any-return]


async def generate_complex_pdf_fallback(html_content: str) -> bytes:
    """Fallback: save HTML and return it as-is (no PDF conversion).

    When Adobe credentials are not configured, return the HTML content
    as bytes so it can be saved and served via file-serve.
    """
    return html_content.encode("utf-8")
