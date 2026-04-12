"""WeCom outbound reply methods.

Three message types:
1. Passive reply — synchronous XML response to WeCom within 5 seconds
2. Active reply — async text push via WeCom API (for slow agent responses)
3. News message — rich link card with title, description, and URL (for documents/invoices)
"""

from __future__ import annotations

import hashlib
import time
from typing import TYPE_CHECKING, Any

import httpx

from app.core.logging import get_logger
from app.services.wecom.crypto import encrypt_message

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.wecom_connection import WeComConnection

logger = get_logger(__name__)

WECOM_SEND_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send"
WECOM_MEDIA_UPLOAD_URL = "https://qyapi.weixin.qq.com/cgi-bin/media/upload"


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
    from app.services.wecom.access_token import WeComTokenError, get_access_token

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


async def send_news_message(
    *,
    to_user: str,
    title: str,
    description: str,
    url: str,
    pic_url: str = "",
    connection: "WeComConnection",
    session: "AsyncSession",
) -> bool:
    """Send a rich link card (news message) via WeCom API.

    This is the preferred way to deliver documents, invoices, and other files
    to WeCom users — the card shows a title, description, and tappable URL.

    Returns True on success, False on failure.
    """
    from app.services.wecom.access_token import WeComTokenError, get_access_token

    try:
        access_token = await get_access_token(connection, session)
    except WeComTokenError as exc:
        logger.error("wecom.news.token_error error=%s", str(exc)[:200])
        return False

    article: dict[str, Any] = {
        "title": title,
        "description": description,
        "url": url,
    }
    if pic_url:
        article["picurl"] = pic_url

    payload = {
        "touser": to_user,
        "msgtype": "news",
        "agentid": int(connection.agent_id) if connection.agent_id else 0,
        "news": {"articles": [article]},
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
                "wecom.news.api_error to_user=%s errcode=%s errmsg=%s",
                to_user,
                errcode,
                data.get("errmsg", ""),
            )
            return False

        logger.info(
            "wecom.news.sent to_user=%s title=%s",
            to_user,
            title[:60],
        )
        return True

    except Exception as exc:
        logger.error(
            "wecom.news.failed to_user=%s error=%s",
            to_user,
            str(exc)[:200],
        )
        return False


async def send_file_message(
    *,
    to_user: str,
    file_bytes: bytes,
    filename: str,
    connection: "WeComConnection",
    session: "AsyncSession",
) -> bool:
    """Upload a file to WeCom's media library and send it as a file message.

    Use ``send_news_message`` for link-based delivery instead when a download
    URL is available — it avoids the extra media upload step.

    Returns True on success, False on failure.
    """
    from app.services.wecom.access_token import WeComTokenError, get_access_token

    try:
        access_token = await get_access_token(connection, session)
    except WeComTokenError as exc:
        logger.error("wecom.file.token_error error=%s", str(exc)[:200])
        return False

    # Step 1: upload to WeCom temporary media library
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                WECOM_MEDIA_UPLOAD_URL,
                params={"access_token": access_token, "type": "file"},
                files={"media": (filename, file_bytes)},
            )
            resp.raise_for_status()
            upload_data = resp.json()

        if upload_data.get("errcode", 0) != 0:
            logger.error(
                "wecom.file.upload_error errcode=%s errmsg=%s",
                upload_data.get("errcode"),
                upload_data.get("errmsg", ""),
            )
            return False

        media_id = upload_data.get("media_id")
        if not media_id:
            logger.error("wecom.file.no_media_id response=%s", upload_data)
            return False

    except Exception as exc:
        logger.error("wecom.file.upload_failed error=%s", str(exc)[:200])
        return False

    # Step 2: send file message using media_id
    payload = {
        "touser": to_user,
        "msgtype": "file",
        "agentid": int(connection.agent_id) if connection.agent_id else 0,
        "file": {"media_id": media_id},
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
                "wecom.file.send_error to_user=%s errcode=%s errmsg=%s",
                to_user,
                errcode,
                data.get("errmsg", ""),
            )
            return False

        logger.info(
            "wecom.file.sent to_user=%s filename=%s media_id=%s",
            to_user,
            filename,
            media_id,
        )
        return True

    except Exception as exc:
        logger.error(
            "wecom.file.send_failed to_user=%s error=%s",
            to_user,
            str(exc)[:200],
        )
        return False
