#!/usr/bin/env python3
"""One-time migration: re-encrypt all Fernet-encrypted secrets to AES-256-GCM.

Safe to run multiple times — skips values already in v1: format.

Usage:
    cd mission-control/backend
    python scripts/migrate_fernet_to_aes256.py [--dry-run]

Requires DATABASE_URL and ENCRYPTION_KEY env vars (or .env.production).
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.encryption import re_encrypt

# ---------------------------------------------------------------------------
# Every (table, column) pair that stores Fernet-encrypted data
# ---------------------------------------------------------------------------

ENCRYPTED_COLUMNS: list[tuple[str, str]] = [
    # OrganizationSettings
    ("organization_settings", "openrouter_api_key_encrypted"),
    ("organization_settings", "openrouter_management_key_encrypted"),
    ("organization_settings", "adobe_pdf_client_id_encrypted"),
    ("organization_settings", "adobe_pdf_client_secret_encrypted"),
    ("organization_settings", "custom_llm_api_key_encrypted"),
    # EmailAccount
    ("email_accounts", "access_token_encrypted"),
    ("email_accounts", "refresh_token_encrypted"),
    # MicrosoftConnection
    ("microsoft_connections", "access_token_encrypted"),
    ("microsoft_connections", "refresh_token_encrypted"),
    # GoogleCalendarConnection
    ("google_calendar_connections", "access_token_encrypted"),
    ("google_calendar_connections", "refresh_token_encrypted"),
    # WeComConnection
    ("wecom_connections", "corp_secret_encrypted"),
    ("wecom_connections", "access_token_encrypted"),
    # PolymarketWallet
    ("polymarket_wallets", "private_key_encrypted"),
    ("polymarket_wallets", "api_key_encrypted"),
    ("polymarket_wallets", "api_secret_encrypted"),
    ("polymarket_wallets", "api_passphrase_encrypted"),
    # ExchangeAccount
    ("exchange_accounts", "api_key_encrypted"),
    ("exchange_accounts", "api_secret_encrypted"),
]


@dataclass
class Stats:
    skipped: int = 0
    migrated: int = 0
    errors: int = 0
    empty: int = 0


async def migrate(dry_run: bool = False) -> None:
    db_url = settings.database_url
    if not db_url:
        print("ERROR: DATABASE_URL not set.")
        sys.exit(1)

    # Ensure async driver
    if "postgresql://" in db_url and "+asyncpg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")

    engine = create_async_engine(db_url)
    stats = Stats()

    async with engine.begin() as conn:
        for table, column in ENCRYPTED_COLUMNS:
            # Check if table exists
            check = await conn.execute(
                text(
                    "SELECT EXISTS ("
                    "  SELECT 1 FROM information_schema.tables"
                    "  WHERE table_name = :table"
                    ")"
                ),
                {"table": table},
            )
            if not check.scalar():
                print(f"  SKIP {table}.{column} — table does not exist")
                continue

            rows = await conn.execute(
                text(f'SELECT id, "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL')
            )
            for row in rows:
                row_id, ciphertext = row[0], row[1]
                if not ciphertext:
                    stats.empty += 1
                    continue
                if ciphertext.startswith("v1:"):
                    stats.skipped += 1
                    continue
                try:
                    new_ct = re_encrypt(ciphertext)
                    if new_ct and not dry_run:
                        await conn.execute(
                            text(f'UPDATE "{table}" SET "{column}" = :ct WHERE id = :id'),
                            {"ct": new_ct, "id": row_id},
                        )
                    stats.migrated += 1
                    print(f"  {'[DRY RUN] ' if dry_run else ''}Migrated {table}.{column} id={row_id}")
                except Exception as e:
                    stats.errors += 1
                    print(f"  ERROR {table}.{column} id={row_id}: {e}")

    await engine.dispose()
    print(f"\nDone. Migrated={stats.migrated} Skipped={stats.skipped} Errors={stats.errors} Empty={stats.empty}")
    if stats.errors:
        sys.exit(1)


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("=== DRY RUN — no data will be modified ===\n")
    asyncio.run(migrate(dry_run=dry_run))
