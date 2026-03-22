"""OAuth token lifecycle management for Microsoft Graph connections."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from app.core.encryption import decrypt_token, encrypt_token
from app.core.logging import get_logger
from app.core.time import utcnow
from app.services.microsoft.graph_oauth import MicrosoftGraphOAuthProvider

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.microsoft_connection import MicrosoftConnection

logger = get_logger(__name__)

_EXPIRY_BUFFER = timedelta(minutes=5)
_provider = MicrosoftGraphOAuthProvider()


def store_graph_tokens(
    connection: MicrosoftConnection,
    *,
    access_token: str,
    refresh_token: str,
    expires_in: int,
) -> None:
    """Encrypt and persist OAuth tokens on a MicrosoftConnection."""
    connection.access_token_encrypted = encrypt_token(access_token)
    connection.refresh_token_encrypted = encrypt_token(refresh_token)
    connection.token_expires_at = utcnow() + timedelta(seconds=expires_in)
    connection.updated_at = utcnow()


async def get_valid_graph_token(
    session: AsyncSession,
    connection: MicrosoftConnection,
) -> str:
    """Return a valid access token, refreshing automatically if expired."""
    now = utcnow()
    if connection.token_expires_at and connection.token_expires_at > now + _EXPIRY_BUFFER:
        return decrypt_token(connection.access_token_encrypted)

    logger.info(
        "microsoft.token_manager.refreshing connection_id=%s",
        str(connection.id),
    )
    refresh_token = decrypt_token(connection.refresh_token_encrypted)
    new_access_token, expires_in = await _provider.refresh_access_token(refresh_token)

    store_graph_tokens(
        connection,
        access_token=new_access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )
    session.add(connection)
    await session.flush()

    return new_access_token
