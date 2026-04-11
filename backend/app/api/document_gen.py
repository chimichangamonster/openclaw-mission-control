"""Document generation API — simple (reportlab) and complex (Adobe PDF Services).

Includes a two-phase redaction workflow for security assessment reports:
  1. POST /documents/redact-for-review — redact sensitive data, return for human review
  2. POST /documents/generate/complex-with-rehydration — generate after approval, rehydrate placeholders
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import col, select

from app.core.config import settings
from app.core.encryption import decrypt_token
from app.core.file_tokens import create_file_token
from app.core.logging import get_logger
from app.core.redact import RedactionVault
from app.db.session import async_session_maker
from app.models.generated_documents import GeneratedDocument
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
    org_id: str | None = Field(
        default=None, description="Organization ID — auto-resolves logo and accent color"
    )


class ComplexDocRequest(BaseModel):
    template: str | None = Field(
        default=None, description="Template name: proposal, report, or None for raw HTML"
    )
    template_data: dict[str, Any] = Field(
        default_factory=dict, description="Data for template rendering"
    )
    html: str | None = Field(
        default=None, description="Raw HTML content (used when template is None)"
    )
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


async def _get_adobe_credentials(org_id: UUID) -> tuple[str, str] | None:
    """Retrieve Adobe PDF Services credentials for the org, falling back to platform env."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        org_settings = result.scalars().first()

    # Try org BYOK first
    if (
        org_settings
        and org_settings.adobe_pdf_client_id_encrypted
        and org_settings.adobe_pdf_client_secret_encrypted
    ):
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


async def _resolve_org_branding(org_id_str: str | None) -> dict[str, str | None]:
    """Resolve logo absolute path and accent color from org settings.

    Returns dict with keys: logo_path, accent_color, company_name.
    All values may be None if org not found or no branding configured.
    """
    if not org_id_str:
        return {"logo_path": None, "accent_color": None, "company_name": None}

    try:
        from uuid import UUID

        from sqlmodel import select as sel

        from app.models.organizations import Organization

        oid = UUID(org_id_str)
    except (ValueError, TypeError):
        logger.warning("document_gen.invalid_org_id org_id=%s", org_id_str)
        return {"logo_path": None, "accent_color": None, "company_name": None}

    async with async_session_maker() as session:
        # Get org settings for branding
        result = await session.execute(
            sel(OrganizationSettings).where(OrganizationSettings.organization_id == oid)
        )
        org_settings = result.scalars().first()

        # Get org name
        org_result = await session.execute(sel(Organization).where(Organization.id == oid))
        org = org_result.scalars().first()

    branding = org_settings.branding if org_settings else {}
    logo_rel = branding.get("logo_path")
    accent = branding.get("primary_color")
    company_name = org.name if org else None

    # Resolve logo relative path to absolute
    logo_abs = None
    if logo_rel:
        workspace = settings.gateway_workspaces_root or settings.gateway_workspace_path
        if workspace:
            candidate = Path(workspace) / logo_rel
            if candidate.exists():
                logo_abs = str(candidate)
            else:
                logger.info("document_gen.logo_file_missing path=%s", candidate)

    return {
        "logo_path": logo_abs,
        "accent_color": accent,
        "company_name": company_name,
    }


def _save_to_workspace(content: bytes, filename: str, extension: str) -> str:
    """Save generated content to the gateway workspaces root and return relative path."""
    workspace = settings.gateway_workspaces_root or settings.gateway_workspace_path
    if not workspace:
        raise HTTPException(
            status_code=503,
            detail="GATEWAY_WORKSPACES_ROOT not configured.",
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
            stmt = (
                select(MicrosoftConnection)
                .where(
                    col(MicrosoftConnection.is_active).is_(True),
                )
                .limit(1)
            )
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


async def _persist_document(
    *,
    filename: str,
    relative_path: str,
    file_size: int,
    mime_type: str,
    doc_type: str,
    mode: str,
    engine: str,
    title: str,
    onedrive_url: str | None = None,
    onedrive_edit_url: str | None = None,
) -> None:
    """Save a GeneratedDocument record to the database."""
    try:
        async with async_session_maker() as session:
            doc = GeneratedDocument(
                filename=filename,
                relative_path=relative_path,
                file_size=file_size,
                mime_type=mime_type,
                doc_type=doc_type,
                mode=mode,
                engine=engine,
                title=title,
                onedrive_url=onedrive_url,
                onedrive_edit_url=onedrive_edit_url,
            )
            session.add(doc)
            await session.commit()
    except Exception as exc:
        logger.warning("document_gen.persist_failed error=%s", exc)


def _infer_doc_type(template: str | None, title: str) -> str:
    """Infer document type from template name or title keywords."""
    if template:
        mapping = {
            "proposal": "proposal",
            "report": "report",
            "security-assessment": "security-assessment",
            "rules-of-engagement": "rules-of-engagement",
        }
        for key, dtype in mapping.items():
            if key in template:
                return dtype
    lower = title.lower()
    if "invoice" in lower:
        return "invoice"
    if "proposal" in lower or "sow" in lower:
        return "proposal"
    if "report" in lower:
        return "report"
    return "other"


@router.post(
    "/generate/simple",
    summary="Generate a simple PDF document",
    response_model=DocumentResponse,
)
async def generate_simple(
    body: SimpleDocRequest,
    token: str = Query(..., description="Auth token"),
) -> Any:
    """Generate a simple PDF using reportlab (tables, text, basic formatting).

    When ``org_id`` is provided in the request body, the endpoint auto-resolves
    the organization's logo and accent color from branding settings so agents
    don't need to pass them manually.
    """
    if token != settings.local_auth_token:
        raise HTTPException(status_code=401, detail="Invalid token")

    from app.services.document_gen import generate_simple_pdf

    # Auto-resolve branding when org_id is provided
    branding = await _resolve_org_branding(body.org_id)
    logo_path = branding["logo_path"]
    accent_color = branding["accent_color"] or "#1a1a2e"

    # Merge org name into company dict if not already provided
    company = body.company or {}
    if branding["company_name"] and not company.get("name"):
        company["name"] = branding["company_name"]

    sections = [s.model_dump() for s in body.sections]
    pdf_bytes = generate_simple_pdf(
        title=body.title,
        sections=sections,
        company=company or None,
        page_size=body.page_size,
        logo_path=logo_path,
        accent_color=accent_color,
    )

    relative_path = _save_to_workspace(pdf_bytes, body.filename, ".pdf")
    file_token = create_file_token(relative_path, expires_hours=48)
    download_url = f"{settings.base_url}/api/v1/files/download?token={file_token}"

    # Try OneDrive upload
    od = await _try_onedrive_upload(pdf_bytes, Path(relative_path).name, "application/pdf")

    actual_filename = Path(relative_path).name
    logger.info("document_gen.simple filename=%s size=%d", body.filename, len(pdf_bytes))

    await _persist_document(
        filename=actual_filename,
        relative_path=relative_path,
        file_size=len(pdf_bytes),
        mime_type="application/pdf",
        doc_type=_infer_doc_type(None, body.title),
        mode="simple",
        engine="reportlab",
        title=body.title,
        onedrive_url=od.get("onedrive_url"),
        onedrive_edit_url=od.get("onedrive_edit_url"),
    )

    return DocumentResponse(
        url=download_url,
        filename=actual_filename,
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
) -> Any:
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

    actual_filename = Path(relative_path).name
    mime = "application/pdf" if extension == ".pdf" else "text/html"
    logger.info(
        "document_gen.complex filename=%s engine=%s size=%d",
        body.filename,
        engine,
        len(pdf_bytes),
    )

    title = body.template_data.get("title", "") or body.template or body.filename
    await _persist_document(
        filename=actual_filename,
        relative_path=relative_path,
        file_size=len(pdf_bytes),
        mime_type=mime,
        doc_type=_infer_doc_type(body.template, str(title)),
        mode="complex",
        engine=engine,
        title=str(title),
        onedrive_url=od.get("onedrive_url"),
        onedrive_edit_url=od.get("onedrive_edit_url"),
    )

    return DocumentResponse(
        url=download_url,
        filename=actual_filename,
        mode="complex",
        engine=engine,
        onedrive_url=od["onedrive_url"],
        onedrive_edit_url=od["onedrive_edit_url"],
    )


# ---------------------------------------------------------------------------
# Redact-Review-Rehydrate workflow for security assessment reports
# ---------------------------------------------------------------------------


class RedactForReviewRequest(BaseModel):
    """Raw pentest data to be redacted before human review."""

    template_data: dict[str, Any] = Field(
        ..., description="Template variables containing raw pentest findings data"
    )


class RedactedEntry(BaseModel):
    tag: str
    original: str
    label: str


class RedactForReviewResponse(BaseModel):
    """Redacted data for human review before sending to LLM."""

    redacted_template_data: dict[str, Any]
    vault: dict[str, Any]
    redacted_entries: list[RedactedEntry]
    entry_count: int


class GenerateWithRehydrationRequest(BaseModel):
    """Generate report from LLM output, rehydrating redacted placeholders."""

    template: str = Field(default="security-assessment", description="Template name")
    template_data: dict[str, Any] = Field(
        ..., description="Template data (may contain LLM-generated text with placeholders)"
    )
    vault: dict[str, Any] = Field(..., description="Vault from redact-for-review response")
    filename: str = Field(default="security-assessment.pdf")
    page_width: float = Field(default=8.5)
    page_height: float = Field(default=11.0)


def _redact_recursive(obj: Any, vault: RedactionVault) -> Any:
    """Recursively redact string values in nested dicts/lists."""
    if isinstance(obj, str):
        return vault.redact(obj)
    if isinstance(obj, dict):
        return {k: _redact_recursive(v, vault) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_recursive(item, vault) for item in obj]
    return obj


def _rehydrate_recursive(obj: Any, vault: RedactionVault) -> Any:
    """Recursively rehydrate placeholder tags in nested dicts/lists."""
    if isinstance(obj, str):
        return vault.rehydrate(obj)
    if isinstance(obj, dict):
        return {k: _rehydrate_recursive(v, vault) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_rehydrate_recursive(item, vault) for item in obj]
    return obj


@router.post(
    "/redact-for-review",
    summary="Redact pentest data for human review before LLM processing",
    response_model=RedactForReviewResponse,
)
async def redact_for_review(
    body: RedactForReviewRequest,
    token: str = Query(..., description="Auth token"),
) -> Any:
    """Phase 1: Redact sensitive data (IPs, hostnames, credentials, paths) from
    raw pentest findings. Returns the redacted data and a vault for the user to
    review. Nothing is sent to any LLM at this stage.

    The user must review the redacted_entries list to confirm no sensitive data
    remains before proceeding to report generation.
    """
    if token != settings.local_auth_token:
        raise HTTPException(status_code=401, detail="Invalid token")

    vault = RedactionVault()
    redacted_data = _redact_recursive(body.template_data, vault)

    logger.info(
        "document_gen.redact_for_review entries=%d",
        vault.entry_count,
    )

    return RedactForReviewResponse(
        redacted_template_data=redacted_data,
        vault=vault.to_dict(),
        redacted_entries=[RedactedEntry(**e) for e in vault.entries],
        entry_count=vault.entry_count,
    )


@router.post(
    "/generate/complex-with-rehydration",
    summary="Generate report with rehydration of redacted placeholders",
    response_model=DocumentResponse,
)
async def generate_complex_with_rehydration(
    body: GenerateWithRehydrationRequest,
    token: str = Query(..., description="Auth token"),
) -> Any:
    """Phase 2: After the user has reviewed and approved the redacted data,
    generate the final report. Template data (which may contain LLM-generated
    text with placeholder tags) is rehydrated with original values from the
    vault before rendering to PDF.

    Flow: redacted data → user approves → LLM generates text with placeholders
    → this endpoint rehydrates → renders final PDF with real data.
    """
    if token != settings.local_auth_token:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Reconstruct vault and rehydrate
    vault = RedactionVault.from_dict(body.vault)
    rehydrated_data = _rehydrate_recursive(body.template_data, vault)

    logger.info(
        "document_gen.rehydrate entries=%d",
        vault.entry_count,
    )

    # Render template with rehydrated data
    from app.services.document_gen import _render_html_template

    try:
        html_content = _render_html_template(body.template, rehydrated_data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Template rendering failed: {exc}")

    # Generate PDF (same logic as generate_complex)
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
            pdf_bytes = html_content.encode("utf-8")
            engine = "html_fallback"
            extension = ".html"
    else:
        pdf_bytes = html_content.encode("utf-8")
        engine = "html_fallback"
        extension = ".html"

    relative_path = _save_to_workspace(pdf_bytes, body.filename, extension)
    file_token = create_file_token(relative_path, expires_hours=48)
    download_url = f"{settings.base_url}/api/v1/files/download?token={file_token}"

    od = await _try_onedrive_upload(
        pdf_bytes,
        Path(relative_path).name,
        "application/pdf" if extension == ".pdf" else "text/html",
    )

    actual_filename = Path(relative_path).name
    mime = "application/pdf" if extension == ".pdf" else "text/html"
    logger.info(
        "document_gen.complex_rehydrated filename=%s engine=%s entries_rehydrated=%d",
        body.filename,
        engine,
        vault.entry_count,
    )

    title = rehydrated_data.get("title", "") or body.template or body.filename
    await _persist_document(
        filename=actual_filename,
        relative_path=relative_path,
        file_size=len(pdf_bytes),
        mime_type=mime,
        doc_type=_infer_doc_type(body.template, str(title)),
        mode="complex_rehydrated",
        engine=engine,
        title=str(title),
        onedrive_url=od.get("onedrive_url"),
        onedrive_edit_url=od.get("onedrive_edit_url"),
    )

    return DocumentResponse(
        url=download_url,
        filename=actual_filename,
        mode="complex_rehydrated",
        engine=engine,
        onedrive_url=od["onedrive_url"],
        onedrive_edit_url=od["onedrive_edit_url"],
    )


# ---------------------------------------------------------------------------
# Generated documents listing & management
# ---------------------------------------------------------------------------

from app.api.deps import require_org_member
from app.db.session import get_session
from app.services.organizations import OrganizationContext

_ORG_DEP = Depends(require_org_member)
_SESSION_DEP = Depends(get_session)


class GeneratedDocumentRead(BaseModel):
    id: str
    filename: str
    title: str
    doc_type: str
    mode: str
    engine: str
    file_size: int
    mime_type: str
    download_url: str
    onedrive_url: str | None = None
    onedrive_edit_url: str | None = None
    created_at: str


@router.get(
    "/generated",
    summary="List generated documents",
    response_model=list[GeneratedDocumentRead],
)
async def list_generated_documents(
    doc_type: str | None = Query(default=None, description="Filter by doc_type"),
    ctx: OrganizationContext = _ORG_DEP,
    session: Any = _SESSION_DEP,
) -> Any:
    """List all tracked generated documents for the current organization."""
    from sqlmodel.ext.asyncio.session import AsyncSession

    session: AsyncSession  # type: ignore[no-redef]

    stmt = (
        select(GeneratedDocument)
        .where(
            (GeneratedDocument.organization_id == ctx.organization.id)
            | (col(GeneratedDocument.organization_id).is_(None))
        )
        .order_by(col(GeneratedDocument.created_at).desc())
    )

    if doc_type:
        stmt = stmt.where(GeneratedDocument.doc_type == doc_type)

    result = await session.execute(stmt)
    docs = result.scalars().all()

    items = []
    for doc in docs:
        # Generate a fresh download token for each document
        try:
            file_token = create_file_token(doc.relative_path, expires_hours=48)
            download_url = f"{settings.base_url}/api/v1/files/download?token={file_token}"
        except Exception:
            download_url = ""

        items.append(
            GeneratedDocumentRead(
                id=str(doc.id),
                filename=doc.filename,
                title=doc.title,
                doc_type=doc.doc_type,
                mode=doc.mode,
                engine=doc.engine,
                file_size=doc.file_size,
                mime_type=doc.mime_type,
                download_url=download_url,
                onedrive_url=doc.onedrive_url,
                onedrive_edit_url=doc.onedrive_edit_url,
                created_at=doc.created_at.isoformat(),
            )
        )
    return items


@router.delete(
    "/generated/{doc_id}",
    summary="Delete a generated document record",
    status_code=204,
)
async def delete_generated_document(
    doc_id: UUID,
    ctx: OrganizationContext = _ORG_DEP,
    session: Any = _SESSION_DEP,
) -> None:
    """Delete a generated document record (and optionally the file on disk)."""
    from sqlmodel.ext.asyncio.session import AsyncSession

    session: AsyncSession  # type: ignore[no-redef]

    stmt = select(GeneratedDocument).where(GeneratedDocument.id == doc_id)
    result = await session.execute(stmt)
    doc = result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Try to delete file from disk
    workspace = settings.gateway_workspaces_root or settings.gateway_workspace_path
    if workspace:
        file_path = Path(workspace) / doc.relative_path
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as exc:
                logger.warning("document_gen.delete_file_failed path=%s error=%s", file_path, exc)

    await session.delete(doc)
    await session.commit()
