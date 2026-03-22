"""Email account and message CRUD endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import ORG_MEMBER_DEP, ORG_RATE_LIMIT_DEP, SESSION_DEP, require_feature
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.email_accounts import EmailAccount
from app.models.email_attachments import EmailAttachment
from app.models.email_messages import EmailMessage
from app.schemas.email import (
    EmailAccountRead,
    EmailAccountUpdate,
    EmailAttachmentRead,
    EmailForwardCreate,
    EmailMessageDetail,
    EmailMessageRead,
    EmailMessageUpdate,
    EmailReplyCreate,
    EmailSyncTriggerResponse,
)
from app.services.email.queue import QueuedEmailSync, enqueue_email_sync
from app.services.email.token_manager import get_valid_access_token
from app.services.organizations import OrganizationContext

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)
router = APIRouter(
    prefix="/email",
    tags=["email"],
    dependencies=[Depends(require_feature("email")), ORG_RATE_LIMIT_DEP],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_account_or_404(
    account_id: UUID,
    org_id: UUID,
    session: AsyncSession,
) -> EmailAccount:
    account = await session.get(EmailAccount, account_id)
    if account is None or account.organization_id != org_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return account


async def _get_message_or_404(
    message_id: UUID,
    account: EmailAccount,
    session: AsyncSession,
) -> EmailMessage:
    msg = await session.get(EmailMessage, message_id)
    if msg is None or msg.email_account_id != account.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return msg


# ---------------------------------------------------------------------------
# Account endpoints
# ---------------------------------------------------------------------------


@router.get("/accounts", response_model=list[EmailAccountRead])
async def list_email_accounts(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[EmailAccount]:
    """List connected email accounts for the current organization."""
    stmt = (
        select(EmailAccount)
        .where(EmailAccount.organization_id == ctx.organization.id)
        .order_by(EmailAccount.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/accounts/{account_id}", response_model=EmailAccountRead)
async def get_email_account(
    account_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> EmailAccount:
    """Get a single email account."""
    return await _get_account_or_404(account_id, ctx.organization.id, session)


@router.patch("/accounts/{account_id}", response_model=EmailAccountRead)
async def update_email_account(
    account_id: UUID,
    payload: EmailAccountUpdate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> EmailAccount:
    """Update email account settings (sync toggle, display name)."""
    account = await _get_account_or_404(account_id, ctx.organization.id, session)
    if payload.sync_enabled is not None:
        account.sync_enabled = payload.sync_enabled
    if payload.display_name is not None:
        account.display_name = payload.display_name
    account.updated_at = utcnow()
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_email_account(
    account_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    """Disconnect and delete an email account and its synced messages."""
    account = await _get_account_or_404(account_id, ctx.organization.id, session)

    # Delete attachments for this account's messages
    msg_ids_stmt = select(EmailMessage.id).where(EmailMessage.email_account_id == account.id)
    from sqlalchemy import delete as sa_delete

    await session.execute(
        sa_delete(EmailAttachment).where(EmailAttachment.email_message_id.in_(msg_ids_stmt))
    )
    await session.execute(
        sa_delete(EmailMessage).where(EmailMessage.email_account_id == account.id)
    )
    await session.delete(account)
    await session.commit()


@router.post("/accounts/{account_id}/sync", response_model=EmailSyncTriggerResponse)
async def trigger_email_sync(
    account_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> EmailSyncTriggerResponse:
    """Trigger an immediate email sync for an account."""
    account = await _get_account_or_404(account_id, ctx.organization.id, session)
    ok = enqueue_email_sync(
        QueuedEmailSync(
            email_account_id=account.id,
            organization_id=account.organization_id,
        )
    )
    return EmailSyncTriggerResponse(ok=True, enqueued=ok)


# ---------------------------------------------------------------------------
# Message endpoints
# ---------------------------------------------------------------------------


@router.get("/accounts/{account_id}/messages", response_model=list[EmailMessageRead])
async def list_email_messages(
    account_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
    folder: str | None = Query(default=None),
    triage_status: str | None = Query(default=None),
    is_read: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[EmailMessage]:
    """List synced email messages for an account with filters."""
    account = await _get_account_or_404(account_id, ctx.organization.id, session)
    stmt = (
        select(EmailMessage)
        .where(EmailMessage.email_account_id == account.id)
        .order_by(EmailMessage.received_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if folder:
        stmt = stmt.where(EmailMessage.folder == folder)
    if triage_status:
        stmt = stmt.where(EmailMessage.triage_status == triage_status)
    if is_read is not None:
        stmt = stmt.where(EmailMessage.is_read == is_read)

    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/accounts/{account_id}/messages/{message_id}", response_model=EmailMessageDetail)
async def get_email_message(
    account_id: UUID,
    message_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> EmailMessage:
    """Get a single email message with full body."""
    account = await _get_account_or_404(account_id, ctx.organization.id, session)
    return await _get_message_or_404(message_id, account, session)


@router.patch("/accounts/{account_id}/messages/{message_id}", response_model=EmailMessageRead)
async def update_email_message(
    account_id: UUID,
    message_id: UUID,
    payload: EmailMessageUpdate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> EmailMessage:
    """Update email message metadata (triage, read status, linked task)."""
    account = await _get_account_or_404(account_id, ctx.organization.id, session)
    msg = await _get_message_or_404(message_id, account, session)

    for field in ("is_read", "is_starred", "triage_status", "triage_category", "linked_task_id"):
        value = getattr(payload, field, None)
        if value is not None:
            setattr(msg, field, value)

    msg.updated_at = utcnow()
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg


@router.post(
    "/accounts/{account_id}/messages/{message_id}/reply",
    status_code=status.HTTP_202_ACCEPTED,
)
async def reply_to_email(
    account_id: UUID,
    message_id: UUID,
    payload: EmailReplyCreate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, bool]:
    """Send a reply to an email message via the provider API."""
    account = await _get_account_or_404(account_id, ctx.organization.id, session)
    msg = await _get_message_or_404(message_id, account, session)
    access_token = await get_valid_access_token(session, account)

    if account.provider == "zoho":
        from app.services.email.providers.zoho import send_message

        await send_message(
            access_token,
            account.provider_account_id or "",
            to=msg.sender_email,
            subject=f"Re: {msg.subject or ''}",
            body=payload.body_text,
            in_reply_to=msg.provider_message_id,
        )
    elif account.provider == "microsoft":
        from app.services.email.providers.microsoft import send_message

        await send_message(
            access_token,
            to=msg.sender_email,
            subject=f"Re: {msg.subject or ''}",
            body=payload.body_text,
            reply_to_message_id=msg.provider_message_id,
        )
    return {"ok": True}


@router.post(
    "/accounts/{account_id}/messages/{message_id}/forward",
    status_code=status.HTTP_202_ACCEPTED,
)
async def forward_email(
    account_id: UUID,
    message_id: UUID,
    payload: EmailForwardCreate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, bool]:
    """Forward an email message to another recipient."""
    account = await _get_account_or_404(account_id, ctx.organization.id, session)
    msg = await _get_message_or_404(message_id, account, session)
    access_token = await get_valid_access_token(session, account)

    body = payload.body_text or ""
    if msg.body_text:
        body = f"{body}\n\n--- Forwarded message ---\n{msg.body_text}"

    if account.provider == "zoho":
        from app.services.email.providers.zoho import send_message

        await send_message(
            access_token,
            account.provider_account_id or "",
            to=payload.to,
            subject=f"Fwd: {msg.subject or ''}",
            body=body,
        )
    elif account.provider == "microsoft":
        from app.services.email.providers.microsoft import send_message

        await send_message(
            access_token,
            to=payload.to,
            subject=f"Fwd: {msg.subject or ''}",
            body=body,
        )
    return {"ok": True}


@router.post(
    "/accounts/{account_id}/messages/{message_id}/archive",
    status_code=status.HTTP_202_ACCEPTED,
)
async def archive_email(
    account_id: UUID,
    message_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, bool]:
    """Move an email message to the archive folder."""
    account = await _get_account_or_404(account_id, ctx.organization.id, session)
    msg = await _get_message_or_404(message_id, account, session)
    access_token = await get_valid_access_token(session, account)

    if account.provider == "zoho":
        from app.services.email.providers.zoho import move_message

        await move_message(
            access_token,
            account.provider_account_id or "",
            msg.provider_message_id,
            target_folder="archive",
        )
    elif account.provider == "microsoft":
        from app.services.email.providers.microsoft import move_message

        await move_message(access_token, msg.provider_message_id, target_folder="archive")

    msg.folder = "archive"
    msg.updated_at = utcnow()
    session.add(msg)
    await session.commit()
    return {"ok": True}


@router.get(
    "/accounts/{account_id}/messages/{message_id}/attachments",
    response_model=list[EmailAttachmentRead],
)
async def list_email_attachments(
    account_id: UUID,
    message_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[EmailAttachment]:
    """List attachment metadata for an email message."""
    account = await _get_account_or_404(account_id, ctx.organization.id, session)
    msg = await _get_message_or_404(message_id, account, session)
    stmt = (
        select(EmailAttachment)
        .where(EmailAttachment.email_message_id == msg.id)
        .order_by(EmailAttachment.created_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
