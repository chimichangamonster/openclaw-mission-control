"""Bookkeeping placements — assign workers to jobs with bill/pay rates."""


from __future__ import annotations

from typing import Any

from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import ORG_ACTOR_DEP
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.bookkeeping import BkPlacement, BkWorker
from app.services.organizations import OrganizationContext

router = APIRouter(prefix="/placements")


class PlacementCreate(BaseModel):
    worker_id: str
    job_id: str
    start_date: date
    bill_rate: float
    pay_rate: float
    notes: str | None = None


@router.post("", status_code=201)
async def create_placement(payload: PlacementCreate, org_ctx: OrganizationContext = ORG_ACTOR_DEP) -> Any:
    org_id = org_ctx.organization.id
    async with async_session_maker() as session:
        placement = BkPlacement(
            id=uuid4(),
            organization_id=org_id,
            worker_id=payload.worker_id,
            job_id=payload.job_id,
            start_date=payload.start_date,
            bill_rate=payload.bill_rate,
            pay_rate=payload.pay_rate,
            notes=payload.notes,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(placement)

        # Auto-set worker status to "placed"
        worker_result = await session.execute(
            select(BkWorker).where(
                BkWorker.id == payload.worker_id, BkWorker.organization_id == org_id
            )
        )
        worker = worker_result.scalars().first()
        if worker:
            worker.status = "placed"
            worker.updated_at = utcnow()

        await session.commit()
        await session.refresh(placement)
        return _serialize(placement)


@router.get("")
async def list_placements(
    status: str | None = None,
    job_id: str | None = None,
    worker_id: str | None = None,
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> Any:
    async with async_session_maker() as session:
        stmt = select(BkPlacement).where(BkPlacement.organization_id == org_ctx.organization.id)
        if status:
            stmt = stmt.where(BkPlacement.status == status)
        if job_id:
            stmt = stmt.where(BkPlacement.job_id == job_id)
        if worker_id:
            stmt = stmt.where(BkPlacement.worker_id == worker_id)
        stmt = stmt.order_by(BkPlacement.created_at.desc())  # type: ignore[attr-defined]
        result = await session.execute(stmt)
        return [_serialize(p) for p in result.scalars().all()]


@router.get("/{placement_id}")
async def get_placement(placement_id: str, org_ctx: OrganizationContext = ORG_ACTOR_DEP) -> Any:
    async with async_session_maker() as session:
        result = await session.execute(
            select(BkPlacement).where(
                BkPlacement.id == placement_id,
                BkPlacement.organization_id == org_ctx.organization.id,
            )
        )
        placement = result.scalars().first()
        if not placement:
            raise HTTPException(status_code=404, detail="Placement not found")
        return _serialize(placement)


@router.put("/{placement_id}/end")
async def end_placement(placement_id: str, org_ctx: OrganizationContext = ORG_ACTOR_DEP) -> Any:
    """Mark a placement as completed and set worker back to available if no other active placements."""
    org_id = org_ctx.organization.id
    async with async_session_maker() as session:
        result = await session.execute(
            select(BkPlacement).where(
                BkPlacement.id == placement_id, BkPlacement.organization_id == org_id
            )
        )
        placement = result.scalars().first()
        if not placement:
            raise HTTPException(status_code=404, detail="Placement not found")

        placement.status = "completed"
        placement.end_date = date.today()
        placement.updated_at = utcnow()

        # Check if worker has other active placements
        other = await session.execute(
            select(BkPlacement).where(
                BkPlacement.worker_id == placement.worker_id,
                BkPlacement.organization_id == org_id,
                BkPlacement.status == "active",
                BkPlacement.id != placement.id,
            )
        )
        if not other.scalars().first():
            worker_result = await session.execute(
                select(BkWorker).where(
                    BkWorker.id == placement.worker_id, BkWorker.organization_id == org_id
                )
            )
            worker = worker_result.scalars().first()
            if worker:
                worker.status = "available"
                worker.updated_at = utcnow()

        await session.commit()
        await session.refresh(placement)
        return _serialize(placement)


def _serialize(p: BkPlacement) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "worker_id": str(p.worker_id),
        "job_id": str(p.job_id),
        "start_date": str(p.start_date),
        "end_date": str(p.end_date) if p.end_date else None,
        "bill_rate": p.bill_rate,
        "pay_rate": p.pay_rate,
        "status": p.status,
        "notes": p.notes,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }
