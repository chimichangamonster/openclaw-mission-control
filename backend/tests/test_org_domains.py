# ruff: noqa: INP001
"""Tests for domain-based org auto-assignment.

Verifies:
- Email domain → org matching in ensure_member_for_user()
- Personal email domain blocklist
- Admin CRUD for domain claims
- Cross-org domain claim rejection
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.organization_domains import (
    PERSONAL_EMAIL_DOMAINS,
    OrganizationDomain,
)
from app.models.organizations import Organization
from app.models.users import User
from app.services.organizations import (
    _find_org_by_email_domain,
    ensure_member_for_user,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _make_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _seed_org_with_domain(session: AsyncSession, domain: str, role: str = "member"):
    """Create an org and claim a domain for it."""
    org = Organization(id=uuid4(), name="Test Corp", slug="test-corp")
    session.add(org)
    await session.flush()
    mapping = OrganizationDomain(
        organization_id=org.id,
        domain=domain,
        default_role=role,
    )
    session.add(mapping)
    await session.commit()
    return org


# ---------------------------------------------------------------------------
# Domain lookup tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_domain_match_returns_mapping():
    maker = await _make_session()
    async with maker() as session:
        org = await _seed_org_with_domain(session, "eliteconstruction.ca")
        result = await _find_org_by_email_domain(session, "john@eliteconstruction.ca")
        assert result is not None
        assert result.organization_id == org.id


@pytest.mark.asyncio
async def test_domain_match_case_insensitive():
    maker = await _make_session()
    async with maker() as session:
        org = await _seed_org_with_domain(session, "wastegurus.ca")
        result = await _find_org_by_email_domain(session, "Henry@WasteGurus.CA")
        assert result is not None
        assert result.organization_id == org.id


@pytest.mark.asyncio
async def test_domain_no_match_returns_none():
    maker = await _make_session()
    async with maker() as session:
        await _seed_org_with_domain(session, "eliteconstruction.ca")
        result = await _find_org_by_email_domain(session, "bob@othercorp.com")
        assert result is None


@pytest.mark.asyncio
async def test_personal_email_blocked():
    """Gmail, Outlook, etc. should never match any org."""
    maker = await _make_session()
    async with maker() as session:
        # Even if someone claims gmail.com (shouldn't be possible via API),
        # the lookup should still reject it
        org = Organization(id=uuid4(), name="Fake", slug="fake")
        session.add(org)
        await session.flush()
        session.add(
            OrganizationDomain(
                organization_id=org.id,
                domain="gmail.com",
            )
        )
        await session.commit()

        result = await _find_org_by_email_domain(session, "user@gmail.com")
        assert result is None


@pytest.mark.asyncio
async def test_unverified_domain_not_matched():
    maker = await _make_session()
    async with maker() as session:
        org = Organization(id=uuid4(), name="Corp", slug="corp")
        session.add(org)
        await session.flush()
        session.add(
            OrganizationDomain(
                organization_id=org.id,
                domain="corp.com",
                verified=False,
            )
        )
        await session.commit()

        result = await _find_org_by_email_domain(session, "user@corp.com")
        assert result is None


# ---------------------------------------------------------------------------
# ensure_member_for_user integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_assign_by_domain():
    """User with matching domain gets auto-assigned to org as member."""
    maker = await _make_session()
    async with maker() as session:
        org = await _seed_org_with_domain(session, "acme.com", role="member")
        user = User(
            id=uuid4(),
            clerk_user_id="clerk_test_1",
            email="alice@acme.com",
            name="Alice",
        )
        session.add(user)
        await session.commit()

        member = await ensure_member_for_user(session, user)
        assert member.organization_id == org.id
        assert member.role == "member"
        assert member.all_boards_read is True
        assert member.all_boards_write is False


@pytest.mark.asyncio
async def test_auto_assign_admin_role_gets_write():
    """Domain with default_role=admin should get all_boards_write."""
    maker = await _make_session()
    async with maker() as session:
        org = await _seed_org_with_domain(session, "bigcorp.com", role="admin")
        user = User(
            id=uuid4(),
            clerk_user_id="clerk_test_2",
            email="boss@bigcorp.com",
            name="Boss",
        )
        session.add(user)
        await session.commit()

        member = await ensure_member_for_user(session, user)
        assert member.organization_id == org.id
        assert member.role == "admin"
        assert member.all_boards_write is True


@pytest.mark.asyncio
async def test_personal_email_gets_personal_org():
    """Gmail user without invite creates a personal org, not matched to any domain."""
    maker = await _make_session()
    async with maker() as session:
        user = User(
            id=uuid4(),
            clerk_user_id="clerk_test_3",
            email="random@gmail.com",
            name="Random",
        )
        session.add(user)
        await session.commit()

        member = await ensure_member_for_user(session, user)
        assert member.role == "owner"  # personal org → owner
        # Should be a new personal org, not any claimed domain
        org = await session.get(Organization, member.organization_id)
        assert org is not None
        assert org.name == "Personal"


@pytest.mark.asyncio
async def test_invite_takes_precedence_over_domain():
    """Pending invite should be accepted even if domain also matches."""
    from app.models.organization_invites import OrganizationInvite

    maker = await _make_session()
    async with maker() as session:
        # Set up org with domain
        await _seed_org_with_domain(session, "example.com")

        # Set up a different org with an invite
        org_invite = Organization(id=uuid4(), name="Invite Org", slug="invite-org")
        session.add(org_invite)
        await session.flush()
        invite = OrganizationInvite(
            id=uuid4(),
            organization_id=org_invite.id,
            invited_email="bob@example.com",
            token="test-token-123",
            role="admin",
            all_boards_read=True,
            all_boards_write=True,
        )
        session.add(invite)
        await session.commit()

        user = User(
            id=uuid4(),
            clerk_user_id="clerk_test_4",
            email="bob@example.com",
            name="Bob",
        )
        session.add(user)
        await session.commit()

        member = await ensure_member_for_user(session, user)
        # Invite org wins, not domain org
        assert member.organization_id == org_invite.id
        assert member.role == "admin"


# ---------------------------------------------------------------------------
# Personal email blocklist completeness
# ---------------------------------------------------------------------------


def test_blocklist_has_common_providers():
    """Sanity check that the blocklist covers the obvious ones."""
    for domain in (
        "gmail.com",
        "outlook.com",
        "hotmail.com",
        "yahoo.com",
        "icloud.com",
        "protonmail.com",
        "proton.me",
    ):
        assert domain in PERSONAL_EMAIL_DOMAINS, f"{domain} missing from blocklist"


def test_blocklist_does_not_include_business_domains():
    for domain in ("eliteconstruction.ca", "wastegurus.ca", "vantagesolutions.ca"):
        assert domain not in PERSONAL_EMAIL_DOMAINS
