"""Gateway live activity feed — real-time agent session data."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import ORG_MEMBER_DEP
from app.core.logging import get_logger
from app.services.openclaw.gateway_rpc import GatewayConfig, openclaw_call
from app.services.organizations import OrganizationContext

logger = get_logger(__name__)
router = APIRouter(prefix="/gateway/live", tags=["gateway-live"])


class AgentSession(BaseModel):
    agent_id: str
    channel: str
    model: str
    last_active: str
    seconds_ago: int
    input_tokens: int
    output_tokens: int
    status: str  # "active", "idle", "sleeping"


class LiveFeedResponse(BaseModel):
    sessions: list[AgentSession]
    timestamp: str


@router.get("", summary="Live gateway activity")
async def get_live_feed(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> LiveFeedResponse:
    """Return current agent sessions with activity status."""
    from sqlmodel import select as sql_select

    from app.db.session import async_session_maker
    from app.models.gateways import Gateway

    async with async_session_maker() as db_session:
        result = await db_session.execute(
            sql_select(Gateway).where(Gateway.organization_id == ctx.organization.id)
        )
        gateway = result.scalars().first()

    if not gateway:
        return LiveFeedResponse(sessions=[], timestamp=datetime.now(UTC).isoformat())

    config = GatewayConfig(url=gateway.url, token=gateway.token)
    try:
        sessions_data = await openclaw_call("sessions.list", config=config)
    except Exception:
        logger.exception("gateway_live.rpc_failed")
        return LiveFeedResponse(sessions=[], timestamp=datetime.now(UTC).isoformat())

    now_ms = datetime.now(UTC).timestamp() * 1000
    sessions = []

    if isinstance(sessions_data, list):
        session_list = sessions_data
    elif isinstance(sessions_data, dict):
        session_list = sessions_data.get("sessions", [])
    else:
        session_list = []
    for s in session_list:
        key = s.get("key", "")
        if "heartbeat" in key or "mc-gateway" in key:
            continue  # Skip internal sessions

        channel = s.get("groupChannel", s.get("displayName", "unknown"))
        agent_id = key.split(":")[1] if len(key.split(":")) > 1 else "unknown"
        model = (s.get("model") or "unknown").split("/")[-1]
        updated_ms = s.get("updatedAt", 0)
        seconds_ago = int((now_ms - updated_ms) / 1000) if updated_ms else 9999

        if seconds_ago < 30:
            status = "active"
        elif seconds_ago < 300:
            status = "idle"
        else:
            status = "sleeping"

        last_active = ""
        if updated_ms:
            last_active = datetime.fromtimestamp(updated_ms / 1000, tz=UTC).strftime("%H:%M:%S")

        sessions.append(
            AgentSession(
                agent_id=agent_id,
                channel=channel,
                model=model,
                last_active=last_active,
                seconds_ago=seconds_ago,
                input_tokens=s.get("inputTokens", 0),
                output_tokens=s.get("outputTokens", 0),
                status=status,
            )
        )

    # Sort by most recently active
    sessions.sort(key=lambda x: x.seconds_ago)

    return LiveFeedResponse(
        sessions=sessions,
        timestamp=datetime.now(UTC).isoformat(),
    )
