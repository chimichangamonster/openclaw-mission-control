"""Binance exchange account storage and client instantiation."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from binance.client import Client as BinanceClient

from app.core.encryption import decrypt_token, encrypt_token
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.exchange_accounts import ExchangeAccount

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)


async def store_exchange_account(
    session: AsyncSession,
    org_id: str,
    *,
    exchange: str,
    api_key: str,
    api_secret: str,
    label: str,
) -> ExchangeAccount:
    """Encrypt and store exchange API credentials."""
    from sqlalchemy import select

    stmt = select(ExchangeAccount).where(
        ExchangeAccount.organization_id == org_id,
        ExchangeAccount.exchange == exchange,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()

    now = utcnow()
    if existing:
        account = existing
        account.updated_at = now
    else:
        account = ExchangeAccount(
            id=uuid4(),
            organization_id=org_id,
            exchange=exchange,
            created_at=now,
            updated_at=now,
        )

    account.label = label
    account.api_key_encrypted = encrypt_token(api_key)
    account.api_secret_encrypted = encrypt_token(api_secret)
    account.is_active = True
    account.last_error = None

    # Test connectivity
    try:
        client = BinanceClient(api_key, api_secret)
        client.get_account()
        account.last_connected_at = now
    except Exception as exc:
        account.last_error = f"Connection test failed: {str(exc)[:200]}"
        logger.warning(
            "binance.credentials.test_failed",
            extra={"error": str(exc)[:200]},
        )

    session.add(account)
    await session.flush()
    return account


def get_binance_client(account: ExchangeAccount) -> BinanceClient:
    """Instantiate a Binance client from encrypted credentials."""
    api_key = decrypt_token(account.api_key_encrypted)
    api_secret = decrypt_token(account.api_secret_encrypted)
    return BinanceClient(api_key, api_secret)
