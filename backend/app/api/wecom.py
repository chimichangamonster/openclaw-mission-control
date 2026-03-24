"""WeCom (Enterprise WeChat) integration — config CRUD and callback endpoint."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from sqlmodel import col, select

from app.api.deps import ORG_MEMBER_DEP, ORG_RATE_LIMIT_DEP, SESSION_DEP, require_feature
from app.core.config import settings
from app.core.encryption import encrypt_token
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.gateways import Gateway
from app.models.organization_settings import DEFAULT_FEATURE_FLAGS, OrganizationSettings
from app.models.organizations import Organization
from app.models.wecom_connection import WeComConnection
from app.schemas.wecom import (
    WeComConnectionCreate,
    WeComConnectionResponse,
    WeComConnectionUpdate,
    WeComTestResult,
)
from app.services.organizations import OrganizationContext, is_org_admin
from app.services.wecom.crypto import WeComCryptoError, check_timestamp, verify_signature
from app.services.wecom.message_handler import handle_message
from app.services.wecom.reply import build_passive_reply, send_active_reply
from app.services.wecom.xml_parser import parse_inbound_message

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)
router = APIRouter(prefix="/wecom", tags=["wecom"])

_AUTH_DEPS = [Depends(require_feature("wechat")), ORG_RATE_LIMIT_DEP]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_response(conn: WeComConnection, org_slug: str) -> WeComConnectionResponse:
    """Convert a WeComConnection to an API response with computed callback URL."""
    # The callback URL WeCom should POST to — uses env or Tailscale default
    base_url = getattr(settings, "wecom_callback_base_url", "") or "https://vantageclaw.basa-dab.ts.net:8443"
    callback_url = f"{base_url}/api/v1/wecom/{org_slug}/callback"
    return WeComConnectionResponse(
        id=conn.id,
        organization_id=conn.organization_id,
        corp_id=conn.corp_id,
        agent_id=conn.agent_id,
        callback_token=conn.callback_token,
        has_corp_secret=bool(conn.corp_secret_encrypted),
        target_agent_id=conn.target_agent_id,
        target_channel=conn.target_channel,
        label=conn.label,
        is_active=conn.is_active,
        callback_url=callback_url,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


def _require_admin(ctx: OrganizationContext) -> None:
    if not is_org_admin(ctx.member):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")


async def _get_connection_or_404(
    connection_id: UUID,
    org_id: UUID,
    session: "AsyncSession",
) -> WeComConnection:
    result = await session.execute(
        select(WeComConnection).where(
            WeComConnection.id == connection_id,
            WeComConnection.organization_id == org_id,
        )
    )
    conn = result.scalars().first()
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WeCom connection not found")
    return conn


# ---------------------------------------------------------------------------
# Config CRUD (authenticated, admin-gated)
# ---------------------------------------------------------------------------


@router.get("/connections", dependencies=_AUTH_DEPS)
async def list_connections(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: "AsyncSession" = SESSION_DEP,
) -> list[WeComConnectionResponse]:
    """List WeCom connections for the current org."""
    result = await session.execute(
        select(WeComConnection)
        .where(WeComConnection.organization_id == ctx.organization.id)
        .order_by(col(WeComConnection.created_at).desc())
    )
    connections = result.scalars().all()
    slug = ctx.organization.slug or str(ctx.organization.id)
    return [_to_response(c, slug) for c in connections]


@router.post(
    "/connections",
    dependencies=_AUTH_DEPS,
    status_code=status.HTTP_201_CREATED,
)
async def create_connection(
    body: WeComConnectionCreate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: "AsyncSession" = SESSION_DEP,
) -> WeComConnectionResponse:
    """Create a new WeCom connection for the current org. Requires admin."""
    _require_admin(ctx)

    conn = WeComConnection(
        organization_id=ctx.organization.id,
        user_id=ctx.member.user_id,
        corp_id=body.corp_id,
        agent_id=body.agent_id,
        callback_token=body.callback_token,
        encoding_aes_key=body.encoding_aes_key,
        corp_secret_encrypted=encrypt_token(body.corp_secret) if body.corp_secret else None,
        target_agent_id=body.target_agent_id,
        target_channel=body.target_channel,
        label=body.label,
    )
    session.add(conn)
    await session.commit()
    await session.refresh(conn)

    slug = ctx.organization.slug or str(ctx.organization.id)
    logger.info(
        "wecom.connection.created org_id=%s corp_id=%s",
        ctx.organization.id,
        body.corp_id,
    )
    return _to_response(conn, slug)


@router.patch("/connections/{connection_id}", dependencies=_AUTH_DEPS)
async def update_connection(
    connection_id: UUID,
    body: WeComConnectionUpdate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: "AsyncSession" = SESSION_DEP,
) -> WeComConnectionResponse:
    """Update an existing WeCom connection. Requires admin."""
    _require_admin(ctx)
    conn = await _get_connection_or_404(connection_id, ctx.organization.id, session)

    if body.agent_id is not None:
        conn.agent_id = body.agent_id
    if body.callback_token is not None:
        conn.callback_token = body.callback_token
    if body.encoding_aes_key is not None:
        conn.encoding_aes_key = body.encoding_aes_key
    if body.corp_secret is not None:
        conn.corp_secret_encrypted = encrypt_token(body.corp_secret) if body.corp_secret else None
    if body.target_agent_id is not None:
        conn.target_agent_id = body.target_agent_id
    if body.target_channel is not None:
        conn.target_channel = body.target_channel
    if body.label is not None:
        conn.label = body.label
    if body.is_active is not None:
        conn.is_active = body.is_active

    conn.updated_at = utcnow()
    session.add(conn)
    await session.commit()
    await session.refresh(conn)

    slug = ctx.organization.slug or str(ctx.organization.id)
    return _to_response(conn, slug)


@router.delete(
    "/connections/{connection_id}",
    dependencies=_AUTH_DEPS,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_connection(
    connection_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: "AsyncSession" = SESSION_DEP,
) -> None:
    """Delete a WeCom connection. Requires admin."""
    _require_admin(ctx)
    conn = await _get_connection_or_404(connection_id, ctx.organization.id, session)
    await session.delete(conn)
    await session.commit()
    logger.info("wecom.connection.deleted org_id=%s id=%s", ctx.organization.id, connection_id)


@router.post("/connections/{connection_id}/test", dependencies=_AUTH_DEPS)
async def test_connection(
    connection_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: "AsyncSession" = SESSION_DEP,
) -> WeComTestResult:
    """Test WeCom API connectivity using stored credentials."""
    _require_admin(ctx)
    conn = await _get_connection_or_404(connection_id, ctx.organization.id, session)

    if not conn.corp_secret_encrypted:
        return WeComTestResult(success=False, message="No corp secret configured")

    try:
        from app.services.wecom.access_token import get_access_token

        token = await get_access_token(conn, session)
        await session.commit()
        return WeComTestResult(
            success=True,
            message=f"Connected — access token obtained (expires at {conn.access_token_expires_at})",
        )
    except Exception as exc:
        return WeComTestResult(success=False, message=str(exc)[:300])


# ---------------------------------------------------------------------------
# Callback endpoint (unauthenticated — called by WeCom servers)
# ---------------------------------------------------------------------------


@router.get("/{org_slug}/callback", include_in_schema=False)
async def wecom_url_verification(
    org_slug: str,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
    session: "AsyncSession" = SESSION_DEP,
) -> PlainTextResponse:
    """WeCom URL verification — returns decrypted echostr to prove ownership."""
    org, conn = await _resolve_callback_context(org_slug, session)
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    try:
        verify_signature(
            conn.callback_token,
            timestamp,
            nonce,
            msg_encrypt=echostr,
            signature=msg_signature,
        )
        # Decrypt echostr
        from app.services.wecom.crypto import decrypt_message

        echo_plain = decrypt_message(conn.encoding_aes_key, echostr, conn.corp_id)
        return PlainTextResponse(echo_plain)
    except WeComCryptoError as exc:
        logger.warning("wecom.callback.verify_failed org=%s error=%s", org_slug, str(exc))
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Signature verification failed")


@router.post("/{org_slug}/callback", include_in_schema=False)
async def wecom_callback(
    org_slug: str,
    request: Request,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    session: "AsyncSession" = SESSION_DEP,
) -> Response:
    """Handle inbound WeCom messages."""
    org, conn = await _resolve_callback_context(org_slug, session)
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # Read XML body
    body = await request.body()
    if not body:
        return Response(content="success", media_type="text/plain")

    # Parse outer XML to get Encrypt field
    parsed = parse_inbound_message(body)

    # Verify signature
    try:
        verify_signature(
            conn.callback_token,
            timestamp,
            nonce,
            msg_encrypt=parsed.encrypt,
            signature=msg_signature,
        )
        check_timestamp(timestamp)
    except WeComCryptoError as exc:
        logger.warning("wecom.callback.verify_failed org=%s error=%s", org_slug, str(exc))
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    # Decrypt the message
    try:
        from app.services.wecom.crypto import decrypt_message

        decrypted_xml = decrypt_message(conn.encoding_aes_key, parsed.encrypt, conn.corp_id)
        inner_parsed = parse_inbound_message(decrypted_xml.encode("utf-8"))
    except WeComCryptoError as exc:
        logger.error("wecom.callback.decrypt_failed org=%s error=%s", org_slug, str(exc))
        return Response(content="success", media_type="text/plain")

    # Only handle text messages for now
    if inner_parsed.msg_type != "text":
        logger.info(
            "wecom.callback.skip_non_text org=%s type=%s",
            org_slug,
            inner_parsed.msg_type,
        )
        return Response(content="success", media_type="text/plain")

    if not inner_parsed.content.strip():
        return Response(content="success", media_type="text/plain")

    # Resolve gateway for org
    gateway = await _resolve_gateway(org, session)
    if not gateway:
        logger.warning("wecom.callback.no_gateway org=%s", org_slug)
        return Response(content="success", media_type="text/plain")

    # Try synchronous response (within WeCom's 5-second window)
    response_text = await handle_message(
        connection=conn,
        gateway=gateway,
        from_user=inner_parsed.from_user,
        content=inner_parsed.content,
    )

    if response_text:
        # Passive encrypted reply
        reply_xml = build_passive_reply(
            content=response_text,
            connection=conn,
            nonce=nonce,
            timestamp=timestamp,
        )
        return Response(content=reply_xml, media_type="application/xml")

    # Agent didn't respond in time — send async reply in background
    asyncio.create_task(
        _async_reply_worker(
            conn=conn,
            gateway=gateway,
            from_user=inner_parsed.from_user,
            content=inner_parsed.content,
            session_factory=session,
        )
    )
    return Response(content="success", media_type="text/plain")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _resolve_callback_context(
    org_slug: str,
    session: "AsyncSession",
) -> tuple[Organization | None, WeComConnection | None]:
    """Resolve org and active WeCom connection from org slug."""
    result = await session.execute(
        select(Organization).where(Organization.slug == org_slug)
    )
    org = result.scalars().first()
    if not org:
        return None, None

    # Check wechat feature flag
    settings_result = await session.execute(
        select(OrganizationSettings).where(
            OrganizationSettings.organization_id == org.id
        )
    )
    org_settings = settings_result.scalars().first()
    if org_settings:
        flags = org_settings.feature_flags
    else:
        flags = dict(DEFAULT_FEATURE_FLAGS)

    if not flags.get("wechat", False):
        return org, None

    # Get active connection
    conn_result = await session.execute(
        select(WeComConnection).where(
            WeComConnection.organization_id == org.id,
            WeComConnection.is_active == True,  # noqa: E712
        )
    )
    conn = conn_result.scalars().first()
    return org, conn


async def _resolve_gateway(
    org: Organization,
    session: "AsyncSession",
) -> Gateway | None:
    """Get the gateway for an organization."""
    result = await session.execute(
        select(Gateway).where(Gateway.organization_id == org.id)
    )
    return result.scalars().first()


async def _async_reply_worker(
    *,
    conn: WeComConnection,
    gateway: Gateway,
    from_user: str,
    content: str,
    session_factory: "AsyncSession",
) -> None:
    """Background task: wait for agent response and send via WeCom API."""
    import asyncio

    from app.db.session import async_session_maker
    from app.services.wecom.message_handler import POLL_INTERVAL_SECONDS

    # Wait longer for the async path
    max_wait = 30.0
    elapsed = 4.0  # we already waited ~4s in sync path

    while elapsed < max_wait:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS

        try:
            from app.services.openclaw.gateway_resolver import gateway_client_config
            from app.services.openclaw.gateway_rpc import get_chat_history

            config = gateway_client_config(gateway)
            agent_id = conn.target_agent_id or "the-claw"
            session_key = f"agent:{agent_id}:wecom-{from_user}"

            history = await get_chat_history(session_key, config, limit=5)
            if not isinstance(history, dict):
                continue

            messages = history.get("messages", [])
            for msg in reversed(messages):
                if msg.get("role") == "assistant" and msg.get("content", "").strip():
                    # Found a response — send it
                    async with async_session_maker() as db_session:
                        # Re-fetch connection to get current token
                        result = await db_session.execute(
                            select(WeComConnection).where(WeComConnection.id == conn.id)
                        )
                        fresh_conn = result.scalars().first()
                        if fresh_conn:
                            await send_active_reply(
                                content=msg["content"],
                                to_user=from_user,
                                connection=fresh_conn,
                                session=db_session,
                            )
                            await db_session.commit()
                    return
        except Exception as exc:
            logger.error("wecom.async_reply.error from_user=%s error=%s", from_user, str(exc)[:200])

    logger.warning("wecom.async_reply.timeout from_user=%s", from_user)
