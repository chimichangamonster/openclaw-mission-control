"""Bookkeeping API — workers, clients, jobs, placements, timesheets, expenses, invoices, transactions, reports, exports."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import ORG_RATE_LIMIT_DEP, require_feature

from .clients import router as clients_router
from .expenses import router as expenses_router
from .exports import router as exports_router
from .invoices import router as invoices_router
from .jobs import router as jobs_router
from .placements import router as placements_router
from .reports import router as reports_router
from .timesheets import router as timesheets_router
from .transactions import router as transactions_router
from .workers import router as workers_router

router = APIRouter(
    prefix="/bookkeeping",
    tags=["bookkeeping"],
    dependencies=[Depends(require_feature("bookkeeping")), ORG_RATE_LIMIT_DEP],
)

router.include_router(clients_router)
router.include_router(workers_router)
router.include_router(jobs_router)
router.include_router(placements_router)
router.include_router(timesheets_router)
router.include_router(expenses_router)
router.include_router(invoices_router)
router.include_router(transactions_router)
router.include_router(reports_router)
router.include_router(exports_router)
