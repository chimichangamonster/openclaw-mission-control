"""WeCom access token lifecycle management.

WeCom API tokens expire after 7200 seconds (2 hours). This module handles
fetching, caching, and refreshing tokens per connection.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import httpx

from app.core.encryption import decrypt_token, encrypt_token
from app.core.logging import get_logger
from app.core.time import utcnow

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.wecom_connection import WeComConnection

logger = get_logger(__name__)

WECOM_TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
TOKEN_REFRESH_MARGIN = timedelta(minutes=5)


class WeComTokenError(Exception):
    """Raised when access token retrieval fails."""


async def get_access_token(
    connection: "WeComConnection",
    session: "AsyncSession",
) -> str:
    """Return a valid access token, refreshing from WeCom API if needed.

    Updates the connection row in-place and flushes to DB.
    """
    # Check cached token
    if (
        connection.access_token_encrypted
        and connection.access_token_expires_at
        and connection.access_token_expires_at > utcnow() + TOKEN_REFRESH_MARGIN
    ):
        return decrypt_token(connection.access_token_encrypted)

    # Refresh from WeCom API
    if not connection.corp_secret_encrypted:
        raise WeComTokenError("Corp secret not configured — cannot fetch access token")

    corp_secret = decrypt_token(connection.corp_secret_encrypted)

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            WECOM_TOKEN_URL,
            params={"corpid": connection.corp_id, "corpsecret": corp_secret},
        )
        resp.raise_for_status()
        data = resp.json()

    errcode = data.get("errcode", 0)
    if errcode != 0:
        errmsg = data.get("errmsg", "unknown")
        logger.error(
            "wecom.access_token.error corp_id=%s errcode=%s errmsg=%s",
            connection.corp_id,
            errcode,
            errmsg,
        )
        raise WeComTokenError(f"WeCom API error {errcode}: {errmsg}")

    access_token = data["access_token"]
    expires_in = data.get("expires_in", 7200)

    connection.access_token_encrypted = encrypt_token(access_token)
    connection.access_token_expires_at = utcnow() + timedelta(seconds=expires_in)
    session.add(connection)
    await session.flush()

    logger.info(
        "wecom.access_token.refreshed corp_id=%s expires_in=%s",
        connection.corp_id,
        expires_in,
    )

    return access_token
