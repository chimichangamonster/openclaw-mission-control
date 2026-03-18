"""Polymarket wallet storage and CLOB client instantiation."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from eth_account import Account

from app.core.config import settings
from app.core.encryption import decrypt_token, encrypt_token
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.polymarket_wallets import PolymarketWallet

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)


async def store_wallet(
    session: AsyncSession,
    org_id: str,
    private_key: str,
    label: str,
) -> PolymarketWallet:
    """Encrypt and store a wallet private key, derive the public address."""
    account = Account.from_key(private_key)
    wallet_address = account.address

    from sqlalchemy import select

    stmt = select(PolymarketWallet).where(PolymarketWallet.organization_id == org_id)
    existing = (await session.execute(stmt)).scalar_one_or_none()

    now = utcnow()
    if existing:
        wallet = existing
        wallet.updated_at = now
    else:
        wallet = PolymarketWallet(
            id=uuid4(),
            organization_id=org_id,
            created_at=now,
            updated_at=now,
        )

    wallet.label = label
    wallet.wallet_address = wallet_address
    wallet.private_key_encrypted = encrypt_token(private_key)
    wallet.is_active = True
    # Clear stale API credentials — will be re-derived
    wallet.api_key_encrypted = ""
    wallet.api_secret_encrypted = ""
    wallet.api_passphrase_encrypted = ""
    wallet.api_credentials_derived_at = None

    session.add(wallet)
    await session.flush()
    return wallet


async def derive_api_credentials(
    session: AsyncSession,
    wallet: PolymarketWallet,
) -> None:
    """Derive L2 CLOB API credentials from the wallet's private key."""
    from py_clob_client.client import ClobClient

    private_key = decrypt_token(wallet.private_key_encrypted)
    client = ClobClient(
        settings.polymarket_clob_base_url,
        key=private_key,
        chain_id=settings.polymarket_chain_id,
    )
    creds = client.create_or_derive_api_creds()

    wallet.api_key_encrypted = encrypt_token(creds.api_key)
    wallet.api_secret_encrypted = encrypt_token(creds.api_secret)
    wallet.api_passphrase_encrypted = encrypt_token(creds.api_passphrase)
    wallet.api_credentials_derived_at = utcnow()
    wallet.updated_at = utcnow()

    session.add(wallet)
    await session.flush()

    logger.info(
        "polymarket.credentials.derived",
        extra={"wallet_id": str(wallet.id), "address": wallet.wallet_address},
    )


def get_clob_client(wallet: PolymarketWallet) -> "ClobClient":
    """Instantiate a configured ClobClient from an encrypted wallet."""
    from py_clob_client.client import ClobClient

    private_key = decrypt_token(wallet.private_key_encrypted)
    client = ClobClient(
        settings.polymarket_clob_base_url,
        key=private_key,
        chain_id=settings.polymarket_chain_id,
    )

    if wallet.api_key_encrypted:
        from py_clob_client.clob_types import ApiCreds

        client.set_api_creds(
            ApiCreds(
                api_key=decrypt_token(wallet.api_key_encrypted),
                api_secret=decrypt_token(wallet.api_secret_encrypted),
                api_passphrase=decrypt_token(wallet.api_passphrase_encrypted),
            )
        )
    return client
