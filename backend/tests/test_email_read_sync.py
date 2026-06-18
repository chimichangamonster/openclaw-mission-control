# ruff: noqa: INP001
"""Tests for read-state mirroring back to the email provider.

Backlog item 79 (read-state half): `update_email_message` previously wrote
`is_read` to the MC DB only — a one-way mirror. The provider (Zoho/MS/Gmail)
never learned the message was read, so on any re-insert (180-day retention
cleanup + re-sync, folder move, reconnect) the message reverted to unread
because the provider is the source of truth on a fresh insert.

The fix wires the provider `mark_read()` into the update path, best-effort:
- Only `is_read` is pushed (is_starred / triage stay MC-local).
- Dispatch by `account.provider`; Zoho needs `provider_account_id`, MS/Gmail don't.
- A provider failure logs and is swallowed — it must NOT fail the local update
  (read-state is a UX convenience; a Zoho hiccup must not 500 the user's click).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.email import update_email_message
from app.core.time import utcnow
from app.models.email_accounts import EmailAccount
from app.models.email_messages import EmailMessage
from app.schemas.email import EmailMessageUpdate
from app.services.organizations import OrganizationContext

ORG_ID = uuid4()
USER_ID = uuid4()


async def _make_session() -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _ctx() -> OrganizationContext:
    return OrganizationContext(
        organization=SimpleNamespace(id=ORG_ID),
        member=SimpleNamespace(user_id=USER_ID, role="owner"),
    )


async def _seed(
    session: AsyncSession,
    *,
    provider: str = "zoho",
    provider_account_id: str | None = "zoho-acct-1",
) -> tuple[EmailAccount, EmailMessage]:
    account = EmailAccount(
        id=uuid4(),
        organization_id=ORG_ID,
        user_id=USER_ID,
        provider=provider,
        provider_account_id=provider_account_id,
        email_address="info@vantagesolutions.ca",
        visibility="shared",
        sync_enabled=True,
    )
    msg = EmailMessage(
        id=uuid4(),
        organization_id=ORG_ID,
        email_account_id=account.id,
        provider_message_id="provider-msg-1",
        subject="Hello",
        sender_email="client@example.com",
        body_text="Body",
        received_at=utcnow(),
        folder="inbox",
        triage_status="pending",
        is_read=False,
        is_starred=False,
        has_attachments=False,
    )
    session.add_all([account, msg])
    await session.commit()
    return account, msg


@pytest.mark.asyncio
async def test_patch_is_read_pushes_to_zoho_provider():
    """Marking a Zoho message read pushes mark_read(token, account_id, msg_id, read=True)."""
    maker = await _make_session()
    async with maker() as session:
        account, msg = await _seed(session, provider="zoho")

        with (
            patch(
                "app.api.email.get_valid_access_token",
                new_callable=AsyncMock,
                return_value="fake-token",
            ),
            patch(
                "app.services.email.providers.zoho.mark_read",
                new_callable=AsyncMock,
            ) as mock_mark,
        ):
            result = await update_email_message(
                account_id=account.id,
                message_id=msg.id,
                payload=EmailMessageUpdate(is_read=True),
                ctx=_ctx(),
                session=session,
            )

        assert result.is_read is True
        mock_mark.assert_awaited_once()
        call = mock_mark.call_args
        # Zoho positional args: access_token, account_id, message_id
        assert call.args[0] == "fake-token"
        assert call.args[1] == "zoho-acct-1"
        assert call.args[2] == "provider-msg-1"
        assert call.kwargs.get("read") is True


@pytest.mark.asyncio
async def test_patch_is_read_false_pushes_unread():
    """Marking read=False pushes read=False to the provider."""
    maker = await _make_session()
    async with maker() as session:
        account, msg = await _seed(session, provider="zoho")
        msg.is_read = True
        session.add(msg)
        await session.commit()

        with (
            patch(
                "app.api.email.get_valid_access_token",
                new_callable=AsyncMock,
                return_value="fake-token",
            ),
            patch(
                "app.services.email.providers.zoho.mark_read",
                new_callable=AsyncMock,
            ) as mock_mark,
        ):
            await update_email_message(
                account_id=account.id,
                message_id=msg.id,
                payload=EmailMessageUpdate(is_read=False),
                ctx=_ctx(),
                session=session,
            )

        mock_mark.assert_awaited_once()
        assert mock_mark.call_args.kwargs.get("read") is False


@pytest.mark.asyncio
async def test_patch_is_read_pushes_to_microsoft_without_account_id():
    """Microsoft mark_read takes (token, message_id) — no account_id positional."""
    maker = await _make_session()
    async with maker() as session:
        account, msg = await _seed(session, provider="microsoft", provider_account_id=None)

        with (
            patch(
                "app.api.email.get_valid_access_token",
                new_callable=AsyncMock,
                return_value="fake-token",
            ),
            patch(
                "app.services.email.providers.microsoft.mark_read",
                new_callable=AsyncMock,
            ) as mock_mark,
        ):
            await update_email_message(
                account_id=account.id,
                message_id=msg.id,
                payload=EmailMessageUpdate(is_read=True),
                ctx=_ctx(),
                session=session,
            )

        mock_mark.assert_awaited_once()
        call = mock_mark.call_args
        assert call.args[0] == "fake-token"
        assert call.args[1] == "provider-msg-1"
        assert call.kwargs.get("read") is True


@pytest.mark.asyncio
async def test_patch_is_read_pushes_to_google_without_account_id():
    """Gmail mark_read takes (token, message_id) — no account_id positional."""
    maker = await _make_session()
    async with maker() as session:
        account, msg = await _seed(session, provider="google", provider_account_id=None)

        with (
            patch(
                "app.api.email.get_valid_access_token",
                new_callable=AsyncMock,
                return_value="fake-token",
            ),
            patch(
                "app.services.email.providers.google.mark_read",
                new_callable=AsyncMock,
            ) as mock_mark,
        ):
            await update_email_message(
                account_id=account.id,
                message_id=msg.id,
                payload=EmailMessageUpdate(is_read=True),
                ctx=_ctx(),
                session=session,
            )

        mock_mark.assert_awaited_once()
        assert mock_mark.call_args.args[1] == "provider-msg-1"


@pytest.mark.asyncio
async def test_provider_failure_does_not_fail_local_update():
    """A provider error is swallowed — the local read-state still commits and the
    endpoint returns 200 with is_read=True."""
    maker = await _make_session()
    async with maker() as session:
        account, msg = await _seed(session, provider="zoho")

        with (
            patch(
                "app.api.email.get_valid_access_token",
                new_callable=AsyncMock,
                return_value="fake-token",
            ),
            patch(
                "app.services.email.providers.zoho.mark_read",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Zoho 503"),
            ) as mock_mark,
        ):
            result = await update_email_message(
                account_id=account.id,
                message_id=msg.id,
                payload=EmailMessageUpdate(is_read=True),
                ctx=_ctx(),
                session=session,
            )

        mock_mark.assert_awaited_once()
        assert result.is_read is True  # local update survived the provider failure

    # And it persisted to the DB.
    async with maker() as session:
        reloaded = await session.get(EmailMessage, msg.id)
        assert reloaded is not None
        assert reloaded.is_read is True


@pytest.mark.asyncio
async def test_patch_without_is_read_does_not_call_provider():
    """A metadata-only update (is_starred / triage) must not touch the provider."""
    maker = await _make_session()
    async with maker() as session:
        account, msg = await _seed(session, provider="zoho")

        with (
            patch(
                "app.api.email.get_valid_access_token",
                new_callable=AsyncMock,
            ) as mock_token,
            patch(
                "app.services.email.providers.zoho.mark_read",
                new_callable=AsyncMock,
            ) as mock_mark,
        ):
            await update_email_message(
                account_id=account.id,
                message_id=msg.id,
                payload=EmailMessageUpdate(is_starred=True),
                ctx=_ctx(),
                session=session,
            )

        mock_mark.assert_not_awaited()
        mock_token.assert_not_awaited()
