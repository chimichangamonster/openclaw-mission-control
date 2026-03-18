"""Email sync orchestrator — fetches new messages from provider APIs."""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.email_accounts import EmailAccount
from app.models.email_attachments import EmailAttachment
from app.models.email_messages import EmailMessage
from app.services.email.queue import QueuedEmailSync, enqueue_email_sync
from app.services.email.token_manager import get_valid_access_token
from app.services.email.types import RawEmailMessage

logger = get_logger(__name__)


async def _save_message(
    session: AsyncSession,
    account: EmailAccount,
    raw: RawEmailMessage,
) -> EmailMessage | None:
    """Persist a raw email message, deduplicating by provider_message_id."""
    stmt = select(EmailMessage).where(
        EmailMessage.email_account_id == account.id,
        EmailMessage.provider_message_id == raw.provider_message_id,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        return None

    now = utcnow()
    msg = EmailMessage(
        id=uuid4(),
        organization_id=account.organization_id,
        email_account_id=account.id,
        provider_message_id=raw.provider_message_id,
        thread_id=raw.thread_id,
        subject=raw.subject,
        sender_email=raw.sender_email,
        sender_name=raw.sender_name,
        recipients_to=raw.recipients_to,
        recipients_cc=raw.recipients_cc,
        body_text=raw.body_text,
        body_html=raw.body_html,
        received_at=raw.received_at,
        is_read=raw.is_read,
        folder=raw.folder,
        labels=raw.labels,
        has_attachments=raw.has_attachments,
        synced_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(msg)

    for att in raw.attachments:
        session.add(
            EmailAttachment(
                id=uuid4(),
                email_message_id=msg.id,
                filename=att.filename,
                content_type=att.content_type,
                size_bytes=att.size_bytes,
                provider_attachment_id=att.provider_attachment_id,
                created_at=now,
            )
        )
    return msg


async def sync_email_account(email_account_id: UUID) -> int:
    """Sync messages for a single email account. Returns count of new messages."""
    async with async_session_maker() as session:
        account = await session.get(EmailAccount, email_account_id)
        if account is None:
            logger.warning("email.sync.account_missing", extra={"id": str(email_account_id)})
            return 0
        if not account.sync_enabled:
            return 0

        try:
            access_token = await get_valid_access_token(session, account)
        except Exception as exc:
            account.last_sync_error = f"Token refresh failed: {exc}"
            account.updated_at = utcnow()
            session.add(account)
            await session.commit()
            logger.exception(
                "email.sync.token_failed",
                extra={"account_id": str(account.id)},
            )
            return 0

        try:
            raw_messages = await _fetch_from_provider(access_token, account)
        except Exception as exc:
            account.last_sync_error = f"Fetch failed: {exc}"
            account.updated_at = utcnow()
            session.add(account)
            await session.commit()
            logger.exception(
                "email.sync.fetch_failed",
                extra={"account_id": str(account.id)},
            )
            return 0

        new_count = 0
        for raw in raw_messages:
            saved = await _save_message(session, account, raw)
            if saved:
                new_count += 1

        account.last_sync_at = utcnow()
        account.last_sync_error = None
        account.updated_at = utcnow()
        session.add(account)
        await session.commit()

        logger.info(
            "email.sync.complete",
            extra={
                "account_id": str(account.id),
                "provider": account.provider,
                "fetched": len(raw_messages),
                "new": new_count,
            },
        )
        return new_count


async def _fetch_from_provider(
    access_token: str,
    account: EmailAccount,
) -> list[RawEmailMessage]:
    """Dispatch to the correct provider's fetch function."""
    if account.provider == "zoho":
        from app.services.email.providers.zoho import fetch_messages

        return await fetch_messages(
            access_token,
            account.provider_account_id or "",
            from_message_id=account.sync_cursor,
        )
    elif account.provider == "microsoft":
        from app.services.email.providers.microsoft import fetch_messages

        messages, next_delta = await fetch_messages(
            access_token,
            delta_link=account.sync_cursor,
        )
        if next_delta:
            account.sync_cursor = next_delta
        return messages
    else:
        raise ValueError(f"Unknown provider: {account.provider}")


async def sync_all_active_accounts() -> int:
    """Enqueue sync jobs for all active email accounts."""
    async with async_session_maker() as session:
        stmt = select(EmailAccount).where(EmailAccount.sync_enabled == True)  # noqa: E712
        result = await session.execute(stmt)
        accounts = result.scalars().all()

    enqueued = 0
    for account in accounts:
        ok = enqueue_email_sync(
            QueuedEmailSync(
                email_account_id=account.id,
                organization_id=account.organization_id,
            )
        )
        if ok:
            enqueued += 1
    logger.info("email.sync.enqueued_all", extra={"count": enqueued})
    return enqueued
