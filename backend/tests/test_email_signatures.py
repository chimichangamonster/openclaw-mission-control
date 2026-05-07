# ruff: noqa: INP001
"""Tests for email signature library + send-path append.

Locks in:
- Single-default invariant (clearing other defaults when promoting one)
- Resolution order: explicit signature_id > account default > none
- Account-scope isolation: a signature_id from a different account does not resolve
- HTML append behavior: existing HTML body gets <br><br>signature; plain-text-only
  send is promoted to HTML so the signature renders properly
- Send-path integration calls the resolver and rewrites body/body_html accordingly
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.email_accounts import EmailAccount
from app.models.email_signatures import EmailSignature
from app.services.email_signatures import append_signature_html, resolve_signature

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ORG_ID = uuid4()
OWNER_USER_ID = uuid4()


async def _make_session() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed_account(session: AsyncSession) -> EmailAccount:
    account = EmailAccount(
        id=uuid4(),
        organization_id=ORG_ID,
        user_id=OWNER_USER_ID,
        provider="microsoft",
        email_address="henry@wastegurus.ca",
        visibility="shared",
        agent_access="enabled",
        sync_enabled=True,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


def _make_sig(
    *,
    account_id,
    name: str,
    body: str,
    is_default: bool = False,
) -> EmailSignature:
    return EmailSignature(
        organization_id=ORG_ID,
        email_account_id=account_id,
        name=name,
        body_html=body,
        is_default=is_default,
    )


# ---------------------------------------------------------------------------
# resolve_signature
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_returns_default_when_no_explicit_id():
    maker = await _make_session()
    async with maker() as session:
        account = await _seed_account(session)
        non_default = _make_sig(
            account_id=account.id, name="Short", body="<p>Short</p>", is_default=False
        )
        default = _make_sig(account_id=account.id, name="Full", body="<p>Full</p>", is_default=True)
        session.add_all([non_default, default])
        await session.commit()

        sig = await resolve_signature(session, account, signature_id=None)
        assert sig is not None
        assert sig.id == default.id


@pytest.mark.asyncio
async def test_resolve_returns_none_when_no_default_and_no_explicit_id():
    maker = await _make_session()
    async with maker() as session:
        account = await _seed_account(session)
        only = _make_sig(account_id=account.id, name="Only", body="<p>Only</p>", is_default=False)
        session.add(only)
        await session.commit()

        sig = await resolve_signature(session, account, signature_id=None)
        assert sig is None


@pytest.mark.asyncio
async def test_resolve_returns_explicit_signature_even_when_not_default():
    maker = await _make_session()
    async with maker() as session:
        account = await _seed_account(session)
        explicit = _make_sig(
            account_id=account.id,
            name="Pick me",
            body="<p>Pick me</p>",
            is_default=False,
        )
        default = _make_sig(
            account_id=account.id,
            name="Default",
            body="<p>Default</p>",
            is_default=True,
        )
        session.add_all([explicit, default])
        await session.commit()
        await session.refresh(explicit)

        sig = await resolve_signature(session, account, signature_id=explicit.id)
        assert sig is not None
        assert sig.id == explicit.id


@pytest.mark.asyncio
async def test_resolve_rejects_signature_from_different_account():
    """A signature_id belonging to another account must not resolve — even if it exists."""
    maker = await _make_session()
    async with maker() as session:
        account_a = await _seed_account(session)
        # Second account
        account_b = EmailAccount(
            id=uuid4(),
            organization_id=ORG_ID,
            user_id=OWNER_USER_ID,
            provider="zoho",
            email_address="info@vantagesolutions.ca",
            visibility="shared",
            agent_access="enabled",
            sync_enabled=True,
        )
        session.add(account_b)
        await session.commit()
        await session.refresh(account_b)

        sig_for_b = _make_sig(
            account_id=account_b.id,
            name="B sig",
            body="<p>B sig</p>",
            is_default=True,
        )
        session.add(sig_for_b)
        await session.commit()
        await session.refresh(sig_for_b)

        # Trying to use B's signature for account A must return None.
        result = await resolve_signature(session, account_a, signature_id=sig_for_b.id)
        assert result is None


@pytest.mark.asyncio
async def test_resolve_returns_none_for_unknown_signature_id():
    maker = await _make_session()
    async with maker() as session:
        account = await _seed_account(session)
        result = await resolve_signature(session, account, signature_id=uuid4())
        assert result is None


# ---------------------------------------------------------------------------
# append_signature_html
# ---------------------------------------------------------------------------


def test_append_appends_to_existing_html():
    text, html = append_signature_html(
        body_html="<p>Hello</p>",
        body_text="Hello",
        sig_html="<p>-- Henz</p>",
    )
    assert text == "Hello"
    assert html == "<p>Hello</p><br><br><p>-- Henz</p>"


def test_append_promotes_plain_to_html_when_no_html_body():
    text, html = append_signature_html(
        body_html=None,
        body_text="Line 1\nLine 2",
        sig_html="<p>-- Henz</p>",
    )
    # Plain text body unchanged so providers' fallback is honest.
    assert text == "Line 1\nLine 2"
    # Newlines turned into <br>, signature appended.
    assert "<br>" in html
    assert "<p>-- Henz</p>" in html


def test_append_handles_empty_html_body_as_no_html():
    """Empty string for body_html should fall back to plain-promotion path."""
    text, html = append_signature_html(
        body_html="",
        body_text="Hello",
        sig_html="<p>sig</p>",
    )
    assert text == "Hello"
    # Empty string is falsy → hits the promote-to-html branch.
    assert html.startswith("<div>Hello</div>")
    assert "<p>sig</p>" in html


# ---------------------------------------------------------------------------
# Single-default invariant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_one_default_at_a_time_per_account():
    """When a new default is set, the previous default must be cleared.

    This mirrors the API's _clear_other_defaults helper. We exercise the
    behavior at the data layer to lock the invariant.
    """
    from sqlalchemy import select

    maker = await _make_session()
    async with maker() as session:
        account = await _seed_account(session)
        first = _make_sig(account_id=account.id, name="First", body="<p>1</p>", is_default=True)
        session.add(first)
        await session.commit()
        await session.refresh(first)

        # Now add a second one as default + clear the prior default in the same txn.
        second = _make_sig(account_id=account.id, name="Second", body="<p>2</p>", is_default=True)
        session.add(second)
        # Apply the same logic as _clear_other_defaults.
        stmt = select(EmailSignature).where(
            EmailSignature.email_account_id == account.id,
            EmailSignature.is_default.is_(True),
            EmailSignature.id != second.id,
        )
        result = await session.execute(stmt)
        for sig in result.scalars().all():
            sig.is_default = False
            session.add(sig)
        await session.commit()

        # Verify exactly one default remains.
        check = await session.execute(
            select(EmailSignature).where(
                EmailSignature.email_account_id == account.id,
                EmailSignature.is_default.is_(True),
            )
        )
        defaults = list(check.scalars().all())
        assert len(defaults) == 1
        assert defaults[0].name == "Second"


# ---------------------------------------------------------------------------
# Send-path integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_email_appends_resolved_signature_to_html():
    """send_email should resolve the default signature and append it before dispatching."""
    from app.services import email_send as email_send_module

    maker = await _make_session()
    async with maker() as session:
        account = await _seed_account(session)
        default = _make_sig(
            account_id=account.id,
            name="Default",
            body="<p>-- The Claw</p>",
            is_default=True,
        )
        session.add(default)
        await session.commit()

        send_mock = AsyncMock(return_value={"ok": True})
        with (
            patch.object(
                email_send_module,
                "get_valid_access_token",
                AsyncMock(return_value="fake-token"),
            ),
            patch("app.services.email.providers.microsoft.send_message", send_mock),
        ):
            await email_send_module.send_email(
                session,
                account,
                to="client@example.com",
                subject="Hi",
                body="Body text",
                body_html="<p>Body text</p>",
            )

        assert send_mock.await_count == 1
        kwargs = send_mock.await_args.kwargs
        assert "<p>-- The Claw</p>" in kwargs["body"]
        assert "<br><br>" in kwargs["body"]


@pytest.mark.asyncio
async def test_send_email_skips_signature_when_none_resolves():
    """No default + no explicit signature_id = body untouched."""
    from app.services import email_send as email_send_module

    maker = await _make_session()
    async with maker() as session:
        account = await _seed_account(session)

        send_mock = AsyncMock(return_value={"ok": True})
        with (
            patch.object(
                email_send_module,
                "get_valid_access_token",
                AsyncMock(return_value="fake-token"),
            ),
            patch("app.services.email.providers.microsoft.send_message", send_mock),
        ):
            await email_send_module.send_email(
                session,
                account,
                to="client@example.com",
                subject="Hi",
                body="Body text",
                body_html="<p>Body text</p>",
            )

        kwargs = send_mock.await_args.kwargs
        assert kwargs["body"] == "<p>Body text</p>"  # untouched
