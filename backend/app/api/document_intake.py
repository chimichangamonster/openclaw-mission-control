"""Document intake API — upload, extract text, classify."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.deps import ORG_ACTOR_DEP
from app.core.logging import get_logger
from app.db.session import async_session_maker
from app.services.document_intake import process_document
from app.services.organizations import OrganizationContext

logger = get_logger(__name__)

router = APIRouter(prefix="/document-intake", tags=["document-intake"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
ALLOWED_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "text/plain",
    "text/csv",
    "text/markdown",
    "application/json",
}


@router.post("/process")
async def intake_document(
    file: UploadFile = File(...),
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> Any:
    """Upload a document for text extraction and classification."""
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported file type: {content_type}")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            400, f"File too large ({len(file_bytes) / 1024 / 1024:.1f} MB, max 20 MB)"
        )

    org_id = org_ctx.organization.id
    async with async_session_maker() as session:
        result = await process_document(
            file_bytes=file_bytes,
            filename=file.filename or "unknown",
            content_type=content_type,
            org_id=org_id,
            db_session=session,
        )
    return result


@router.post("/agent/process")
async def agent_intake_document(
    file: UploadFile = File(...),
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> Any:
    """Agent-accessible document intake — same as user endpoint."""
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported file type: {content_type}")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            400, f"File too large ({len(file_bytes) / 1024 / 1024:.1f} MB, max 20 MB)"
        )

    org_id = org_ctx.organization.id
    async with async_session_maker() as session:
        return await process_document(
            file_bytes=file_bytes,
            filename=file.filename or "unknown",
            content_type=content_type,
            org_id=org_id,
            db_session=session,
        )
