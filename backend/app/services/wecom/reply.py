"""WeCom outbound reply methods.

Two reply paths:
1. Passive reply — synchronous XML response to WeCom within 5 seconds
2. Active reply — async push via WeCom API (for slow agent responses)
"""

from __future__ import annotations

import hashlib
import time
from typing import TYPE_CHECKING

import httpx

from app.core.logging import get_logger
from app.services.wecom.crypto import encrypt_message

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.wecom_connection import WeComConnection

logger = get_logger(__name__)

WECOM_SEND_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send"


def build_passive_reply(
    *,
    content: str,
    connection: "WeComConnection",
    nonce: str,
    timestamp: str = "",
) -> str:
    """Build an encrypted XML reply for synchronous passive response."""
    ts = timestamp or str(int(time.time()))

    encrypted = encrypt_message(
        connection.encoding_aes_key,
        connection.corp_id,
        content,
    )

    # Sign the reply
    parts = sorted([connection.callback_token, ts, nonce, encrypted])
    signature = hashlib.sha1("".join(parts).encode()).hexdigest()

    from app.services.wecom.xml_parser import build_encrypted_reply_xml

    return build_encrypted_reply_xml(
        encrypt=encrypted,
        signature=signature,
        timestamp=ts,
        nonce=nonce,
    )


async def send_active_reply(
    *,
    content: str,
    to_user: str,
    connection: "WeComConnection",
    session: "AsyncSession",
) -> bool:
    """Send an async text reply via WeCom's message/send API.

    Returns True on success, False on failure.
    """
    from app.services.wecom.access_token import get_access_token, WeComTokenError

    try:
        access_token = await get_access_token(connection, session)
    except WeComTokenError as exc:
        logger.error("wecom.reply.token_error error=%s", str(exc)[:200])
        return False

    payload = {
        "touser": to_user,
        "msgtype": "text",
        "agentid": int(connection.agent_id) if connection.agent_id else 0,
        "text": {"content": content},
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                WECOM_SEND_URL,
                params={"access_token": access_token},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        errcode = data.get("errcode", 0)
        if errcode != 0:
            logger.error(
                "wecom.reply.api_error to_user=%s errcode=%s errmsg=%s",
                to_user,
                errcode,
                data.get("errmsg", ""),
            )
            return False

        logger.info("wecom.reply.sent to_user=%s len=%d", to_user, len(content))
        return True

    except Exception as exc:
        logger.error(
            "wecom.reply.failed to_user=%s error=%s",
            to_user,
            str(exc)[:200],
        )
        return False
