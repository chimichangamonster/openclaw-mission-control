# ruff: noqa: INP001
"""Tests for org contacts model and search logic.

Verifies manual contacts CRUD, email-derived contact extraction,
and unified search across org members, contacts, and email history.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.time import utcnow
from app.models.email_accounts import EmailAccount
from app.models.email_messages import EmailMessage
from app.models.org_contacts import OrgContact
from app.models.organization_members import OrganizationMember
from app.models.organizations import Organization
from app.models.users import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ORG_ID = uuid4()
HENRY_USER_ID = uuid4()
SAMIR_USER_ID = uuid4()


async def _make_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return maker


async def _seed(session: AsyncSession) -> dict:
    """Seed org, users, members, contacts, and email messages."""
    org = Organization(id=ORG_ID, name="Waste Gurus", slug="waste-gurus")
    session.add(org)

    henry = User(id=HENRY_USER_ID, clerk_user_id="clerk_henry", email="henry@wastegurus.ca", name="Henry Chin")
    samir = User(id=SAMIR_USER_ID, clerk_user_id="clerk_samir", email="samir@wastegurus.ca", name="Samir Khan")
    session.add_all([henry, samir])

    henry_member = OrganizationMember(id=uuid4(), organization_id=ORG_ID, user_id=HENRY_USER_ID, role="owner")
    samir_member = OrganizationMember(id=uuid4(), organization_id=ORG_ID, user_id=SAMIR_USER_ID, role="member")
    session.add_all([henry_member, samir_member])

    # Manual contacts
    client_contact = OrgContact(
        id=uuid4(), organization_id=ORG_ID, created_by_user_id=HENRY_USER_ID,
        email="bob@client.com", name="Bob Builder", company="BuildCo", role="client",
        source="manual", created_at=utcnow(), updated_at=utcnow(),
    )
    supplier_contact = OrgContact(
        id=uuid4(), organization_id=ORG_ID, created_by_user_id=HENRY_USER_ID,
        email="alice@supplies.com", name="Alice Supply", company="Supplies Inc", role="supplier",
        source="manual", created_at=utcnow(), updated_at=utcnow(),
    )
    session.add_all([client_contact, supplier_contact])

    # Email account + messages (for email-derived contacts)
    email_account = EmailAccount(
        id=uuid4(), organization_id=ORG_ID, user_id=HENRY_USER_ID,
        provider="microsoft", email_address="henry@wastegurus.ca",
        visibility="shared", sync_enabled=True,
    )
    session.add(email_account)

    msg1 = EmailMessage(
        id=uuid4(), organization_id=ORG_ID, email_account_id=email_account.id,
        provider_message_id="msg-1", subject="Quote request",
        sender_email="dave@contractor.com", sender_name="Dave Contractor",
        body_text="Hi", received_at=utcnow(), folder="inbox",
        triage_status="pending", is_read=False, is_starred=False, has_attachments=False,
    )
    msg2 = EmailMessage(
        id=uuid4(), organization_id=ORG_ID, email_account_id=email_account.id,
        provider_message_id="msg-2", subject="Follow up",
        sender_email="dave@contractor.com", sender_name="Dave Contractor",
        body_text="Following up", received_at=utcnow(), folder="inbox",
        triage_status="pending", is_read=False, is_starred=False, has_attachments=False,
    )
    msg3 = EmailMessage(
        id=uuid4(), organization_id=ORG_ID, email_account_id=email_account.id,
        provider_message_id="msg-3", subject="Invoice",
        sender_email="eve@vendor.com", sender_name="Eve Vendor",
        body_text="Invoice attached", received_at=utcnow(), folder="inbox",
        triage_status="pending", is_read=False, is_starred=False, has_attachments=False,
    )
    session.add_all([msg1, msg2, msg3])

    await session.commit()
    return {
        "org": org,
        "henry": henry, "samir": samir,
        "client_contact": client_contact, "supplier_contact": supplier_contact,
        "email_account": email_account,
    }


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contact_defaults():
    """OrgContact defaults are correct."""
    contact = OrgContact(
        id=uuid4(), organization_id=ORG_ID, email="test@example.com",
    )
    assert contact.source == "manual"
    assert contact.name == ""
    assert contact.company == ""


@pytest.mark.asyncio
async def test_contact_unique_email_per_org():
    """Cannot create two contacts with same email in one org."""
    maker = await _make_session()
    async with maker() as session:
        now = utcnow()
        c1 = OrgContact(
            id=uuid4(), organization_id=ORG_ID, email="dupe@test.com",
            created_at=now, updated_at=now,
        )
        c2 = OrgContact(
            id=uuid4(), organization_id=ORG_ID, email="dupe@test.com",
            created_at=now, updated_at=now,
        )
        session.add(c1)
        await session.commit()
        session.add(c2)
        with pytest.raises(Exception):  # IntegrityError
            await session.commit()


# ---------------------------------------------------------------------------
# Query tests (manual contacts)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_contacts_by_org():
    """List contacts scoped to org."""
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        stmt = select(OrgContact).where(OrgContact.organization_id == ORG_ID)
        result = await session.execute(stmt)
        contacts = list(result.scalars().all())
        assert len(contacts) == 2


@pytest.mark.asyncio
async def test_search_contacts_by_name():
    """Search contacts by name substring."""
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        search = "%bob%"
        stmt = select(OrgContact).where(
            OrgContact.organization_id == ORG_ID,
            func.lower(OrgContact.name).like(search),
        )
        result = await session.execute(stmt)
        contacts = list(result.scalars().all())
        assert len(contacts) == 1
        assert contacts[0].email == "bob@client.com"


@pytest.mark.asyncio
async def test_search_contacts_by_company():
    """Search contacts by company name."""
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        search = "%supplies%"
        stmt = select(OrgContact).where(
            OrgContact.organization_id == ORG_ID,
            func.lower(OrgContact.company).like(search),
        )
        result = await session.execute(stmt)
        contacts = list(result.scalars().all())
        assert len(contacts) == 1
        assert contacts[0].name == "Alice Supply"


# ---------------------------------------------------------------------------
# Email-derived contacts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_derived_contacts_deduplicated():
    """Email senders are deduplicated (Dave sent 2 emails but appears once)."""
    maker = await _make_session()
    async with maker() as session:
        data = await _seed(session)
        email_account = data["email_account"]

        # Query distinct senders from shared accounts
        from sqlalchemy import distinct as sa_distinct

        shared_account_ids = select(EmailAccount.id).where(
            EmailAccount.organization_id == ORG_ID,
            EmailAccount.visibility == "shared",
        )
        stmt = select(
            sa_distinct(EmailMessage.sender_email),
        ).where(
            EmailMessage.organization_id == ORG_ID,
            EmailMessage.email_account_id.in_(shared_account_ids),
        )
        result = await session.execute(stmt)
        emails = {row[0] for row in result.all()}
        assert "dave@contractor.com" in emails
        assert "eve@vendor.com" in emails
        assert len(emails) == 2  # Dave deduplicated


# ---------------------------------------------------------------------------
# Unified search (simulating agent search logic)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unified_search_finds_members():
    """Unified search finds org members by name."""
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        search = "%samir%"
        stmt = (
            select(User.email, User.name)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .where(
                OrganizationMember.organization_id == ORG_ID,
                func.lower(User.name).like(search),
            )
        )
        result = await session.execute(stmt)
        rows = list(result.all())
        assert len(rows) == 1
        assert rows[0].email == "samir@wastegurus.ca"


@pytest.mark.asyncio
async def test_unified_search_finds_manual_contacts():
    """Unified search finds manual contacts by name."""
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        search = "%bob%"
        stmt = select(OrgContact).where(
            OrgContact.organization_id == ORG_ID,
            func.lower(OrgContact.name).like(search),
        )
        result = await session.execute(stmt)
        contacts = list(result.scalars().all())
        assert len(contacts) == 1
        assert contacts[0].email == "bob@client.com"


@pytest.mark.asyncio
async def test_unified_search_finds_email_senders():
    """Unified search finds people from email history."""
    maker = await _make_session()
    async with maker() as session:
        await _seed(session)
        search = "%dave%"
        shared_ids = select(EmailAccount.id).where(
            EmailAccount.organization_id == ORG_ID,
            EmailAccount.visibility == "shared",
        )
        from sqlalchemy import distinct as sa_distinct

        stmt = select(
            sa_distinct(EmailMessage.sender_email),
        ).where(
            EmailMessage.organization_id == ORG_ID,
            EmailMessage.email_account_id.in_(shared_ids),
            or_(
                func.lower(EmailMessage.sender_email).like(search),
                func.lower(EmailMessage.sender_name).like(search),
            ),
        )
        result = await session.execute(stmt)
        emails = {row[0] for row in result.all()}
        assert len(emails) == 1
        assert "dave@contractor.com" in emails


@pytest.mark.asyncio
async def test_private_email_contacts_excluded():
    """Email senders from private accounts are not returned."""
    maker = await _make_session()
    async with maker() as session:
        data = await _seed(session)

        # Add a private email account with a message
        private_account = EmailAccount(
            id=uuid4(), organization_id=ORG_ID, user_id=SAMIR_USER_ID,
            provider="microsoft", email_address="samir@wastegurus.ca",
            visibility="private", sync_enabled=True,
        )
        session.add(private_account)

        private_msg = EmailMessage(
            id=uuid4(), organization_id=ORG_ID, email_account_id=private_account.id,
            provider_message_id="msg-private", subject="Personal",
            sender_email="secret@personal.com", sender_name="Secret Person",
            body_text="Private", received_at=utcnow(), folder="inbox",
            triage_status="pending", is_read=False, is_starred=False, has_attachments=False,
        )
        session.add(private_msg)
        await session.commit()

        # Search should NOT find "secret" because it's from a private account
        from sqlalchemy import distinct as sa_distinct

        search = "%secret%"
        shared_ids = select(EmailAccount.id).where(
            EmailAccount.organization_id == ORG_ID,
            EmailAccount.visibility == "shared",
        )
        stmt = select(
            sa_distinct(EmailMessage.sender_email),
        ).where(
            EmailMessage.organization_id == ORG_ID,
            EmailMessage.email_account_id.in_(shared_ids),
            func.lower(EmailMessage.sender_name).like(search),
        )
        result = await session.execute(stmt)
        emails = {row[0] for row in result.all()}
        assert len(emails) == 0
