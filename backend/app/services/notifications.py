"""Send notifications to the #notifications Discord channel.

Usage from any API route or service:

    from app.services.notifications import notify

    await notify(session, "🔔 APPROVAL NEEDED\\n\\nAction: trade.execute\\n...")

Posts directly to the Discord channel via the bot token.  Falls back silently
on failure so callers are never blocked by a notification issue.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import httpx

from app.core.logging import get_logger

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
NOTIFICATION_CHANNEL_ID = "1484731181995135156"


async def notify(session: AsyncSession, message: str) -> None:  # noqa: ARG001
    """Send a notification message to the #notifications Discord channel.

    Failures are logged but never raised — notifications must not block
    the calling operation.
    """
    if not DISCORD_BOT_TOKEN:
        logger.warning("notifications.no_bot_token: DISCORD_BOT_TOKEN not set")
        return
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://discord.com/api/v10/channels/{NOTIFICATION_CHANNEL_ID}/messages",
                headers={
                    "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={"content": message},
                timeout=10.0,
            )
            if resp.status_code >= 400:
                logger.error(
                    "notifications.discord_error status=%s body=%s",
                    resp.status_code,
                    resp.text[:200],
                )
    except Exception as exc:  # noqa: BLE001
        logger.error("notifications.send_failed error=%s", exc)
