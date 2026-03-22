"""Bookkeeping workers CRUD + safety cert tracking."""

from __future__ import annotations

import json
from datetime import date, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select, col

from app.api.deps import ORG_ACTOR_DEP
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.bookkeeping import BkWorker, BkPlacement
from app.services.organizations import OrganizationContext

router = APIRouter(prefix="/workers")


class WorkerCreate(BaseModel):
    name: str
    phone: str | None = None
    email: str | None = None
    role: str | None = None
    hourly_rate: float | None = None
    safety_certs: list[dict] | None = None
    csts_expiry: date | None = None
    ossa_expiry: date | None = None
    first_aid_expiry: date | None = None
    h2s_expiry: date | None = None
    status: str = "available"
    notes: str | None = None


class WorkerUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    role: str | None = None
    hourly_rate: float | None = None
    safety_certs: list[dict] | None = None
    csts_expiry: date | None = None
    ossa_expiry: date | None = None
    first_aid_expiry: date | None = None
    h2s_expiry: date | None = None
    status: str | None = None
    notes: str | None = None


@router.post("", status_code=201)
async def create_worker(payload: WorkerCreate, org_ctx: OrganizationContext = ORG_ACTOR_DEP):
    async with async_session_maker() as session:
        worker = BkWorker(
            id=uuid4(),
            organization_id=org_ctx.organization.id,
            name=payload.name,
            phone=payload.phone,
            email=payload.email,
            role=payload.role,
            hourly_rate=payload.hourly_rate,
            safety_certs_json=json.dumps(payload.safety_certs or []),
            csts_expiry=payload.csts_expiry,
            ossa_expiry=payload.ossa_expiry,
            first_aid_expiry=payload.first_aid_expiry,
            h2s_expiry=payload.h2s_expiry,
            status=payload.status,
            notes=payload.notes,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(worker)
        await session.commit()
        await session.refresh(worker)
        return _serialize(worker)


@router.get("")
async def list_workers(status: str | None = None, org_ctx: OrganizationContext = ORG_ACTOR_DEP):
    async with async_session_maker() as session:
        stmt = select(BkWorker).where(BkWorker.organization_id == org_ctx.organization.id)
        if status:
            stmt = stmt.where(BkWorker.status == status)
        stmt = stmt.order_by(BkWorker.name)
        result = await session.execute(stmt)
        return [_serialize(w) for w in result.scalars().all()]


@router.get("/available")
async def available_workers(org_ctx: OrganizationContext = ORG_ACTOR_DEP):
    async with async_session_maker() as session:
        # Workers with status "available" who don't have active placements
        active_placed = select(BkPlacement.worker_id).where(
            BkPlacement.organization_id == org_ctx.organization.id,
            BkPlacement.status == "active",
        )
        stmt = (
            select(BkWorker)
            .where(
                BkWorker.organization_id == org_ctx.organization.id,
                BkWorker.status == "available",
                ~BkWorker.id.in_(active_placed),  # type: ignore[union-attr]
            )
            .order_by(BkWorker.name)
        )
        result = await session.execute(stmt)
        return [_serialize(w) for w in result.scalars().all()]


@router.get("/expiring-certs")
async def expiring_certs(days: int = Query(default=30), org_ctx: OrganizationContext = ORG_ACTOR_DEP):
    cutoff = date.today() + timedelta(days=days)
    async with async_session_maker() as session:
        stmt = (
            select(BkWorker)
            .where(
                BkWorker.organization_id == org_ctx.organization.id,
                BkWorker.status != "inactive",
            )
            .where(
                (BkWorker.csts_expiry <= cutoff)  # type: ignore[operator]
                | (BkWorker.ossa_expiry <= cutoff)  # type: ignore[operator]
                | (BkWorker.first_aid_expiry <= cutoff)  # type: ignore[operator]
                | (BkWorker.h2s_expiry <= cutoff)  # type: ignore[operator]
            )
        )
        result = await session.execute(stmt)
        return [_serialize(w) for w in result.scalars().all()]


@router.get("/{worker_id}")
async def get_worker(worker_id: str, org_ctx: OrganizationContext = ORG_ACTOR_DEP):
    async with async_session_maker() as session:
        result = await session.execute(
            select(BkWorker).where(BkWorker.id == worker_id, BkWorker.organization_id == org_ctx.organization.id)
        )
        worker = result.scalars().first()
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found")
        return _serialize(worker)


@router.put("/{worker_id}")
async def update_worker(worker_id: str, payload: WorkerUpdate, org_ctx: OrganizationContext = ORG_ACTOR_DEP):
    async with async_session_maker() as session:
        result = await session.execute(
            select(BkWorker).where(BkWorker.id == worker_id, BkWorker.organization_id == org_ctx.organization.id)
        )
        worker = result.scalars().first()
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found")

        data = payload.model_dump(exclude_none=True)
        if "safety_certs" in data:
            worker.safety_certs_json = json.dumps(data.pop("safety_certs"))
        for field, value in data.items():
            setattr(worker, field, value)
        worker.updated_at = utcnow()
        await session.commit()
        await session.refresh(worker)
        return _serialize(worker)


def _serialize(w: BkWorker) -> dict:
    return {
        "id": str(w.id),
        "name": w.name,
        "phone": w.phone,
        "email": w.email,
        "role": w.role,
        "hourly_rate": w.hourly_rate,
        "safety_certs": w.safety_certs,
        "csts_expiry": str(w.csts_expiry) if w.csts_expiry else None,
        "ossa_expiry": str(w.ossa_expiry) if w.ossa_expiry else None,
        "first_aid_expiry": str(w.first_aid_expiry) if w.first_aid_expiry else None,
        "h2s_expiry": str(w.h2s_expiry) if w.h2s_expiry else None,
        "status": w.status,
        "notes": w.notes,
        "created_at": w.created_at.isoformat(),
        "updated_at": w.updated_at.isoformat(),
    }
