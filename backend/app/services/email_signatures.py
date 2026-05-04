"""Email signature resolution + body composition helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.email_signatures import EmailSignature

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.email_accounts import EmailAccount


async def resolve_signature(
    session: AsyncSession,
    account: EmailAccount,
    signature_id: UUID | None,
) -> EmailSignature | None:
    """Resolve the signature to use for a send: explicit id > account default > none."""
    if signature_id is not None:
        sig = await session.get(EmailSignature, signature_id)
        if sig is None or sig.email_account_id != account.id:
            return None
        return sig

    stmt = (
        select(EmailSignature)
        .where(
            EmailSignature.email_account_id == account.id,  # type: ignore[arg-type]
            EmailSignature.is_default.is_(True),  # type: ignore[attr-defined]
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalars().first()  # type: ignore[no-any-return]


def append_signature_html(body_html: str | None, body_text: str, sig_html: str) -> tuple[str, str]:
    """Append signature HTML to body. Promotes plain-text-only sends to HTML.

    Returns ``(new_body_text, new_body_html)``. ``new_body_text`` is the original
    plain-text body unchanged — providers always send the HTML branch when one
    is present, so the plain-text body is fallback-only and we don't bother
    appending a stripped-text version.
    """
    if body_html:
        return body_text, f"{body_html}<br><br>{sig_html}"
    # Promote plain-only send to HTML so the signature renders properly.
    return body_text, f"<div>{body_text.replace(chr(10), '<br>')}</div><br><br>{sig_html}"
