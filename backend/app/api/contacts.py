"""Organization contacts CRUD endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import ORG_MEMBER_DEP, ORG_RATE_LIMIT_DEP, SESSION_DEP
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.org_contacts import OrgContact
from app.schemas.contacts import OrgContactCreate, OrgContactRead, OrgContactUpdate
from app.services.organizations import OrganizationContext

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)
router = APIRouter(
    prefix="/contacts",
    tags=["contacts"],
    dependencies=[ORG_RATE_LIMIT_DEP],
)


@router.get("", response_model=list[OrgContactRead])
async def list_contacts(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
    q: str = Query(default="", description="Search name, email, or company"),
    source: str = Query(default="", description="Filter by source: manual, email"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[OrgContact]:
    """List contacts for the current organization."""
    stmt = (
        select(OrgContact)
        .where(OrgContact.organization_id == ctx.organization.id)  # type: ignore[arg-type]
        .order_by(OrgContact.name, OrgContact.email)
        .offset(offset)
        .limit(limit)
    )
    if q:
        search = f"%{q.lower()}%"
        from sqlalchemy import func, or_

        stmt = stmt.where(
            or_(
                func.lower(OrgContact.name).like(search),
                func.lower(OrgContact.email).like(search),
                func.lower(OrgContact.company).like(search),
            )
        )
    if source:
        stmt = stmt.where(OrgContact.source == source)  # type: ignore[arg-type]
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=OrgContactRead, status_code=status.HTTP_201_CREATED)
async def create_contact(
    payload: OrgContactCreate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> OrgContact:
    """Create a new contact."""
    # Check for duplicate email in this org
    existing = (
        await session.execute(
            select(OrgContact).where(
                OrgContact.organization_id == ctx.organization.id,  # type: ignore[arg-type]
                OrgContact.email == payload.email.lower(),  # type: ignore[arg-type]
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Contact with email {payload.email} already exists.",
        )

    now = utcnow()
    contact = OrgContact(
        id=uuid4(),
        organization_id=ctx.organization.id,
        created_by_user_id=ctx.member.user_id,
        email=payload.email.lower(),
        name=payload.name,
        company=payload.company,
        phone=payload.phone,
        role=payload.role,
        notes=payload.notes,
        source="manual",
        created_at=now,
        updated_at=now,
    )
    session.add(contact)
    await session.commit()
    await session.refresh(contact)
    return contact


@router.patch("/{contact_id}", response_model=OrgContactRead)
async def update_contact(
    contact_id: UUID,
    payload: OrgContactUpdate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> OrgContact:
    """Update a contact."""
    contact = await session.get(OrgContact, contact_id)
    if contact is None or contact.organization_id != ctx.organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    for field in ("name", "email", "company", "phone", "role", "notes"):
        value = getattr(payload, field, None)
        if value is not None:
            setattr(contact, field, value.lower() if field == "email" else value)

    contact.updated_at = utcnow()
    session.add(contact)
    await session.commit()
    await session.refresh(contact)
    return contact


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: UUID,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    """Delete a contact."""
    contact = await session.get(OrgContact, contact_id)
    if contact is None or contact.organization_id != ctx.organization.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await session.delete(contact)
    await session.commit()
