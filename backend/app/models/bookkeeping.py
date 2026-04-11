"""Bookkeeping models — workers, clients, jobs, placements, timesheets, expenses, invoices, transactions."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped


class BkClient(TenantScoped, table=True):
    """A billing client / customer company."""

    __tablename__ = "bk_clients"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    name: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    billing_terms: str = "net30"
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class BkWorker(TenantScoped, table=True):
    """A crew member / worker in the staffing pool."""

    __tablename__ = "bk_workers"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    hourly_rate: Optional[float] = None
    # Safety certifications stored as JSON array
    # [{"name": "CSTS", "expiry_date": "2026-06-01", "certificate_number": "123"}]
    safety_certs_json: str = Field(default="[]")
    csts_expiry: Optional[date] = None
    ossa_expiry: Optional[date] = None
    first_aid_expiry: Optional[date] = None
    h2s_expiry: Optional[date] = None
    status: str = "available"  # available, placed, on_leave, inactive
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def safety_certs(self) -> list[dict[str, Any]]:
        return json.loads(self.safety_certs_json)  # type: ignore[no-any-return]


class BkJob(TenantScoped, table=True):
    """A project / job at a site."""

    __tablename__ = "bk_jobs"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    client_id: Optional[UUID] = Field(default=None, foreign_key="bk_clients.id", index=True)
    name: str
    site_address: Optional[str] = None
    job_type: Optional[str] = None
    status: str = "active"  # active, completed, on_hold, cancelled
    budget: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class BkPlacement(TenantScoped, table=True):
    """A worker assigned to a job with bill/pay rates."""

    __tablename__ = "bk_placements"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    worker_id: UUID = Field(foreign_key="bk_workers.id", index=True)
    job_id: UUID = Field(foreign_key="bk_jobs.id", index=True)
    start_date: date
    end_date: Optional[date] = None
    bill_rate: float  # what the client pays per hour
    pay_rate: float  # what the worker gets per hour
    status: str = "active"  # active, completed, cancelled
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class BkTimesheet(TenantScoped, table=True):
    """Daily hours logged for a worker on a job."""

    __tablename__ = "bk_timesheets"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    placement_id: Optional[UUID] = Field(default=None, foreign_key="bk_placements.id", index=True)
    worker_id: UUID = Field(foreign_key="bk_workers.id", index=True)
    job_id: UUID = Field(foreign_key="bk_jobs.id", index=True)
    work_date: date
    regular_hours: float = 0.0
    overtime_hours: float = 0.0
    notes: Optional[str] = None
    status: str = "pending"  # pending, approved, rejected
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class BkExpense(TenantScoped, table=True):
    """An expense with optional OCR receipt data."""

    __tablename__ = "bk_expenses"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    worker_id: Optional[UUID] = Field(default=None, foreign_key="bk_workers.id", index=True)
    job_id: Optional[UUID] = Field(default=None, foreign_key="bk_jobs.id", index=True)
    amount: float = 0.0
    gst_amount: float = 0.0
    category: Optional[str] = None
    vendor: Optional[str] = None
    description: Optional[str] = None
    receipt_url: Optional[str] = None
    ocr_data_json: str = Field(default="{}")
    expense_date: date = Field(default_factory=date.today)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def ocr_data(self) -> dict[str, Any]:
        return json.loads(self.ocr_data_json)  # type: ignore[no-any-return]


class BkInvoice(TenantScoped, table=True):
    """An invoice to a client."""

    __tablename__ = "bk_invoices"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    client_id: UUID = Field(foreign_key="bk_clients.id", index=True)
    invoice_number: Optional[str] = None
    status: str = "draft"  # draft, sent, paid, overdue, cancelled
    subtotal: float = 0.0
    gst_amount: float = 0.0
    total: float = 0.0
    issued_date: Optional[date] = None
    due_date: Optional[date] = None
    paid_date: Optional[date] = None
    exported_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class BkInvoiceLine(TenantScoped, table=True):
    """A line item on an invoice."""

    __tablename__ = "bk_invoice_lines"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    invoice_id: UUID = Field(foreign_key="bk_invoices.id", index=True)
    description: str = ""
    quantity: float = 0.0
    unit_price: float = 0.0
    amount: float = 0.0
    timesheet_id: Optional[UUID] = Field(default=None, foreign_key="bk_timesheets.id")
    created_at: datetime = Field(default_factory=utcnow)


class BkTransaction(TenantScoped, table=True):
    """A general ledger entry (income or expense)."""

    __tablename__ = "bk_transactions"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    type: str  # income, expense
    amount: float = 0.0
    gst_amount: float = 0.0
    category: Optional[str] = None
    description: Optional[str] = None
    txn_date: date = Field(default_factory=date.today)
    job_id: Optional[UUID] = Field(default=None, foreign_key="bk_jobs.id", index=True)
    expense_id: Optional[UUID] = Field(default=None, foreign_key="bk_expenses.id")
    invoice_id: Optional[UUID] = Field(default=None, foreign_key="bk_invoices.id")
    created_at: datetime = Field(default_factory=utcnow)
