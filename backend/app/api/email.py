"""Email account and message CRUD endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, select

from app.api.deps import ORG_MEMBER_DEP, ORG_RATE_LIMIT_DEP, SESSION_DEP, require_feature
from app.core.logging import get_logger
from app.core.redact import RedactionLevel, redact_email_content
from app.core.sanitize import sanitize_text
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
    EmailSendCreate,
    EmailSyncTriggerResponse,
)
from app.services.email.queue import QueuedEmailSync, enqueue_email_sync
from app.services.email.token_manager import get_valid_access_token
from app.services.organizations import OrganizationContext, is_org_admin

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)
router = APIRouter(
    prefix="/email",
    tags=["email"],
    dependencies=[Depends(require_feature("email")), ORG_RATE_LIMIT_DEP],
)

# Separate unauthenticated router for HMAC-signed inline attachment URLs
# (browser <img> tags can't send auth headers, so inline images use signed tokens)
inline_router = APIRouter(prefix="/email", tags=["email"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_account_or_404(
    account_id: UUID,
    ctx: OrganizationContext,
    session: AsyncSession,
) -> EmailAccount:
    account = await session.get(EmailAccount, account_id)
    if account is None or account.organization_id != ctx.organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    # Private accounts are only visible to the owner or org admins
    if (
        account.visibility == "private"
        and account.user_id != ctx.member.user_id
        and not is_org_admin(ctx.member)
    ):
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
    from sqlalchemy import or_

    stmt = (
        select(EmailAccount)
        .where(EmailAccount.organization_id == ctx.organization.id)  # type: ignore[arg-type]
        .order_by(EmailAccount.created_at.desc())  # type: ignore[attr-defined]
    )
    # Non-admin users only see shared accounts + their own private accounts
    if not is_org_admin(ctx.member):
        stmt = stmt.where(
            or_(
                EmailAccount.visibility == "shared",  # type: ignore[arg-type]
                EmailAccount.user_id == ctx.member.user_id,  # type: ignore[arg-type]
            )
        )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/unread-count")
async def get_unread_email_count(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, int]:
    """Total unread inbox messages across the caller's accessible mailboxes.

    Mirrors the visibility filter from `list_email_accounts`: non-admins see
    shared accounts plus their own private accounts. Used by the sidebar
    Email badge.
    """
    from sqlalchemy import or_

    stmt = (
        select(func.count(EmailMessage.id))  # type: ignore[arg-type]
        .join(EmailAccount, EmailAccount.id == EmailMessage.email_account_id)  # type: ignore[arg-type]
        .where(EmailAccount.organization_id == ctx.organization.id)  # type: ignore[arg-type]
        .where(EmailMessage.is_read.is_(False))  # type: ignore[union-attr]
        .where(EmailMessage.folder == "inbox")  # type: ignore[arg-type]
    )
    if not is_org_admin(ctx.member):
        stmt = stmt.where(
            or_(
                EmailAccount.visibility == "shared",  # type: ignore[arg-type]
                EmailAccount.user_id == ctx.member.user_id,  # type: ignore[arg-type]
            )
        )
    result = await session.execute(stmt)
    count = result.scalar_one() or 0
    return {"count": int(count)}


@router.get("/accounts/{account_id}", response_model=EmailAccountRead)
async def get_email_account(
    account_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> EmailAccount:
    """Get a single email account."""
    return await _get_account_or_404(account_id, ctx, session)


@router.patch("/accounts/{account_id}", response_model=EmailAccountRead)
async def update_email_account(
    account_id: UUID,
    payload: EmailAccountUpdate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> EmailAccount:
    """Update email account settings (sync toggle, display name, visibility)."""
    account = await _get_account_or_404(account_id, ctx, session)
    if payload.sync_enabled is not None:
        account.sync_enabled = payload.sync_enabled
    if payload.display_name is not None:
        account.display_name = payload.display_name
    if payload.visibility is not None:
        if payload.visibility not in ("shared", "private"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="visibility must be 'shared' or 'private'",
            )
        # Only account owner or org admin can change visibility
        if account.user_id != ctx.member.user_id and not is_org_admin(ctx.member):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the account owner or an admin can change visibility.",
            )
        account.visibility = payload.visibility
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
    account = await _get_account_or_404(account_id, ctx, session)

    # Delete attachments for this account's messages
    msg_ids_stmt = select(EmailMessage.id).where(EmailMessage.email_account_id == account.id)  # type: ignore[call-overload]
    from sqlalchemy import delete as sa_delete

    await session.execute(
        sa_delete(EmailAttachment).where(EmailAttachment.email_message_id.in_(msg_ids_stmt))  # type: ignore[attr-defined]
    )
    await session.execute(
        sa_delete(EmailMessage).where(EmailMessage.email_account_id == account.id)  # type: ignore[arg-type]
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
    account = await _get_account_or_404(account_id, ctx, session)
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
    account = await _get_account_or_404(account_id, ctx, session)
    stmt = (
        select(EmailMessage)
        .where(EmailMessage.email_account_id == account.id)  # type: ignore[arg-type]
        .order_by(EmailMessage.received_at.desc())  # type: ignore[attr-defined]
        .offset(offset)
        .limit(limit)
    )
    if folder:
        stmt = stmt.where(EmailMessage.folder == folder)  # type: ignore[arg-type]
    if triage_status:
        stmt = stmt.where(EmailMessage.triage_status == triage_status)  # type: ignore[arg-type]
    if is_read is not None:
        stmt = stmt.where(EmailMessage.is_read == is_read)  # type: ignore[arg-type]

    result = await session.execute(stmt)
    messages = list(result.scalars().all())
    for msg in messages:
        msg.body_text = sanitize_text(msg.body_text)
    return messages


@router.get("/accounts/{account_id}/messages/{message_id}", response_model=EmailMessageDetail)
async def get_email_message(
    account_id: UUID,
    message_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> EmailMessage:
    """Get a single email message with full body."""
    account = await _get_account_or_404(account_id, ctx, session)
    msg = await _get_message_or_404(message_id, account, session)
    msg.body_text = sanitize_text(msg.body_text)
    msg.body_html = sanitize_text(msg.body_html)
    text, html, _, _ = redact_email_content(
        msg.body_text, msg.body_html, level=RedactionLevel.MODERATE
    )
    msg.body_text = text
    msg.body_html = html

    # Replace cid: references in HTML with signed download URLs
    # so inline images render without auth headers (browser <img> tags can't send them)
    if msg.body_html and "cid:" in msg.body_html:
        from app.core.file_tokens import create_file_token

        att_stmt = select(EmailAttachment).where(
            EmailAttachment.email_message_id == msg.id,  # type: ignore[arg-type]
            EmailAttachment.content_id.isnot(None),  # type: ignore[union-attr]
        )
        att_result = await session.execute(att_stmt)
        inline_atts = list(att_result.scalars().all())

        # Lazy-fetch attachments from provider if none with content_id exist yet
        if not inline_atts and msg.has_attachments and account.provider == "microsoft":
            try:
                from uuid import uuid4 as _uuid4

                from app.services.email.providers.microsoft import fetch_attachments

                access_token = await get_valid_access_token(session, account)
                att_list = await fetch_attachments(access_token, msg.provider_message_id)
                now = utcnow()
                for a in att_list:
                    att_obj = EmailAttachment(
                        id=_uuid4(),
                        email_message_id=msg.id,
                        filename=a["filename"],
                        content_type=a.get("content_type"),
                        size_bytes=a.get("size_bytes"),
                        provider_attachment_id=a.get("provider_attachment_id"),
                        content_id=a.get("content_id"),
                        is_inline=a.get("is_inline", False),
                        created_at=now,
                    )
                    session.add(att_obj)
                    if att_obj.content_id:
                        inline_atts.append(att_obj)
                await session.commit()
            except Exception:
                logger.warning("email.inline.lazy_fetch_failed", extra={"message_id": str(msg.id)})

        for att in inline_atts:
            cid = att.content_id
            if cid:
                # Encode attachment coordinates into a signed token (1h expiry)
                token_path = f"email-att:{account_id}:{message_id}:{att.id}"
                token = create_file_token(token_path, expires_hours=1)
                download_url = f"/api/v1/email/inline-attachment?token={token}"
                msg.body_html = msg.body_html.replace(f"cid:{cid}", download_url)

    return msg


@router.patch("/accounts/{account_id}/messages/{message_id}", response_model=EmailMessageRead)
async def update_email_message(
    account_id: UUID,
    message_id: UUID,
    payload: EmailMessageUpdate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> EmailMessage:
    """Update email message metadata (triage, read status, linked task)."""
    account = await _get_account_or_404(account_id, ctx, session)
    msg = await _get_message_or_404(message_id, account, session)

    # Detect re-categorization for Langfuse quality scoring
    old_category = msg.triage_category
    new_category = payload.triage_category

    for field in (
        "is_read",
        "is_starred",
        "triage_status",
        "triage_category",
        "triage_trace_id",
        "linked_task_id",
    ):
        value = getattr(payload, field, None)
        if value is not None:
            setattr(msg, field, value)

    msg.updated_at = utcnow()
    session.add(msg)
    await session.commit()
    await session.refresh(msg)

    # Fire Langfuse score when user re-categorizes a triaged email
    if new_category and new_category != old_category and old_category is not None:
        from app.services.langfuse_client import score_trace

        trace_id = msg.triage_trace_id
        if trace_id:
            score_trace(
                trace_id=trace_id,
                name="triage_accuracy",
                value=0.0,
                comment=f"Re-categorized: {old_category} → {new_category}",
            )
        else:
            # No trace_id yet — log as a standalone event for quality monitoring
            from app.services.langfuse_client import get_langfuse

            client = get_langfuse()
            if client:
                try:
                    client.create_event(
                        name="email_recategorization",
                        metadata={
                            "org_id": str(ctx.organization.id),
                            "message_id": str(msg.id),
                            "old_category": old_category,
                            "new_category": new_category,
                        },
                    )
                except Exception:
                    logger.debug("langfuse.recategorization_event_failed", exc_info=True)

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
    account = await _get_account_or_404(account_id, ctx, session)
    msg = await _get_message_or_404(message_id, account, session)
    access_token = await get_valid_access_token(session, account)

    if account.provider == "zoho":
        from app.services.email.providers.zoho import send_message as zoho_send_message

        await zoho_send_message(
            access_token,
            account.provider_account_id or "",
            to=msg.sender_email,
            subject=f"Re: {msg.subject or ''}",
            body=payload.body_text,
            in_reply_to=msg.provider_message_id,
        )
    elif account.provider == "microsoft":
        from app.services.email.providers.microsoft import send_message as msft_send_message

        await msft_send_message(
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
    account = await _get_account_or_404(account_id, ctx, session)
    msg = await _get_message_or_404(message_id, account, session)
    access_token = await get_valid_access_token(session, account)

    body = payload.body_text or ""
    if msg.body_text:
        body = f"{body}\n\n--- Forwarded message ---\n{msg.body_text}"

    if account.provider == "zoho":
        from app.services.email.providers.zoho import send_message as zoho_send_message

        await zoho_send_message(
            access_token,
            account.provider_account_id or "",
            to=payload.to,
            subject=f"Fwd: {msg.subject or ''}",
            body=body,
        )
    elif account.provider == "microsoft":
        from app.services.email.providers.microsoft import send_message as msft_send_message

        await msft_send_message(
            access_token,
            to=payload.to,
            subject=f"Fwd: {msg.subject or ''}",
            body=body,
        )
    return {"ok": True}


@router.post(
    "/accounts/{account_id}/send",
    status_code=status.HTTP_202_ACCEPTED,
)
async def send_new_email(
    account_id: UUID,
    payload: EmailSendCreate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, bool]:
    """Send a new email (not a reply) from the given account."""
    account = await _get_account_or_404(account_id, ctx, session)
    from app.services.email_send import send_email

    await send_email(
        session,
        account,
        to=payload.to,
        subject=payload.subject,
        body=payload.body,
        body_html=payload.body_html,
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
    account = await _get_account_or_404(account_id, ctx, session)
    msg = await _get_message_or_404(message_id, account, session)
    access_token = await get_valid_access_token(session, account)

    if account.provider == "zoho":
        from app.services.email.providers.zoho import move_message as zoho_move_message

        await zoho_move_message(
            access_token,
            account.provider_account_id or "",
            msg.provider_message_id,
            target_folder="archive",
        )
    elif account.provider == "microsoft":
        from app.services.email.providers.microsoft import move_message as msft_move_message

        await msft_move_message(access_token, msg.provider_message_id, target_folder="archive")

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
    """List attachment metadata for an email message.

    Lazily fetches from the provider if the DB has no records but the message
    is flagged as having attachments (e.g. Microsoft Graph messages synced
    before attachment fetching was added).
    """
    account = await _get_account_or_404(account_id, ctx, session)
    msg = await _get_message_or_404(message_id, account, session)
    stmt = (
        select(EmailAttachment)
        .where(EmailAttachment.email_message_id == msg.id)  # type: ignore[arg-type]
        .order_by(EmailAttachment.created_at)  # type: ignore[arg-type]
    )
    result = await session.execute(stmt)
    attachments = list(result.scalars().all())

    # Lazy-fetch from provider if DB is empty but message has attachments
    if not attachments and msg.has_attachments and account.provider == "microsoft":
        try:
            from uuid import uuid4 as _uuid4

            from app.services.email.providers.microsoft import fetch_attachments

            access_token = await get_valid_access_token(session, account)
            att_list = await fetch_attachments(access_token, msg.provider_message_id)
            now = utcnow()
            for a in att_list:
                att = EmailAttachment(
                    id=_uuid4(),
                    email_message_id=msg.id,
                    filename=a["filename"],
                    content_type=a.get("content_type"),
                    size_bytes=a.get("size_bytes"),
                    provider_attachment_id=a.get("provider_attachment_id"),
                    content_id=a.get("content_id"),
                    is_inline=a.get("is_inline", False),
                    created_at=now,
                )
                session.add(att)
                attachments.append(att)
            await session.commit()
        except Exception:
            logger.warning("email.attachments.lazy_fetch_failed", extra={"message_id": str(msg.id)})

    return attachments


@router.get(
    "/accounts/{account_id}/messages/{message_id}/attachments/{attachment_id}/download",
)
async def download_email_attachment(
    account_id: UUID,
    message_id: UUID,
    attachment_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> Response:
    """Download an email attachment's content from the provider."""
    account = await _get_account_or_404(account_id, ctx, session)
    msg = await _get_message_or_404(message_id, account, session)
    att = await session.get(EmailAttachment, attachment_id)
    if att is None or att.email_message_id != msg.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    access_token = await get_valid_access_token(session, account)

    if account.provider == "zoho":
        from app.services.email.providers.zoho import (
            download_attachment as zoho_download_attachment,
        )

        content, filename, content_type = await zoho_download_attachment(
            access_token,
            account.provider_account_id or "",
            msg.provider_message_id,
            att.provider_attachment_id or "",
        )
    elif account.provider == "microsoft":
        from app.services.email.providers.microsoft import (
            download_attachment as msft_download_attachment,
        )

        content, filename, content_type = await msft_download_attachment(
            access_token,
            msg.provider_message_id,
            att.provider_attachment_id or "",
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{att.filename or filename}"',
        },
    )


# ---------------------------------------------------------------------------
# Unauthenticated inline attachment endpoint (HMAC-signed token)
# ---------------------------------------------------------------------------


@inline_router.get("/inline-attachment")
async def get_inline_attachment(
    token: str = Query(...),
    session: AsyncSession = SESSION_DEP,
) -> Response:
    """Serve an inline email attachment using a signed token (no auth required).

    Tokens are generated server-side when replacing cid: references in HTML.
    """
    from app.core.file_tokens import verify_file_token

    path = verify_file_token(token)
    if not path or not path.startswith("email-att:"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or expired token"
        )

    parts = path.split(":")
    if len(parts) != 4:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")

    _, account_id_str, message_id_str, attachment_id_str = parts
    try:
        from uuid import UUID as _UUID

        account_id = _UUID(account_id_str)
        attachment_id = _UUID(attachment_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")

    account = await session.get(EmailAccount, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    att = await session.get(EmailAttachment, attachment_id)
    if att is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    msg = await session.get(EmailMessage, att.email_message_id)
    if msg is None or msg.email_account_id != account.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    access_token = await get_valid_access_token(session, account)

    if account.provider == "zoho":
        from app.services.email.providers.zoho import (
            download_attachment as zoho_download_attachment,
        )

        content, filename, content_type = await zoho_download_attachment(
            access_token,
            account.provider_account_id or "",
            msg.provider_message_id,
            att.provider_attachment_id or "",
        )
    elif account.provider == "microsoft":
        from app.services.email.providers.microsoft import (
            download_attachment as msft_download_attachment,
        )

        content, filename, content_type = await msft_download_attachment(
            access_token,
            msg.provider_message_id,
            att.provider_attachment_id or "",
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": "inline",
        },
    )
