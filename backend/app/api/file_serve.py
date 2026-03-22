"""File serving — temporary signed download links for gateway workspace files."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.file_tokens import create_file_token, verify_file_token
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/files", tags=["files"])

_MIME_MAP: dict[str, str] = {
    ".html": "text/html",
    ".htm": "text/html",
    ".pdf": "application/pdf",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".txt": "text/plain",
    ".xml": "application/xml",
}

_INLINE_TYPES = {
    "text/html",
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/svg+xml",
    "text/plain",
}

_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


def _get_workspace_root() -> Path:
    wp = settings.gateway_workspace_path
    if not wp:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File serving not configured (GATEWAY_WORKSPACE_PATH not set).",
        )
    return Path(wp)


def _resolve_safe_path(workspace_root: Path, relative_path: str) -> Path:
    """Resolve a relative path within the workspace, blocking traversal attacks."""
    # Normalize to forward slashes and reject absolute paths
    cleaned = PurePosixPath(relative_path)
    if cleaned.is_absolute():
        raise HTTPException(status_code=400, detail="Absolute paths not allowed.")

    resolved = (workspace_root / relative_path).resolve()
    workspace_resolved = workspace_root.resolve()

    if not str(resolved).startswith(str(workspace_resolved)):
        logger.warning("file_serve.path_traversal_blocked path=%s", relative_path)
        raise HTTPException(status_code=403, detail="Path outside workspace.")

    return resolved


class CreateLinkRequest(BaseModel):
    path: str = Field(..., description="Relative path from workspace root")
    expires_hours: int = Field(default=24, ge=1, le=168, description="Link TTL in hours (max 7 days)")


class CreateLinkResponse(BaseModel):
    url: str
    expires_at: str
    filename: str


@router.post(
    "/create-link",
    summary="Generate a temporary download link",
    response_model=CreateLinkResponse,
)
async def create_download_link(
    body: CreateLinkRequest,
    token: str = Query(..., description="Auth token"),
) -> dict[str, Any]:
    """Generate a signed download URL for a workspace file. Auth via ?token= query param."""
    if token != settings.local_auth_token:
        raise HTTPException(status_code=401, detail="Invalid token")

    workspace_root = _get_workspace_root()
    resolved = _resolve_safe_path(workspace_root, body.path)

    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found in workspace.")

    size = resolved.stat().st_size
    if size > _MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large ({size} bytes, max {_MAX_FILE_SIZE_BYTES}).")

    file_token = create_file_token(body.path, expires_hours=body.expires_hours)
    import time
    from datetime import datetime, timezone

    expires_at = datetime.fromtimestamp(
        time.time() + body.expires_hours * 3600, tz=timezone.utc
    ).isoformat()

    download_url = f"{settings.base_url}/api/v1/files/download?token={file_token}"

    logger.info("file_serve.link_created path=%s expires_hours=%s", body.path, body.expires_hours)
    return {
        "url": download_url,
        "expires_at": expires_at,
        "filename": resolved.name,
    }


@router.get(
    "/download",
    summary="Download a file via signed token",
)
async def download_file(
    token: str = Query(..., description="Signed download token"),
) -> FileResponse:
    """Download a workspace file using a temporary signed token. No auth required — token IS the auth."""
    relative_path = verify_file_token(token)
    if relative_path is None:
        raise HTTPException(status_code=401, detail="Invalid or expired download link.")

    workspace_root = _get_workspace_root()
    resolved = _resolve_safe_path(workspace_root, relative_path)

    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    size = resolved.stat().st_size
    if size > _MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File too large.")

    suffix = resolved.suffix.lower()
    media_type = _MIME_MAP.get(suffix, "application/octet-stream")
    disposition = "inline" if media_type in _INLINE_TYPES else "attachment"

    return FileResponse(
        path=str(resolved),
        media_type=media_type,
        filename=resolved.name,
        content_disposition_type=disposition,
    )
