"""OAuth token lifecycle management for connected email accounts."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from app.core.encryption import decrypt_token, encrypt_token
from app.core.logging import get_logger
from app.core.time import utcnow
from app.services.email.oauth import get_oauth_provider

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.email_accounts import EmailAccount

logger = get_logger(__name__)

# Refresh tokens 5 minutes before expiry to avoid edge-case failures.
_EXPIRY_BUFFER = timedelta(minutes=5)


def store_tokens(
    account: EmailAccount,
    *,
    access_token: str,
    refresh_token: str,
    expires_in: int,
) -> None:
    """Encrypt and persist OAuth tokens on an EmailAccount instance.

    The caller is responsible for flushing/committing the session.
    """
    account.access_token_encrypted = encrypt_token(access_token)
    account.refresh_token_encrypted = encrypt_token(refresh_token)
    account.token_expires_at = utcnow() + timedelta(seconds=expires_in)
    account.updated_at = utcnow()


async def get_valid_access_token(
    session: AsyncSession,
    account: EmailAccount,
) -> str:
    """Return a valid access token, refreshing automatically if expired.

    Updates the account row in-place and flushes (but does not commit).
    """
    now = utcnow()
    if account.token_expires_at and account.token_expires_at > now + _EXPIRY_BUFFER:
        return decrypt_token(account.access_token_encrypted)

    # Token is expired or about to expire — refresh it.
    logger.info(
        "email.token_manager.refreshing",
        extra={"account_id": str(account.id), "provider": account.provider},
    )
    refresh_token = decrypt_token(account.refresh_token_encrypted)
    provider = get_oauth_provider(account.provider)
    new_access_token, expires_in = await provider.refresh_access_token(refresh_token)

    store_tokens(
        account,
        access_token=new_access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )
    session.add(account)
    await session.flush()

    return new_access_token
