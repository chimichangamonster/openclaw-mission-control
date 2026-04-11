"""Microsoft Graph integration — OAuth flow, OneDrive, Outlook Calendar, and connection management."""

from __future__ import annotations

import json
import secrets
from typing import TYPE_CHECKING, Any, Literal, overload
from uuid import uuid4

import redis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlmodel import col, select

from app.api.deps import ORG_MEMBER_DEP, ORG_RATE_LIMIT_DEP, SESSION_DEP, require_feature
from app.core.config import settings
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.microsoft_connection import MicrosoftConnection
from app.services.microsoft.graph_oauth import MicrosoftGraphOAuthProvider
from app.services.microsoft.token_manager import get_valid_graph_token, store_graph_tokens
from app.services.organizations import OrganizationContext

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)
router = APIRouter(
    prefix="/microsoft-graph",
    tags=["microsoft-graph"],
)

# Shared dependencies for authenticated routes (callback is exempt — it's a Microsoft redirect)
_AUTH_DEPS = [Depends(require_feature("microsoft_graph")), ORG_RATE_LIMIT_DEP]

_STATE_TTL_SECONDS = 300
_oauth_provider = MicrosoftGraphOAuthProvider()


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.rq_redis_url)


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------


@router.get("/authorize", summary="Initiate Microsoft Graph OAuth", dependencies=_AUTH_DEPS)
async def initiate_oauth(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> dict[str, str]:
    """Generate the OAuth2 authorization URL for Microsoft Graph."""
    state = secrets.token_urlsafe(32)
    state_payload = json.dumps(
        {
            "user_id": str(ctx.member.user_id),
            "organization_id": str(ctx.organization.id),
        }
    )
    client = _redis_client()
    client.setex(f"msgraph_oauth_state:{state}", _STATE_TTL_SECONDS, state_payload)

    url = _oauth_provider.get_authorization_url(state)
    return {"authorization_url": url, "state": state}


@router.get("/callback", summary="OAuth callback", include_in_schema=False)
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str | None = Query(default=None),
    session: AsyncSession = SESSION_DEP,
) -> RedirectResponse:
    """Handle Microsoft Graph OAuth2 callback."""
    if error:
        logger.warning("microsoft_graph.oauth.error error=%s", error)
        return RedirectResponse(url=f"/org-settings?graph_error={error}")

    client = _redis_client()
    raw_state = client.get(f"msgraph_oauth_state:{state}")
    if raw_state is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state."
        )
    client.delete(f"msgraph_oauth_state:{state}")

    state_data = json.loads(raw_state if isinstance(raw_state, str) else raw_state.decode())
    user_id = state_data["user_id"]
    organization_id = state_data["organization_id"]

    try:
        result = await _oauth_provider.exchange_code(code)
    except Exception as exc:
        logger.exception("microsoft_graph.oauth.exchange_failed error=%s", exc)
        return RedirectResponse(url="/org-settings?graph_error=exchange_failed")

    # Upsert MicrosoftConnection
    stmt = select(MicrosoftConnection).where(
        MicrosoftConnection.organization_id == organization_id,
        MicrosoftConnection.provider_account_id == result.provider_account_id,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()

    if existing:
        connection = existing
    else:
        connection = MicrosoftConnection(
            id=uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            created_at=utcnow(),
        )

    connection.provider_account_id = result.provider_account_id
    connection.email_address = result.email_address
    connection.display_name = result.display_name
    connection.scopes = result.scopes
    connection.is_active = True
    connection.updated_at = utcnow()

    store_graph_tokens(
        connection,
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        expires_in=result.expires_in,
    )

    session.add(connection)
    await session.commit()

    logger.info(
        "microsoft_graph.oauth.connected email=%s org_id=%s",
        result.email_address,
        organization_id,
    )
    return RedirectResponse(url="/org-settings?graph_connected=true")


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


@router.get("/status", summary="Get Microsoft Graph connection status", dependencies=_AUTH_DEPS)
async def connection_status(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """Check if the org has an active Microsoft Graph connection."""
    conn = await _get_connection(session, ctx.organization.id)
    if not conn:
        return {"connected": False}

    return {
        "connected": True,
        "email": conn.email_address,
        "display_name": conn.display_name,
        "default_folder": conn.default_folder,
        "scopes": conn.scopes,
        "connected_at": conn.created_at.isoformat() if conn.created_at else None,
    }


@router.delete("/disconnect", summary="Disconnect Microsoft Graph", dependencies=_AUTH_DEPS)
async def disconnect(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, bool]:
    """Deactivate the Microsoft Graph connection for this org."""
    conn = await _get_connection(session, ctx.organization.id)
    if conn:
        conn.is_active = False
        conn.updated_at = utcnow()
        session.add(conn)
        await session.commit()
        logger.info("microsoft_graph.disconnected org_id=%s", ctx.organization.id)
    return {"ok": True}


class FolderUpdate(BaseModel):
    default_folder: str = Field(..., description="OneDrive folder path for generated documents")


@router.patch("/settings", summary="Update Graph connection settings", dependencies=_AUTH_DEPS)
async def update_graph_settings(
    body: FolderUpdate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, bool]:
    """Update the default OneDrive folder for document storage."""
    conn = await _get_connection(session, ctx.organization.id, require=True)
    conn.default_folder = body.default_folder
    conn.updated_at = utcnow()
    session.add(conn)
    await session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# OneDrive file operations
# ---------------------------------------------------------------------------


@router.get("/files", summary="List OneDrive files", dependencies=_AUTH_DEPS)
async def list_onedrive_files(
    path: str = Query(default="/", description="Folder path"),
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """List files in a OneDrive folder."""
    from app.services.microsoft.onedrive import list_files

    conn = await _get_connection(session, ctx.organization.id, require=True)
    token = await get_valid_graph_token(session, conn)
    await session.commit()

    files = await list_files(token, path)
    return {"path": path, "files": files}


class UploadRequest(BaseModel):
    folder_path: str = Field(
        default="", description="OneDrive folder path (defaults to org's default folder)"
    )
    filename: str
    content_base64: str = Field(..., description="Base64-encoded file content")
    content_type: str = Field(default="application/octet-stream")
    create_sharing_link: bool = Field(default=True)
    sharing_scope: str = Field(default="organization", pattern="^(organization|anonymous)$")


@router.post("/files/upload", summary="Upload file to OneDrive", dependencies=_AUTH_DEPS)
async def upload_to_onedrive(
    body: UploadRequest,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """Upload a file to OneDrive and optionally create a sharing link."""
    import base64

    from app.services.microsoft.onedrive import create_sharing_link, upload_file

    conn = await _get_connection(session, ctx.organization.id, require=True)
    token = await get_valid_graph_token(session, conn)
    await session.commit()

    folder = body.folder_path or conn.default_folder
    content = base64.b64decode(body.content_base64)

    item = await upload_file(token, folder, body.filename, content, body.content_type)

    result: dict[str, Any] = {
        "id": item.get("id"),
        "name": item.get("name"),
        "web_url": item.get("webUrl"),
        "size": item.get("size"),
    }

    if body.create_sharing_link and item.get("id"):
        share_url = await create_sharing_link(
            token,
            item["id"],
            link_type="view",
            scope=body.sharing_scope,
        )
        result["sharing_url"] = share_url

    return result


@router.post(
    "/files/upload-workspace", summary="Upload workspace file to OneDrive", dependencies=_AUTH_DEPS
)
async def upload_workspace_to_onedrive(
    token: str = Query(..., description="Auth token"),
    workspace_path: str = Query(..., description="Relative path in gateway workspace"),
    folder_path: str = Query(default="", description="OneDrive folder (defaults to org default)"),
    sharing_scope: str = Query(default="organization"),
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """Upload a file from the gateway workspace to OneDrive. For agent use."""
    from pathlib import Path

    from app.services.microsoft.onedrive import create_sharing_link, upload_file

    if token != settings.local_auth_token:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Get the first active connection (platform-level call)
    stmt = (
        select(MicrosoftConnection)
        .where(
            col(MicrosoftConnection.is_active).is_(True),
        )
        .limit(1)
    )
    conn = (await session.execute(stmt)).scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="No active Microsoft Graph connection.")

    graph_token = await get_valid_graph_token(session, conn)
    await session.commit()

    # Read file from workspace
    workspace_root = Path(settings.gateway_workspaces_root or settings.gateway_workspace_path)
    file_path = (workspace_root / workspace_path).resolve()
    if not str(file_path).startswith(str(workspace_root.resolve())):
        raise HTTPException(status_code=403, detail="Path outside workspace.")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found in workspace.")

    content = file_path.read_bytes()
    filename = file_path.name

    # Determine MIME type
    from app.api.file_serve import _MIME_MAP

    mime = _MIME_MAP.get(file_path.suffix.lower(), "application/octet-stream")

    folder = folder_path or conn.default_folder
    item = await upload_file(graph_token, folder, filename, content, mime)

    result: dict[str, Any] = {
        "id": item.get("id"),
        "name": item.get("name"),
        "web_url": item.get("webUrl"),
        "size": item.get("size"),
    }

    if item.get("id"):
        share_url = await create_sharing_link(
            graph_token,
            item["id"],
            link_type="view",
            scope=sharing_scope,
        )
        result["sharing_url"] = share_url

    return result


# ---------------------------------------------------------------------------
# Outlook Calendar operations
# ---------------------------------------------------------------------------


@router.get("/calendar/events", summary="List Outlook Calendar events", dependencies=_AUTH_DEPS)
async def list_outlook_events(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
    time_min: str = Query(default="", description="Start time filter (ISO 8601)"),
    time_max: str = Query(default="", description="End time filter (ISO 8601)"),
    q: str = Query(default="", description="Search query"),
    max_results: int = Query(default=50, le=250),
) -> dict[str, Any]:
    """List events from Outlook Calendar."""
    from app.services.microsoft.outlook_calendar import list_events as outlook_list

    conn = await _get_connection(session, ctx.organization.id, require=True)
    token = await get_valid_graph_token(session, conn)
    await session.commit()

    from datetime import datetime as dt

    t_min = dt.fromisoformat(time_min) if time_min else None
    t_max = dt.fromisoformat(time_max) if time_max else None

    events = await outlook_list(
        token, time_min=t_min, time_max=t_max, max_results=max_results, q=q or None
    )
    return {"events": events}


class OutlookCreateEventRequest(BaseModel):
    summary: str
    start: str = Field(..., description="ISO 8601 datetime or YYYY-MM-DD for all-day")
    end: str = Field(..., description="ISO 8601 datetime or YYYY-MM-DD for all-day")
    description: str = ""
    location: str = ""
    attendees: list[str] = Field(default_factory=list)
    time_zone: str = "America/Edmonton"


@router.post(
    "/calendar/events",
    status_code=status.HTTP_201_CREATED,
    summary="Create Outlook Calendar event",
    dependencies=_AUTH_DEPS,
)
async def create_outlook_event(
    body: OutlookCreateEventRequest,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """Create a calendar event in Outlook."""
    from app.services.microsoft.outlook_calendar import create_event as outlook_create

    conn = await _get_connection(session, ctx.organization.id, require=True)
    token = await get_valid_graph_token(session, conn)
    await session.commit()

    event = await outlook_create(
        token,
        summary=body.summary,
        start=body.start,
        end=body.end,
        description=body.description,
        location=body.location,
        attendees=body.attendees or None,
        time_zone=body.time_zone,
    )
    return event


class OutlookUpdateEventRequest(BaseModel):
    summary: str | None = None
    start: str | None = None
    end: str | None = None
    description: str | None = None
    location: str | None = None
    time_zone: str = "America/Edmonton"


@router.patch(
    "/calendar/events/{event_id}", summary="Update Outlook Calendar event", dependencies=_AUTH_DEPS
)
async def update_outlook_event(
    event_id: str,
    body: OutlookUpdateEventRequest,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """Update an existing Outlook calendar event."""
    from app.services.microsoft.outlook_calendar import update_event as outlook_update

    conn = await _get_connection(session, ctx.organization.id, require=True)
    token = await get_valid_graph_token(session, conn)
    await session.commit()

    event = await outlook_update(
        token,
        event_id,
        summary=body.summary,
        start=body.start,
        end=body.end,
        description=body.description,
        location=body.location,
        time_zone=body.time_zone,
    )
    return event


@router.delete(
    "/calendar/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Outlook Calendar event",
    dependencies=_AUTH_DEPS,
)
async def delete_outlook_event(
    event_id: str,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    """Delete an Outlook calendar event."""
    from app.services.microsoft.outlook_calendar import delete_event as outlook_delete

    conn = await _get_connection(session, ctx.organization.id, require=True)
    token = await get_valid_graph_token(session, conn)
    await session.commit()

    await outlook_delete(token, event_id)


@router.get("/calendar/calendars", summary="List Outlook Calendars", dependencies=_AUTH_DEPS)
async def list_outlook_calendars(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """List all calendars accessible to the connected Outlook account."""
    from app.services.microsoft.outlook_calendar import list_calendars as outlook_list_cals

    conn = await _get_connection(session, ctx.organization.id, require=True)
    token = await get_valid_graph_token(session, conn)
    await session.commit()

    calendars = await outlook_list_cals(token)
    return {"calendars": calendars}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@overload
async def _get_connection(
    session: AsyncSession,
    org_id: Any,
    *,
    require: Literal[True],
) -> MicrosoftConnection: ...


@overload
async def _get_connection(
    session: AsyncSession,
    org_id: Any,
    *,
    require: bool = ...,
) -> MicrosoftConnection | None: ...


async def _get_connection(
    session: AsyncSession,
    org_id: Any,
    *,
    require: bool = False,
) -> MicrosoftConnection | None:
    stmt = select(MicrosoftConnection).where(
        MicrosoftConnection.organization_id == org_id,
        col(MicrosoftConnection.is_active).is_(True),
    )
    conn = (await session.execute(stmt)).scalar_one_or_none()
    if require and not conn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Microsoft Graph connection. Connect via /org-settings.",
        )
    return conn
