"""Standalone email sending service — find org's shared email account and send."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.core.logging import get_logger
from app.models.email_accounts import EmailAccount
from app.services.email.token_manager import get_valid_access_token

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)


class NoEmailAccountError(Exception):
    """No shared email account is available for the organization."""


async def get_org_shared_email_account(
    session: AsyncSession,
    organization_id: UUID,
) -> EmailAccount:
    """Return the first shared, sync-enabled email account for the org.

    Raises ``NoEmailAccountError`` when none is found.
    """
    stmt = (
        select(EmailAccount)
        .where(
            EmailAccount.organization_id == organization_id,  # type: ignore[arg-type]
            EmailAccount.sync_enabled.is_(True),  # type: ignore[attr-defined]
            EmailAccount.visibility == "shared",  # type: ignore[arg-type]
        )
        .order_by(EmailAccount.created_at)  # type: ignore[arg-type]
        .limit(1)
    )
    result = await session.execute(stmt)
    account = result.scalars().first()
    if account is None:
        raise NoEmailAccountError("No shared email account connected for this organization.")
    return account  # type: ignore[no-any-return]


async def send_email(
    session: AsyncSession,
    account: EmailAccount,
    *,
    to: str,
    subject: str,
    body: str,
    body_html: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Send an email using the given account's provider.

    Args:
        session: DB session (needed for token refresh).
        account: The EmailAccount to send from.
        to: Recipient email address.
        subject: Email subject line.
        body: Plain-text body.
        body_html: Optional HTML body (used when provider supports it).
        attachments: Optional list of ``{filename, content_bytes, content_type}`` dicts.

    Returns:
        Provider response dict.
    """
    access_token = await get_valid_access_token(session, account)

    if account.provider == "zoho":
        from app.services.email.providers.zoho import send_message as zoho_send_message

        mail_format = "html" if body_html else "plaintext"
        content = body_html or body
        return await zoho_send_message(
            access_token,
            account.provider_account_id or "",
            to=to,
            subject=subject,
            body=content,
            mail_format=mail_format,
            attachments=attachments,
        )
    elif account.provider == "microsoft":
        from app.services.email.providers.microsoft import send_message as msft_send_message

        content_type = "HTML" if body_html else "Text"
        content = body_html or body
        return await msft_send_message(
            access_token,
            to=to,
            subject=subject,
            body=content,
            content_type=content_type,
            attachments=attachments,
        )
    else:
        raise ValueError(f"Unsupported email provider: {account.provider}")
