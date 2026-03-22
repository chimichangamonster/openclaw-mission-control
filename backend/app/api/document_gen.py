"""Document generation API — simple (reportlab) and complex (Adobe PDF Services)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import select

from app.core.config import settings
from app.core.encryption import decrypt_token
from app.core.file_tokens import create_file_token
from app.core.logging import get_logger
from app.db.session import async_session_maker
from app.models.organization_settings import OrganizationSettings

logger = get_logger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)


class DocumentSection(BaseModel):
    heading: str = ""
    content: Any = ""  # str for text, list[dict] for tables
    page_break: bool = False


class SimpleDocRequest(BaseModel):
    title: str
    sections: list[DocumentSection]
    company: dict[str, str] | None = None
    filename: str = Field(default="document.pdf", description="Output filename")
    page_size: str = Field(default="letter", pattern="^(letter|a4)$")


class ComplexDocRequest(BaseModel):
    template: str | None = Field(default=None, description="Template name: proposal, report, or None for raw HTML")
    template_data: dict[str, Any] = Field(default_factory=dict, description="Data for template rendering")
    html: str | None = Field(default=None, description="Raw HTML content (used when template is None)")
    filename: str = Field(default="document.pdf", description="Output filename")
    page_width: float = Field(default=8.5, description="Page width in inches")
    page_height: float = Field(default=11.0, description="Page height in inches")


class DocumentResponse(BaseModel):
    url: str
    filename: str
    mode: str
    engine: str
    onedrive_url: str | None = None
    onedrive_edit_url: str | None = None


async def _get_adobe_credentials(org_id) -> tuple[str, str] | None:
    """Retrieve Adobe PDF Services credentials for the org, falling back to platform env."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(
                OrganizationSettings.organization_id == org_id
            )
        )
        org_settings = result.scalars().first()

    # Try org BYOK first
    if org_settings and org_settings.adobe_pdf_client_id_encrypted and org_settings.adobe_pdf_client_secret_encrypted:
        try:
            client_id = decrypt_token(org_settings.adobe_pdf_client_id_encrypted)
            client_secret = decrypt_token(org_settings.adobe_pdf_client_secret_encrypted)
            return (client_id, client_secret)
        except Exception:
            logger.warning("document_gen.adobe_decrypt_failed org_id=%s", org_id)

    # Fall back to platform-level env vars
    env_id = settings.adobe_pdf_client_id
    env_secret = settings.adobe_pdf_client_secret
    if env_id and env_secret:
        return (env_id, env_secret)

    return None


def _save_to_workspace(content: bytes, filename: str, extension: str) -> str:
    """Save generated content to the gateway workspace and return relative path."""
    workspace = settings.gateway_workspace_path
    if not workspace:
        raise HTTPException(
            status_code=503,
            detail="GATEWAY_WORKSPACE_PATH not configured.",
        )

    docs_dir = Path(workspace) / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Unique filename to avoid collisions
    stem = Path(filename).stem
    unique_name = f"{stem}-{uuid4().hex[:8]}{extension}"
    output_path = docs_dir / unique_name
    output_path.write_bytes(content)

    # Return path relative to workspace root
    return f"documents/{unique_name}"


async def _try_onedrive_upload(
    content: bytes,
    filename: str,
    content_type: str,
) -> dict[str, str | None]:
    """Attempt to upload to OneDrive if a connection exists. Non-blocking."""
    try:
        from sqlmodel import col, select

        from app.db.session import async_session_maker
        from app.models.microsoft_connection import MicrosoftConnection
        from app.services.microsoft.onedrive import create_sharing_link, upload_file
        from app.services.microsoft.token_manager import get_valid_graph_token

        async with async_session_maker() as session:
            stmt = select(MicrosoftConnection).where(
                col(MicrosoftConnection.is_active).is_(True),
            ).limit(1)
            conn = (await session.execute(stmt)).scalar_one_or_none()
            if not conn:
                return {"onedrive_url": None, "onedrive_edit_url": None}

            token = await get_valid_graph_token(session, conn)
            await session.commit()

        folder = conn.default_folder or "/OpenClaw"
        item = await upload_file(token, f"{folder}/Documents", filename, content, content_type)

        share_url = None
        edit_url = item.get("webUrl")
        if item.get("id"):
            share_url = await create_sharing_link(token, item["id"], scope="organization")

        logger.info("document_gen.onedrive_uploaded name=%s id=%s", filename, item.get("id"))
        return {"onedrive_url": share_url, "onedrive_edit_url": edit_url}
    except Exception as exc:
        logger.warning("document_gen.onedrive_upload_failed error=%s", exc)
        return {"onedrive_url": None, "onedrive_edit_url": None}


@router.post(
    "/generate/simple",
    summary="Generate a simple PDF document",
    response_model=DocumentResponse,
)
async def generate_simple(
    body: SimpleDocRequest,
    token: str = Query(..., description="Auth token"),
):
    """Generate a simple PDF using reportlab (tables, text, basic formatting)."""
    if token != settings.local_auth_token:
        raise HTTPException(status_code=401, detail="Invalid token")

    from app.services.document_gen import generate_simple_pdf

    sections = [s.model_dump() for s in body.sections]
    pdf_bytes = generate_simple_pdf(
        title=body.title,
        sections=sections,
        company=body.company,
        page_size=body.page_size,
    )

    relative_path = _save_to_workspace(pdf_bytes, body.filename, ".pdf")
    file_token = create_file_token(relative_path, expires_hours=48)
    download_url = f"{settings.base_url}/api/v1/files/download?token={file_token}"

    # Try OneDrive upload
    od = await _try_onedrive_upload(pdf_bytes, Path(relative_path).name, "application/pdf")

    logger.info("document_gen.simple filename=%s size=%d", body.filename, len(pdf_bytes))
    return DocumentResponse(
        url=download_url,
        filename=Path(relative_path).name,
        mode="simple",
        engine="reportlab",
        onedrive_url=od["onedrive_url"],
        onedrive_edit_url=od["onedrive_edit_url"],
    )


@router.post(
    "/generate/complex",
    summary="Generate a complex PDF document",
    response_model=DocumentResponse,
)
async def generate_complex(
    body: ComplexDocRequest,
    token: str = Query(..., description="Auth token"),
):
    """Generate a complex PDF using Adobe PDF Services (styled HTML, charts, multi-page)."""
    if token != settings.local_auth_token:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Resolve HTML content
    if body.template:
        from app.services.document_gen import _render_html_template
        try:
            html_content = _render_html_template(body.template, body.template_data)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Template rendering failed: {exc}")
    elif body.html:
        html_content = body.html
    else:
        raise HTTPException(status_code=400, detail="Either 'template' or 'html' must be provided.")

    # Try Adobe PDF Services
    # Pass a dummy org_id for now — platform-level keys from env
    adobe_creds = await _get_adobe_credentials(org_id=None)

    if adobe_creds:
        from app.services.document_gen import generate_complex_pdf_adobe

        try:
            pdf_bytes = await generate_complex_pdf_adobe(
                html_content,
                client_id=adobe_creds[0],
                client_secret=adobe_creds[1],
                page_width=body.page_width,
                page_height=body.page_height,
            )
            engine = "adobe_pdf_services"
            extension = ".pdf"
        except Exception as exc:
            logger.warning("document_gen.adobe_failed error=%s", exc)
            # Fall back to HTML
            pdf_bytes = html_content.encode("utf-8")
            engine = "html_fallback"
            extension = ".html"
    else:
        # No Adobe credentials — save as HTML for browser-based PDF conversion
        pdf_bytes = html_content.encode("utf-8")
        engine = "html_fallback"
        extension = ".html"

    relative_path = _save_to_workspace(pdf_bytes, body.filename, extension)
    file_token = create_file_token(relative_path, expires_hours=48)
    download_url = f"{settings.base_url}/api/v1/files/download?token={file_token}"

    # Try OneDrive upload
    mime = "application/pdf" if extension == ".pdf" else "text/html"
    od = await _try_onedrive_upload(pdf_bytes, Path(relative_path).name, mime)

    logger.info(
        "document_gen.complex filename=%s engine=%s size=%d",
        body.filename, engine, len(pdf_bytes),
    )
    return DocumentResponse(
        url=download_url,
        filename=Path(relative_path).name,
        mode="complex",
        engine=engine,
        onedrive_url=od["onedrive_url"],
        onedrive_edit_url=od["onedrive_edit_url"],
    )
