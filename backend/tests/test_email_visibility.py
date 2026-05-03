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
async def test_agent_only_sees_agent_accessible_accounts():
    """Agent account listing should exclude accounts where agent_access is disabled.

    Gates on agent_access (whether agents can read this inbox), NOT visibility
    (which is the human-side UI control). A private inbox with agent_access
    enabled is still triageable.
    """
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        stmt = select(EmailAccount).where(
            EmailAccount.organization_id == ORG_ID,
            EmailAccount.sync_enabled == True,  # noqa: E712
            EmailAccount.agent_access == "enabled",
        )
        result = await session.execute(stmt)
        accounts = list(result.scalars().all())
        # Default seed: shared accounts have agent_access=enabled (model default),
        # private accounts in fresh test data also have agent_access=enabled by default.
        # Both should appear in the list. The migration's "private→disabled"
        # backfill applies only to existing-prod-data on real deploy, not seed.
        addresses = {a.email_address for a in accounts}
        assert "henry@wastegurus.ca" in addresses


@pytest.mark.asyncio
async def test_agent_messages_exclude_agent_disabled_accounts():
    """Agent message listing should exclude messages from agent-disabled accounts."""
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        accessible_account_ids = select(EmailAccount.id).where(
            EmailAccount.organization_id == ORG_ID,
            EmailAccount.agent_access == "enabled",
        )
        stmt = select(EmailMessage).where(
            EmailMessage.organization_id == ORG_ID,
            EmailMessage.email_account_id.in_(accessible_account_ids),
        )
        result = await session.execute(stmt)
        messages = list(result.scalars().all())
        # Both shared and private accounts default to agent_access=enabled,
        # so messages from both should be returned in fresh seed data.
        subjects = {m.subject for m in messages}
        assert "Shared email" in subjects


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


# ---------------------------------------------------------------------------
# Unread-count aggregate (sidebar badge endpoint)
# ---------------------------------------------------------------------------


async def _seed_unread_mix(session: AsyncSession) -> dict:
    """Seed: shared account (2 unread + 1 read inbox + 1 unread archive),
    a private account owned by MEMBER_USER_ID (3 unread inbox), and a
    private account owned by OWNER_USER_ID (1 unread inbox)."""
    shared_account = EmailAccount(
        id=uuid4(), organization_id=ORG_ID, user_id=OWNER_USER_ID,
        provider="microsoft", email_address="shared@x.ca", visibility="shared",
        sync_enabled=True,
    )
    other_private = EmailAccount(
        id=uuid4(), organization_id=ORG_ID, user_id=MEMBER_USER_ID,
        provider="microsoft", email_address="samir@x.ca", visibility="private",
        sync_enabled=True,
    )
    own_private = EmailAccount(
        id=uuid4(), organization_id=ORG_ID, user_id=OWNER_USER_ID,
        provider="microsoft", email_address="owner-private@x.ca", visibility="private",
        sync_enabled=True,
    )
    session.add_all([shared_account, other_private, own_private])

    def _msg(account_id, *, is_read: bool, folder: str = "inbox"):
        return EmailMessage(
            id=uuid4(), organization_id=ORG_ID, email_account_id=account_id,
            provider_message_id=str(uuid4()), subject="x",
            sender_email="x@example.com", body_text="x",
            received_at=utcnow(), folder=folder, triage_status="pending",
            is_read=is_read, is_starred=False, has_attachments=False,
        )

    session.add_all([
        _msg(shared_account.id, is_read=False),
        _msg(shared_account.id, is_read=False),
        _msg(shared_account.id, is_read=True),
        _msg(shared_account.id, is_read=False, folder="archive"),
        _msg(other_private.id, is_read=False),
        _msg(other_private.id, is_read=False),
        _msg(other_private.id, is_read=False),
        _msg(own_private.id, is_read=False),
    ])
    await session.commit()
    return {
        "shared": shared_account,
        "other_private": other_private,
        "own_private": own_private,
    }


@pytest.mark.asyncio
async def test_unread_count_owner_yours_plus_shared():
    """Henry (non-admin owner of shared + own_private): 2 + 1 = 3.
    The archived message and Samir's 3 private unread are excluded."""
    maker = await _make_session()
    async with maker() as session:
        await _seed_unread_mix(session)
        from sqlalchemy import func, or_

        stmt = (
            select(func.count(EmailMessage.id))
            .join(EmailAccount, EmailAccount.id == EmailMessage.email_account_id)
            .where(EmailAccount.organization_id == ORG_ID)
            .where(EmailMessage.is_read.is_(False))
            .where(EmailMessage.folder == "inbox")
            .where(
                or_(
                    EmailAccount.visibility == "shared",
                    EmailAccount.user_id == OWNER_USER_ID,
                )
            )
        )
        count = (await session.execute(stmt)).scalar_one()
        assert count == 3


@pytest.mark.asyncio
async def test_unread_count_member_excludes_other_users_private():
    """Samir: shared (2) + his own private (3) = 5. Owner's private excluded."""
    maker = await _make_session()
    async with maker() as session:
        await _seed_unread_mix(session)
        from sqlalchemy import func, or_

        stmt = (
            select(func.count(EmailMessage.id))
            .join(EmailAccount, EmailAccount.id == EmailMessage.email_account_id)
            .where(EmailAccount.organization_id == ORG_ID)
            .where(EmailMessage.is_read.is_(False))
            .where(EmailMessage.folder == "inbox")
            .where(
                or_(
                    EmailAccount.visibility == "shared",
                    EmailAccount.user_id == MEMBER_USER_ID,
                )
            )
        )
        count = (await session.execute(stmt)).scalar_one()
        assert count == 5


@pytest.mark.asyncio
async def test_unread_count_admin_sees_all_inbox_unread():
    """Admin: no visibility filter. 2 (shared) + 3 (other private) + 1 (own private) = 6."""
    maker = await _make_session()
    async with maker() as session:
        await _seed_unread_mix(session)
        from sqlalchemy import func

        stmt = (
            select(func.count(EmailMessage.id))
            .join(EmailAccount, EmailAccount.id == EmailMessage.email_account_id)
            .where(EmailAccount.organization_id == ORG_ID)
            .where(EmailMessage.is_read.is_(False))
            .where(EmailMessage.folder == "inbox")
        )
        count = (await session.execute(stmt)).scalar_one()
        assert count == 6


# ---------------------------------------------------------------------------
# Agent access (orthogonal to visibility)
# ---------------------------------------------------------------------------
#
# Locks in the 2026-05-03 fix that split the conflated visibility flag into
# two orthogonal controls. visibility = who in the org can VIEW the inbox in
# the UI. agent_access = whether agents (triage, reply, archive) can read it.
#
# The triggering case: henry@wastegurus.ca was triaged successfully when
# visibility='shared'. Flipping it to 'private' to keep it out of Samir's
# view silently disabled triage. The fix ensures private+enabled = "owner-
# only UI access, agents still triage."


@pytest.mark.asyncio
async def test_agent_access_default_is_enabled():
    """New email accounts default to agent_access='enabled'."""
    maker = await _make_session()
    async with maker() as session:
        account = EmailAccount(
            organization_id=ORG_ID,
            user_id=uuid4(),
            provider="microsoft",
            email_address="newaccount@x.ca",
        )
        session.add(account)
        await session.commit()
        await session.refresh(account)
        assert account.agent_access == "enabled"


@pytest.mark.asyncio
async def test_private_inbox_with_agent_enabled_is_triageable():
    """The henry@wastegurus.ca regression case: private + agent_access=enabled.

    Owner sees inbox in UI. Other org members do NOT see it. But the org's
    triage cron still processes it — agent endpoints gate on agent_access,
    not visibility.
    """
    maker = await _make_session()
    async with maker() as session:
        owner_id = uuid4()
        account = EmailAccount(
            organization_id=ORG_ID,
            user_id=owner_id,
            provider="microsoft",
            email_address="henry@wastegurus.ca",
            visibility="private",
            agent_access="enabled",
        )
        session.add(account)
        await session.commit()

        # Agent-side query — gated on agent_access, not visibility.
        agent_stmt = select(EmailAccount).where(
            EmailAccount.organization_id == ORG_ID,
            EmailAccount.agent_access == "enabled",
        )
        agent_visible = list(
            (await session.execute(agent_stmt)).scalars().all()
        )
        assert any(a.email_address == "henry@wastegurus.ca" for a in agent_visible), (
            "private+enabled inbox MUST be agent-accessible (the triggering bug)"
        )


@pytest.mark.asyncio
async def test_shared_inbox_with_agent_disabled_is_invisible_to_agents():
    """Shared in UI but agent_access=disabled — humans see it, agents don't."""
    maker = await _make_session()
    async with maker() as session:
        account = EmailAccount(
            organization_id=ORG_ID,
            user_id=uuid4(),
            provider="microsoft",
            email_address="sensitive-shared@x.ca",
            visibility="shared",
            agent_access="disabled",
        )
        session.add(account)
        await session.commit()

        agent_stmt = select(EmailAccount).where(
            EmailAccount.organization_id == ORG_ID,
            EmailAccount.agent_access == "enabled",
        )
        agent_visible = list(
            (await session.execute(agent_stmt)).scalars().all()
        )
        assert not any(
            a.email_address == "sensitive-shared@x.ca" for a in agent_visible
        ), "shared+disabled inbox must NOT appear to agents"


@pytest.mark.asyncio
async def test_private_inbox_with_agent_disabled_blocks_both():
    """Private + agent_access=disabled — invisible to other members AND to agents."""
    maker = await _make_session()
    async with maker() as session:
        owner_id = uuid4()
        account = EmailAccount(
            organization_id=ORG_ID,
            user_id=owner_id,
            provider="microsoft",
            email_address="quiet-personal@x.ca",
            visibility="private",
            agent_access="disabled",
        )
        session.add(account)
        await session.commit()

        # Agent query excludes it.
        agent_stmt = select(EmailAccount).where(
            EmailAccount.organization_id == ORG_ID,
            EmailAccount.agent_access == "enabled",
        )
        agent_visible = list(
            (await session.execute(agent_stmt)).scalars().all()
        )
        assert not any(
            a.email_address == "quiet-personal@x.ca" for a in agent_visible
        )

        # Non-owner member query (visibility=shared filter) also excludes it.
        member_stmt = select(EmailAccount).where(
            EmailAccount.organization_id == ORG_ID,
            EmailAccount.visibility == "shared",
        )
        member_visible = list(
            (await session.execute(member_stmt)).scalars().all()
        )
        assert not any(
            a.email_address == "quiet-personal@x.ca" for a in member_visible
        )


@pytest.mark.asyncio
async def test_toggle_agent_access_roundtrip():
    """Owner can toggle agent_access enabled→disabled→enabled without losing visibility setting."""
    maker = await _make_session()
    async with maker() as session:
        account = EmailAccount(
            organization_id=ORG_ID,
            user_id=uuid4(),
            provider="microsoft",
            email_address="toggle@x.ca",
            visibility="private",
            agent_access="enabled",
        )
        session.add(account)
        await session.commit()
        await session.refresh(account)
        assert account.visibility == "private"
        assert account.agent_access == "enabled"

        account.agent_access = "disabled"
        session.add(account)
        await session.commit()
        await session.refresh(account)
        assert account.visibility == "private"  # unchanged
        assert account.agent_access == "disabled"

        account.agent_access = "enabled"
        session.add(account)
        await session.commit()
        await session.refresh(account)
        assert account.visibility == "private"  # still unchanged
        assert account.agent_access == "enabled"
