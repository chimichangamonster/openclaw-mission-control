"""Google Calendar integration — OAuth flow, event CRUD, connection management."""

from __future__ import annotations

import json
import secrets
from datetime import datetime
from typing import TYPE_CHECKING, Any
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
from app.models.google_calendar_connection import GoogleCalendarConnection
from app.services.google.calendar_oauth import GoogleCalendarOAuthProvider
from app.services.google.token_manager import get_valid_google_token, store_google_tokens
from app.services.organizations import OrganizationContext, is_org_admin

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)
router = APIRouter(
    prefix="/google-calendar",
    tags=["google-calendar"],
)

# Shared dependencies for authenticated routes (callback is exempt — it's a Google redirect)
_AUTH_DEPS = [Depends(require_feature("google_calendar")), ORG_RATE_LIMIT_DEP]

_STATE_TTL_SECONDS = 300
_oauth_provider = GoogleCalendarOAuthProvider()


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.rq_redis_url)


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------


@router.get("/authorize", summary="Initiate Google Calendar OAuth", dependencies=_AUTH_DEPS)
async def initiate_oauth(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> dict[str, str]:
    """Generate the OAuth2 authorization URL for Google Calendar."""
    state = secrets.token_urlsafe(32)
    state_payload = json.dumps({
        "user_id": str(ctx.member.user_id),
        "organization_id": str(ctx.organization.id),
    })
    client = _redis_client()
    client.setex(f"gcal_oauth_state:{state}", _STATE_TTL_SECONDS, state_payload)

    url = _oauth_provider.get_authorization_url(state)
    return {"authorization_url": url, "state": state}


@router.get("/callback", summary="OAuth callback", include_in_schema=False)
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str | None = Query(default=None),
    session: AsyncSession = SESSION_DEP,
) -> RedirectResponse:
    """Handle Google Calendar OAuth2 callback."""
    if error:
        logger.warning("google_calendar.oauth.error error=%s", error)
        return RedirectResponse(url=f"/org-settings?gcal_error={error}")

    client = _redis_client()
    raw_state = client.get(f"gcal_oauth_state:{state}")
    if raw_state is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state.")
    client.delete(f"gcal_oauth_state:{state}")

    state_data = json.loads(raw_state if isinstance(raw_state, str) else raw_state.decode())
    user_id = state_data["user_id"]
    organization_id = state_data["organization_id"]

    try:
        result = await _oauth_provider.exchange_code(code)
    except Exception as exc:
        logger.exception("google_calendar.oauth.exchange_failed error=%s", exc)
        return RedirectResponse(url="/org-settings?gcal_error=exchange_failed")

    # Upsert GoogleCalendarConnection (scoped to user — each member can connect their own)
    stmt = select(GoogleCalendarConnection).where(
        GoogleCalendarConnection.organization_id == organization_id,
        GoogleCalendarConnection.user_id == user_id,
        GoogleCalendarConnection.provider_account_id == result.provider_account_id,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()

    if existing:
        connection = existing
    else:
        connection = GoogleCalendarConnection(
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

    store_google_tokens(
        connection,
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        expires_in=result.expires_in,
    )

    session.add(connection)
    await session.commit()

    logger.info(
        "google_calendar.oauth.connected email=%s org_id=%s",
        result.email_address, organization_id,
    )
    return RedirectResponse(url="/org-settings?gcal_connected=true")


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


@router.get("/status", summary="Get Google Calendar connection status", dependencies=_AUTH_DEPS)
async def connection_status(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """Check if the org has active Google Calendar connections."""
    connections = await _list_connections(session, ctx)
    if not connections:
        return {"connected": False, "connections": []}

    return {
        "connected": True,
        "connections": [
            {
                "id": str(conn.id),
                "email": conn.email_address,
                "display_name": conn.display_name,
                "default_calendar_id": conn.default_calendar_id,
                "visibility": conn.visibility,
                "user_id": str(conn.user_id),
                "scopes": conn.scopes,
                "connected_at": conn.created_at.isoformat() if conn.created_at else None,
            }
            for conn in connections
        ],
        # Backward compat: return first connection's fields at top level
        "email": connections[0].email_address,
        "display_name": connections[0].display_name,
        "default_calendar_id": connections[0].default_calendar_id,
        "scopes": connections[0].scopes,
        "connected_at": connections[0].created_at.isoformat() if connections[0].created_at else None,
    }


@router.delete("/disconnect", summary="Disconnect Google Calendar", dependencies=_AUTH_DEPS)
async def disconnect(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
    connection_id: str = Query(default="", description="Specific connection to disconnect"),
) -> dict[str, bool]:
    """Deactivate a Google Calendar connection."""
    conn = await _get_connection(session, ctx.organization.id, ctx=ctx, connection_id=connection_id or None)
    if conn:
        # Only owner of connection or admin can disconnect
        if conn.user_id != ctx.member.user_id and not is_org_admin(ctx.member):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the connection owner or admin can disconnect.")
        conn.is_active = False
        conn.updated_at = utcnow()
        session.add(conn)
        await session.commit()
        logger.info("google_calendar.disconnected org_id=%s conn_id=%s", ctx.organization.id, conn.id)
    return {"ok": True}


class CalendarConnectionUpdate(BaseModel):
    visibility: str = Field(..., description="'shared' or 'private'")


@router.patch("/connections/{connection_id}", summary="Update calendar connection visibility", dependencies=_AUTH_DEPS)
async def update_connection(
    connection_id: str,
    body: CalendarConnectionUpdate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """Update calendar connection settings (visibility)."""
    if body.visibility not in ("shared", "private"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="visibility must be 'shared' or 'private'")
    conn = await _get_connection(session, ctx.organization.id, require=True, connection_id=connection_id, ctx=ctx)
    if conn.user_id != ctx.member.user_id and not is_org_admin(ctx.member):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the connection owner or admin can change visibility.")
    conn.visibility = body.visibility
    conn.updated_at = utcnow()
    session.add(conn)
    await session.commit()
    return {
        "id": str(conn.id),
        "visibility": conn.visibility,
        "email": conn.email_address,
    }


class CalendarSettingsUpdate(BaseModel):
    default_calendar_id: str = Field(..., description="Calendar ID to use for scheduling")


@router.patch("/settings", summary="Update default calendar", dependencies=_AUTH_DEPS)
async def update_calendar_settings(
    body: CalendarSettingsUpdate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, bool]:
    """Update the default calendar for scheduling events."""
    conn = await _get_connection(session, ctx.organization.id, require=True, ctx=ctx)
    conn.default_calendar_id = body.default_calendar_id
    conn.updated_at = utcnow()
    session.add(conn)
    await session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Calendar operations
# ---------------------------------------------------------------------------


@router.get("/calendars", summary="List calendars", dependencies=_AUTH_DEPS)
async def list_calendars(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """List all calendars accessible to the connected Google account."""
    from app.services.google.calendar import list_calendars as gcal_list

    conn = await _get_connection(session, ctx.organization.id, require=True, ctx=ctx)
    token = await get_valid_google_token(session, conn)
    await session.commit()

    calendars = await gcal_list(token)
    return {"calendars": calendars}


@router.get("/events", summary="List events", dependencies=_AUTH_DEPS)
async def list_events(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
    calendar_id: str = Query(default="", description="Calendar ID (defaults to org default)"),
    connection_id: str = Query(default="", description="Connection ID (defaults to first visible)"),
    time_min: str = Query(default="", description="Start time filter (ISO 8601)"),
    time_max: str = Query(default="", description="End time filter (ISO 8601)"),
    q: str = Query(default="", description="Search query"),
    max_results: int = Query(default=50, le=250),
) -> dict[str, Any]:
    """List events from a calendar."""
    from app.services.google.calendar import list_events as gcal_list_events

    conn = await _get_connection(session, ctx.organization.id, require=True, connection_id=connection_id or None, ctx=ctx)
    token = await get_valid_google_token(session, conn)
    await session.commit()

    cal_id = calendar_id or conn.default_calendar_id
    t_min = datetime.fromisoformat(time_min) if time_min else None
    t_max = datetime.fromisoformat(time_max) if time_max else None

    events = await gcal_list_events(
        token, cal_id,
        time_min=t_min, time_max=t_max,
        max_results=max_results,
        q=q or None,
    )
    return {"calendar_id": cal_id, "events": events}


class CreateEventRequest(BaseModel):
    summary: str
    start: str = Field(..., description="ISO 8601 datetime or YYYY-MM-DD for all-day")
    end: str = Field(..., description="ISO 8601 datetime or YYYY-MM-DD for all-day")
    description: str = ""
    location: str = ""
    calendar_id: str = ""
    connection_id: str = ""
    attendees: list[str] = Field(default_factory=list)
    time_zone: str = "America/Edmonton"


@router.post("/events", status_code=status.HTTP_201_CREATED, summary="Create event", dependencies=_AUTH_DEPS)
async def create_event(
    body: CreateEventRequest,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """Create a calendar event."""
    from app.services.google.calendar import create_event as gcal_create

    conn = await _get_connection(session, ctx.organization.id, require=True, connection_id=body.connection_id or None, ctx=ctx)
    token = await get_valid_google_token(session, conn)
    await session.commit()

    cal_id = body.calendar_id or conn.default_calendar_id
    event = await gcal_create(
        token, cal_id,
        summary=body.summary,
        start=body.start,
        end=body.end,
        description=body.description,
        location=body.location,
        attendees=body.attendees or None,
        time_zone=body.time_zone,
    )
    return event


class UpdateEventRequest(BaseModel):
    summary: str | None = None
    start: str | None = None
    end: str | None = None
    description: str | None = None
    location: str | None = None
    time_zone: str = "America/Edmonton"


@router.patch("/events/{event_id}", summary="Update event", dependencies=_AUTH_DEPS)
async def update_event(
    event_id: str,
    body: UpdateEventRequest,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
    calendar_id: str = Query(default="", description="Calendar ID"),
    connection_id: str = Query(default="", description="Connection ID"),
) -> dict[str, Any]:
    """Update an existing calendar event."""
    from app.services.google.calendar import update_event as gcal_update

    conn = await _get_connection(session, ctx.organization.id, require=True, connection_id=connection_id or None, ctx=ctx)
    token = await get_valid_google_token(session, conn)
    await session.commit()

    cal_id = calendar_id or conn.default_calendar_id
    event = await gcal_update(
        token, cal_id, event_id,
        summary=body.summary,
        start=body.start,
        end=body.end,
        description=body.description,
        location=body.location,
        time_zone=body.time_zone,
    )
    return event


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete event", dependencies=_AUTH_DEPS)
async def delete_event(
    event_id: str,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
    calendar_id: str = Query(default="", description="Calendar ID"),
    connection_id: str = Query(default="", description="Connection ID"),
) -> None:
    """Delete a calendar event."""
    from app.services.google.calendar import delete_event as gcal_delete

    conn = await _get_connection(session, ctx.organization.id, require=True, connection_id=connection_id or None, ctx=ctx)
    token = await get_valid_google_token(session, conn)
    await session.commit()

    cal_id = calendar_id or conn.default_calendar_id
    await gcal_delete(token, cal_id, event_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_connection(
    session: AsyncSession,
    org_id: Any,
    *,
    require: bool = False,
    connection_id: str | None = None,
    ctx: OrganizationContext | None = None,
) -> GoogleCalendarConnection | None:
    """Get a calendar connection, optionally by ID with visibility check."""
    from sqlalchemy import or_

    if connection_id:
        from uuid import UUID as _UUID

        conn = await session.get(GoogleCalendarConnection, _UUID(connection_id))
        if conn is None or conn.organization_id != org_id or not conn.is_active:
            if require:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar connection not found.")
            return None
        # Visibility check
        if ctx and conn.visibility == "private" and conn.user_id != ctx.member.user_id and not is_org_admin(ctx.member):
            if require:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar connection not found.")
            return None
        return conn

    # Default: return the first visible active connection
    stmt = select(GoogleCalendarConnection).where(
        GoogleCalendarConnection.organization_id == org_id,
        col(GoogleCalendarConnection.is_active).is_(True),
    )
    if ctx and not is_org_admin(ctx.member):
        stmt = stmt.where(
            or_(
                GoogleCalendarConnection.visibility == "shared",
                GoogleCalendarConnection.user_id == ctx.member.user_id,
            )
        )
    stmt = stmt.order_by(GoogleCalendarConnection.created_at)
    conn = (await session.execute(stmt)).scalars().first()
    if require and not conn:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Google Calendar connection. Connect via /org-settings.",
        )
    return conn


async def _list_connections(
    session: AsyncSession,
    ctx: OrganizationContext,
) -> list[GoogleCalendarConnection]:
    """List all active calendar connections visible to the caller."""
    from sqlalchemy import or_

    stmt = select(GoogleCalendarConnection).where(
        GoogleCalendarConnection.organization_id == ctx.organization.id,
        col(GoogleCalendarConnection.is_active).is_(True),
    )
    if not is_org_admin(ctx.member):
        stmt = stmt.where(
            or_(
                GoogleCalendarConnection.visibility == "shared",
                GoogleCalendarConnection.user_id == ctx.member.user_id,
            )
        )
    stmt = stmt.order_by(GoogleCalendarConnection.created_at)
    result = await session.execute(stmt)
    return list(result.scalars().all())
