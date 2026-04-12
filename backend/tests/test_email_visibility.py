# ruff: noqa: INP001
"""Tests for per-user email account visibility scoping.

Verifies that private email accounts are only visible to the owner and
org admins, and that agents cannot access private account messages.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.time import utcnow
from app.models.email_accounts import EmailAccount
from app.models.email_messages import EmailMessage

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ORG_ID = uuid4()
OWNER_USER_ID = uuid4()
MEMBER_USER_ID = uuid4()


async def _make_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return maker


async def _seed(session: AsyncSession) -> dict:
    """Seed one org with two email accounts: one shared, one private."""
    shared_account = EmailAccount(
        id=uuid4(),
        organization_id=ORG_ID,
        user_id=OWNER_USER_ID,
        provider="microsoft",
        email_address="henry@wastegurus.ca",
        visibility="shared",
        sync_enabled=True,
    )
    private_account = EmailAccount(
        id=uuid4(),
        organization_id=ORG_ID,
        user_id=MEMBER_USER_ID,
        provider="microsoft",
        email_address="samir@wastegurus.ca",
        visibility="private",
        sync_enabled=True,
    )
    session.add_all([shared_account, private_account])

    shared_msg = EmailMessage(
        id=uuid4(),
        organization_id=ORG_ID,
        email_account_id=shared_account.id,
        provider_message_id="msg-shared-1",
        subject="Shared email",
        sender_email="client@example.com",
        sender_name="Client",
        body_text="Hello from shared account",
        received_at=utcnow(),
        folder="inbox",
        triage_status="pending",
        is_read=False,
        is_starred=False,
        has_attachments=False,
    )
    private_msg = EmailMessage(
        id=uuid4(),
        organization_id=ORG_ID,
        email_account_id=private_account.id,
        provider_message_id="msg-private-1",
        subject="Private email",
        sender_email="personal@example.com",
        sender_name="Personal",
        body_text="Hello from private account",
        received_at=utcnow(),
        folder="inbox",
        triage_status="pending",
        is_read=False,
        is_starred=False,
        has_attachments=False,
    )
    session.add_all([shared_msg, private_msg])

    await session.commit()
    return {
        "shared_account": shared_account,
        "private_account": private_account,
        "shared_msg": shared_msg,
        "private_msg": private_msg,
    }


# ---------------------------------------------------------------------------
# Model defaults
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_visibility_is_shared():
    """New email accounts default to 'shared' visibility."""
    account = EmailAccount(
        id=uuid4(),
        organization_id=ORG_ID,
        user_id=OWNER_USER_ID,
        provider="microsoft",
        email_address="test@example.com",
    )
    assert account.visibility == "shared"


# ---------------------------------------------------------------------------
# Query-level visibility filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shared_accounts_visible_to_all():
    """Shared accounts should be visible in unfiltered queries."""
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        stmt = select(EmailAccount).where(
            EmailAccount.organization_id == ORG_ID,
            EmailAccount.visibility == "shared",
        )
        result = await session.execute(stmt)
        accounts = list(result.scalars().all())
        assert len(accounts) == 1
        assert accounts[0].email_address == "henry@wastegurus.ca"


@pytest.mark.asyncio
async def test_private_accounts_hidden_from_non_owner():
    """Non-owner, non-admin query should not return private accounts from other users."""
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        from sqlalchemy import or_

        # Simulate non-admin member query (only shared + own)
        stmt = select(EmailAccount).where(
            EmailAccount.organization_id == ORG_ID,
            or_(
                EmailAccount.visibility == "shared",
                EmailAccount.user_id == OWNER_USER_ID,
            ),
        )
        result = await session.execute(stmt)
        accounts = list(result.scalars().all())
        # Owner sees shared account (their own) — but NOT Samir's private account
        assert len(accounts) == 1
        assert accounts[0].email_address == "henry@wastegurus.ca"


@pytest.mark.asyncio
async def test_private_account_visible_to_owner():
    """Account owner should see their own private account."""
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        from sqlalchemy import or_

        # Simulate member query for MEMBER_USER_ID (Samir)
        stmt = select(EmailAccount).where(
            EmailAccount.organization_id == ORG_ID,
            or_(
                EmailAccount.visibility == "shared",
                EmailAccount.user_id == MEMBER_USER_ID,
            ),
        )
        result = await session.execute(stmt)
        accounts = list(result.scalars().all())
        # Samir sees shared account + his own private account
        assert len(accounts) == 2
        emails = {a.email_address for a in accounts}
        assert emails == {"henry@wastegurus.ca", "samir@wastegurus.ca"}


@pytest.mark.asyncio
async def test_admin_sees_all_accounts():
    """Admin/owner sees all accounts regardless of visibility."""
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        # Admin query — no visibility filter
        stmt = select(EmailAccount).where(
            EmailAccount.organization_id == ORG_ID,
        )
        result = await session.execute(stmt)
        accounts = list(result.scalars().all())
        assert len(accounts) == 2


# ---------------------------------------------------------------------------
# Agent email filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_only_sees_shared_accounts():
    """Agent account listing should exclude private accounts."""
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        stmt = select(EmailAccount).where(
            EmailAccount.organization_id == ORG_ID,
            EmailAccount.sync_enabled == True,  # noqa: E712
            EmailAccount.visibility == "shared",
        )
        result = await session.execute(stmt)
        accounts = list(result.scalars().all())
        assert len(accounts) == 1
        assert accounts[0].email_address == "henry@wastegurus.ca"


@pytest.mark.asyncio
async def test_agent_messages_exclude_private_accounts():
    """Agent message listing should exclude messages from private accounts."""
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        shared_account_ids = select(EmailAccount.id).where(
            EmailAccount.organization_id == ORG_ID,
            EmailAccount.visibility == "shared",
        )
        stmt = select(EmailMessage).where(
            EmailMessage.organization_id == ORG_ID,
            EmailMessage.email_account_id.in_(shared_account_ids),
        )
        result = await session.execute(stmt)
        messages = list(result.scalars().all())
        assert len(messages) == 1
        assert messages[0].subject == "Shared email"


# ---------------------------------------------------------------------------
# Visibility toggle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_visibility_roundtrip():
    """Toggling visibility from shared to private and back works."""
    maker = await _make_session()
    async with maker() as session:
        data = await _seed(session)
        account = data["shared_account"]
        assert account.visibility == "shared"

        account.visibility = "private"
        session.add(account)
        await session.commit()
        await session.refresh(account)
        assert account.visibility == "private"

        # Now it's hidden from agent queries
        stmt = select(EmailAccount).where(
            EmailAccount.organization_id == ORG_ID,
            EmailAccount.visibility == "shared",
        )
        result = await session.execute(stmt)
        accounts = list(result.scalars().all())
        assert len(accounts) == 0

        # Toggle back
        account.visibility = "shared"
        session.add(account)
        await session.commit()
        await session.refresh(account)
        assert account.visibility == "shared"

        result = await session.execute(stmt)
        accounts = list(result.scalars().all())
        assert len(accounts) == 1
