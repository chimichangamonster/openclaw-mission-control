"""Email approval hooks — execute email actions when approvals are resolved."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.core.logging import get_logger
from app.services.email.token_manager import get_valid_access_token

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.approvals import Approval

logger = get_logger(__name__)


async def handle_email_approval_resolution(
    *,
    session: AsyncSession,
    approval: Approval,
) -> None:
    """Execute or discard an email action based on approval status."""
    if approval.status != "approved":
        logger.info(
            "email.approval.skipped",
            extra={"approval_id": str(approval.id), "status": approval.status},
        )
        return

    payload = approval.payload or {}
    action = payload.get("action", "reply")

    if action == "reply":
        await _execute_email_reply(session, payload)
    elif action == "forward":
        await _execute_email_forward(session, payload)
    else:
        logger.warning("email.approval.unknown_action", extra={"action": action})


async def _execute_email_reply(session: AsyncSession, payload: dict[str, Any]) -> None:
    """Send the approved email reply."""
    from sqlmodel import select

    from app.models.email_accounts import EmailAccount
    from app.models.email_messages import EmailMessage

    account_id = payload.get("account_id")
    message_id = payload.get("message_id")
    body_text = payload.get("body_text", "")

    if not account_id or not message_id:
        logger.error("email.approval.missing_ids", extra={"payload": payload})
        return

    account = (
        await session.execute(select(EmailAccount).where(EmailAccount.id == account_id))
    ).scalar_one_or_none()
    if not account:
        logger.error("email.approval.account_not_found", extra={"account_id": account_id})
        return

    msg = (
        await session.execute(select(EmailMessage).where(EmailMessage.id == message_id))
    ).scalar_one_or_none()
    if not msg:
        logger.error("email.approval.message_not_found", extra={"message_id": message_id})
        return

    access_token = await get_valid_access_token(session, account)

    if account.provider == "zoho":
        from app.services.email.providers.zoho import send_message as zoho_send_message

        await zoho_send_message(
            access_token,
            account.provider_account_id or "",
            to=msg.sender_email,
            subject=f"Re: {msg.subject or ''}",
            body=body_text,
            in_reply_to=msg.provider_message_id,
        )
    elif account.provider == "microsoft":
        from app.services.email.providers.microsoft import send_message as msft_send_message

        await msft_send_message(
            access_token,
            to=msg.sender_email,
            subject=f"Re: {msg.subject or ''}",
            body=body_text,
            reply_to_message_id=msg.provider_message_id,
        )

    logger.info(
        "email.approval.sent",
        extra={
            "account_id": account_id,
            "message_id": message_id,
            "to": msg.sender_email,
        },
    )


async def _execute_email_forward(session: AsyncSession, payload: dict[str, Any]) -> None:
    """Send the approved email forward."""
    # Similar to reply but with forward_to address
    logger.info("email.approval.forward_not_implemented")
