"""Bookkeeping clients CRUD."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import ORG_ACTOR_DEP
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.bookkeeping import BkClient
from app.services.organizations import OrganizationContext

router = APIRouter(prefix="/clients")


class ClientCreate(BaseModel):
    name: str
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    address: str | None = None
    billing_terms: str = "net30"
    notes: str | None = None


class ClientUpdate(BaseModel):
    name: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    address: str | None = None
    billing_terms: str | None = None
    notes: str | None = None


@router.post("", status_code=201)
async def create_client(payload: ClientCreate, org_ctx: OrganizationContext = ORG_ACTOR_DEP) -> Any:
    async with async_session_maker() as session:
        client = BkClient(
            id=uuid4(),
            organization_id=org_ctx.organization.id,
            name=payload.name,
            contact_name=payload.contact_name,
            contact_email=payload.contact_email,
            contact_phone=payload.contact_phone,
            address=payload.address,
            billing_terms=payload.billing_terms,
            notes=payload.notes,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(client)
        await session.commit()
        await session.refresh(client)
        return _serialize(client)


@router.get("")
async def list_clients(org_ctx: OrganizationContext = ORG_ACTOR_DEP) -> Any:
    async with async_session_maker() as session:
        result = await session.execute(
            select(BkClient)
            .where(BkClient.organization_id == org_ctx.organization.id)
            .order_by(BkClient.name)
        )
        return [_serialize(c) for c in result.scalars().all()]


@router.get("/{client_id}")
async def get_client(client_id: str, org_ctx: OrganizationContext = ORG_ACTOR_DEP) -> Any:
    async with async_session_maker() as session:
        result = await session.execute(
            select(BkClient).where(
                BkClient.id == client_id, BkClient.organization_id == org_ctx.organization.id
            )
        )
        client = result.scalars().first()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        return _serialize(client)


@router.put("/{client_id}")
async def update_client(
    client_id: str, payload: ClientUpdate, org_ctx: OrganizationContext = ORG_ACTOR_DEP
) -> Any:
    async with async_session_maker() as session:
        result = await session.execute(
            select(BkClient).where(
                BkClient.id == client_id, BkClient.organization_id == org_ctx.organization.id
            )
        )
        client = result.scalars().first()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")

        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(client, field, value)
        client.updated_at = utcnow()
        await session.commit()
        await session.refresh(client)
        return _serialize(client)


def _serialize(c: BkClient) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "name": c.name,
        "contact_name": c.contact_name,
        "contact_email": c.contact_email,
        "contact_phone": c.contact_phone,
        "address": c.address,
        "billing_terms": c.billing_terms,
        "notes": c.notes,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }
