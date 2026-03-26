"""Thin gateway session-inspection API wrappers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status

from app.api.deps import require_org_admin
from app.core.auth import AuthContext, get_auth_context
from app.core.logging import get_logger
from app.core.workspace import resolve_org_workspace
from app.db.session import get_session
from app.schemas.common import OkResponse
from app.schemas.gateway_api import (
    ChatUploadResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    GatewayCommandsResponse,
    GatewayResolveQuery,
    GatewaySessionHistoryResponse,
    GatewaySessionMessageRequest,
    GatewaySessionResponse,
    GatewaySessionsResponse,
    GatewaysStatusResponse,
    RenameSessionRequest,
)
from app.services.openclaw.gateway_rpc import GATEWAY_EVENTS, GATEWAY_METHODS, PROTOCOL_VERSION
from app.services.openclaw.session_service import GatewaySessionService
from app.services.organizations import OrganizationContext

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)
router = APIRouter(prefix="/gateways", tags=["gateways"])
SESSION_DEP = Depends(get_session)
AUTH_DEP = Depends(get_auth_context)
ORG_ADMIN_DEP = Depends(require_org_admin)
BOARD_ID_QUERY = Query(default=None)

# Chat upload constraints
_CHAT_UPLOAD_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_CHAT_UPLOAD_ALLOWED_TYPES = frozenset({
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml",
    "application/pdf",
    "text/plain", "text/csv", "text/markdown",
    "application/json",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
})


@router.post(
    "/sessions/{session_id}/upload",
    response_model=ChatUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_chat_file(
    session_id: str,
    file: UploadFile,
    board_id: str | None = BOARD_ID_QUERY,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> ChatUploadResponse:
    """Upload a file to attach to a chat message.

    Files are saved to the gateway workspace under uploads/chat/{org_id}/
    so the agent can access them directly.
    """
    content_type = (file.content_type or "application/octet-stream").lower()
    if content_type not in _CHAT_UPLOAD_ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{content_type}' not supported for chat uploads.",
        )

    data = await file.read()
    if len(data) > _CHAT_UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large ({len(data)} bytes, max {_CHAT_UPLOAD_MAX_BYTES}).",
        )

    workspace = resolve_org_workspace(ctx.organization)

    org_id = str(ctx.organization.id)
    original_name = file.filename or "upload"
    suffix = Path(original_name).suffix or ""
    unique_name = f"{uuid4().hex[:12]}{suffix}"
    relative_dir = f"uploads/chat/{org_id}"
    upload_dir = workspace / relative_dir
    upload_dir.mkdir(parents=True, exist_ok=True)

    dest = upload_dir / unique_name
    dest.write_bytes(data)
    workspace_path = f"{relative_dir}/{unique_name}"

    logger.info(
        "chat.upload org_id=%s file=%s size=%d path=%s",
        org_id, original_name, len(data), workspace_path,
    )

    return ChatUploadResponse(
        filename=original_name,
        workspace_path=workspace_path,
        content_type=content_type,
        size_bytes=len(data),
    )


def _query_to_resolve_input(
    board_id: str | None = Query(default=None),
    gateway_url: str | None = Query(default=None),
    gateway_token: str | None = Query(default=None),
    gateway_disable_device_pairing: bool | None = Query(default=None),
    gateway_allow_insecure_tls: bool | None = Query(default=None),
) -> GatewayResolveQuery:
    return GatewaySessionService.to_resolve_query(
        board_id=board_id,
        gateway_url=gateway_url,
        gateway_token=gateway_token,
        gateway_disable_device_pairing=gateway_disable_device_pairing,
        gateway_allow_insecure_tls=gateway_allow_insecure_tls,
    )


RESOLVE_INPUT_DEP = Depends(_query_to_resolve_input)


@router.get("/status", response_model=GatewaysStatusResponse)
async def gateways_status(
    params: GatewayResolveQuery = RESOLVE_INPUT_DEP,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> GatewaysStatusResponse:
    """Return gateway connectivity and session status."""
    service = GatewaySessionService(session)
    return await service.get_status(
        params=params,
        organization_id=ctx.organization.id,
        user=auth.user,
    )


@router.get("/sessions", response_model=GatewaySessionsResponse)
async def list_gateway_sessions(
    board_id: str | None = BOARD_ID_QUERY,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> GatewaySessionsResponse:
    """List sessions for a gateway associated with a board."""
    service = GatewaySessionService(session)
    return await service.get_sessions(
        board_id=board_id,
        organization_id=ctx.organization.id,
        user=auth.user,
    )


@router.post("/sessions", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_gateway_session(
    payload: CreateSessionRequest,
    board_id: str | None = BOARD_ID_QUERY,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> CreateSessionResponse:
    """Create a new named chat session on the gateway."""
    service = GatewaySessionService(session)
    return await service.create_session(
        label=payload.label,
        board_id=board_id,
        organization_id=ctx.organization.id,
        user=auth.user,
    )


@router.patch("/sessions/{session_id}", response_model=GatewaySessionResponse)
async def rename_gateway_session(
    session_id: str,
    payload: RenameSessionRequest,
    board_id: str | None = BOARD_ID_QUERY,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> GatewaySessionResponse:
    """Rename an existing chat session."""
    service = GatewaySessionService(session)
    return await service.rename_session(
        session_id=session_id,
        label=payload.label,
        board_id=board_id,
        organization_id=ctx.organization.id,
        user=auth.user,
    )


@router.get("/sessions/{session_id}", response_model=GatewaySessionResponse)
async def get_gateway_session(
    session_id: str,
    board_id: str | None = BOARD_ID_QUERY,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> GatewaySessionResponse:
    """Get a specific gateway session by key."""
    service = GatewaySessionService(session)
    return await service.get_session(
        session_id=session_id,
        board_id=board_id,
        organization_id=ctx.organization.id,
        user=auth.user,
    )


@router.get("/sessions/{session_id}/history", response_model=GatewaySessionHistoryResponse)
async def get_session_history(
    session_id: str,
    board_id: str | None = BOARD_ID_QUERY,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> GatewaySessionHistoryResponse:
    """Fetch chat history for a gateway session."""
    service = GatewaySessionService(session)
    return await service.get_session_history(
        session_id=session_id,
        board_id=board_id,
        organization_id=ctx.organization.id,
        user=auth.user,
    )


@router.post("/sessions/{session_id}/message", response_model=OkResponse)
async def send_gateway_session_message(
    session_id: str,
    payload: GatewaySessionMessageRequest,
    board_id: str | None = BOARD_ID_QUERY,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> OkResponse:
    """Send a message into a specific gateway session."""
    service = GatewaySessionService(session)
    await service.send_session_message(
        session_id=session_id,
        payload=payload,
        board_id=board_id,
        organization_id=ctx.organization.id,
        user=auth.user,
    )
    return OkResponse()


@router.post("/sessions/{session_id}/abort", response_model=OkResponse)
async def abort_gateway_session(
    session_id: str,
    board_id: str | None = BOARD_ID_QUERY,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> OkResponse:
    """Abort (stop) an agent's in-progress response."""
    service = GatewaySessionService(session)
    await service.abort_session_chat(
        session_id=session_id,
        board_id=board_id,
        organization_id=ctx.organization.id,
        user=auth.user,
    )
    return OkResponse()


@router.post("/sessions/{session_id}/compact", response_model=OkResponse)
async def compact_gateway_session(
    session_id: str,
    board_id: str | None = BOARD_ID_QUERY,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> OkResponse:
    """Compact a session's context (summarise and trim history)."""
    service = GatewaySessionService(session)
    await service.compact_session_history(
        session_id=session_id,
        board_id=board_id,
        organization_id=ctx.organization.id,
        user=auth.user,
    )
    return OkResponse()


@router.post("/sessions/{session_id}/reset", response_model=OkResponse)
async def reset_gateway_session(
    session_id: str,
    board_id: str | None = BOARD_ID_QUERY,
    session: AsyncSession = SESSION_DEP,
    auth: AuthContext = AUTH_DEP,
    ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> OkResponse:
    """Reset a session (clear conversation history)."""
    service = GatewaySessionService(session)
    await service.reset_session_history(
        session_id=session_id,
        board_id=board_id,
        organization_id=ctx.organization.id,
        user=auth.user,
    )
    return OkResponse()


@router.get("/commands", response_model=GatewayCommandsResponse)
async def gateway_commands(
    _auth: AuthContext = AUTH_DEP,
    _ctx: OrganizationContext = ORG_ADMIN_DEP,
) -> GatewayCommandsResponse:
    """Return supported gateway protocol methods and events."""
    return GatewayCommandsResponse(
        protocol_version=PROTOCOL_VERSION,
        methods=GATEWAY_METHODS,
        events=GATEWAY_EVENTS,
    )
