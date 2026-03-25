"""WeCom message delivery service — find org's WeCom connection and send messages.

Parallel to ``email_send.py`` but for WeCom (Enterprise WeChat) delivery.
Supports text messages, news cards (rich link), and file attachments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.logging import get_logger
from app.models.wecom_connection import WeComConnection

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)


class NoWeComConnectionError(Exception):
    """No active WeCom connection is available for the organization."""


async def get_org_wecom_connection(
    session: AsyncSession,
    organization_id: UUID,
) -> WeComConnection:
    """Return the first active WeCom connection for the org.

    Raises ``NoWeComConnectionError`` when none is found.
    """
    stmt = (
        select(WeComConnection)
        .where(
            WeComConnection.organization_id == organization_id,
            WeComConnection.is_active == True,  # noqa: E712
        )
        .order_by(WeComConnection.created_at)
        .limit(1)
    )
    result = await session.execute(stmt)
    connection = result.scalars().first()
    if connection is None:
        raise NoWeComConnectionError(
            "No active WeCom connection for this organization."
        )
    return connection


async def send_wecom_text(
    session: AsyncSession,
    connection: WeComConnection,
    *,
    to_user: str,
    content: str,
) -> bool:
    """Send a plain text message to a WeCom user.

    Args:
        session: DB session (for token refresh).
        connection: The WeComConnection to use.
        to_user: WeCom user ID (or ``"@all"`` for broadcast).
        content: Text message content.

    Returns:
        True on success, False on failure.
    """
    from app.services.wecom.reply import send_active_reply

    return await send_active_reply(
        content=content,
        to_user=to_user,
        connection=connection,
        session=session,
    )


async def send_wecom_news(
    session: AsyncSession,
    connection: WeComConnection,
    *,
    to_user: str,
    title: str,
    description: str,
    url: str,
    pic_url: str = "",
) -> bool:
    """Send a rich link card (news message) to a WeCom user.

    This is the preferred method for delivering documents, invoices, and
    download links — the card shows title, description, and a tappable URL.

    Args:
        session: DB session (for token refresh).
        connection: The WeComConnection to use.
        to_user: WeCom user ID (or ``"@all"`` for broadcast).
        title: Card title (e.g., "Invoice #INV-001").
        description: Card description (e.g., "Amount: $1,500.00 — Due: April 15").
        url: Download URL for the document.
        pic_url: Optional thumbnail image URL.

    Returns:
        True on success, False on failure.
    """
    from app.services.wecom.reply import send_news_message

    return await send_news_message(
        to_user=to_user,
        title=title,
        description=description,
        url=url,
        pic_url=pic_url,
        connection=connection,
        session=session,
    )


async def send_wecom_file(
    session: AsyncSession,
    connection: WeComConnection,
    *,
    to_user: str,
    file_bytes: bytes,
    filename: str,
) -> bool:
    """Upload and send a file directly to a WeCom user.

    Uploads to WeCom's temporary media library, then sends as a file message.
    Prefer ``send_wecom_news`` with a download URL when possible.

    Args:
        session: DB session (for token refresh).
        connection: The WeComConnection to use.
        to_user: WeCom user ID.
        file_bytes: File content bytes.
        filename: Display filename.

    Returns:
        True on success, False on failure.
    """
    from app.services.wecom.reply import send_file_message

    return await send_file_message(
        to_user=to_user,
        file_bytes=file_bytes,
        filename=filename,
        connection=connection,
        session=session,
    )
