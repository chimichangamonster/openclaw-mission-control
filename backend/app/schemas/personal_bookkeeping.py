"""Schemas for the Personal bookkeeping (sole-prop) API.

Deliberately separate from ``bookkeeping`` (client-service businesses).
See ``app/models/personal_bookkeeping.py`` for model shape.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.personal_bookkeeping import (
    BUCKET_VALUES,
    RECONCILIATION_STATUSES,
    STATEMENT_SOURCES,
)


# ---------------------------------------------------------------------------
# Reconciliation months
# ---------------------------------------------------------------------------


class ReconciliationMonthRead(BaseModel):
    id: UUID
    period: str
    status: str
    td_line_count: int
    amex_line_count: int
    business_income: float
    business_expenses: float
    vehicle_expenses: float
    gst_collected_informational: float
    gst_paid_informational: float
    flagged_line_count: int
    locked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReconciliationMonthCreate(BaseModel):
    period: str = Field(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


# ---------------------------------------------------------------------------
# Statement files
# ---------------------------------------------------------------------------


class StatementFileRead(BaseModel):
    id: UUID
    reconciliation_month_id: UUID | None
    period: str
    source: str
    original_filename: str
    content_type: str
    sha256: str
    byte_size: int
    local_path: str | None
    retention_until: date
    uploaded_at: datetime


class StatementImportResult(BaseModel):
    statement_file_id: UUID
    inserted_count: int
    skipped_count: int
    classification_summary: dict[str, int]


class StatementFileUpdate(BaseModel):
    local_path: str | None = None


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


class TransactionRead(BaseModel):
    id: UUID
    reconciliation_month_id: UUID
    statement_file_id: UUID | None
    source: str
    txn_date: date
    description: str
    amount: float
    incoming: bool
    bucket: str
    t2125_line: str | None
    category: str | None
    needs_receipt: bool
    receipt_filed: bool
    user_note: str | None
    classified_by: str
    classified_at: datetime
    original_row_hash: str


class TransactionUpdate(BaseModel):
    bucket: str | None = None
    t2125_line: str | None = None
    category: str | None = None
    needs_receipt: bool | None = None
    receipt_filed: bool | None = None
    user_note: str | None = None


class PromoteToRuleRequest(BaseModel):
    # Optional override — if omitted the pattern is derived as a literal
    # escape of the txn description.
    pattern: str | None = None
    applies_to_source: str | None = None  # "TD", "AMEX", or None for both


# ---------------------------------------------------------------------------
# Vendor rules
# ---------------------------------------------------------------------------


class VendorRuleRead(BaseModel):
    id: UUID
    pattern: str
    bucket: str
    t2125_line: str | None
    category: str | None
    needs_receipt: bool
    note: str | None
    applies_to_source: str | None
    source_month: str
    active: bool
    created_at: datetime
    updated_at: datetime


class VendorRuleCreate(BaseModel):
    pattern: str
    bucket: str
    t2125_line: str | None = None
    category: str | None = None
    needs_receipt: bool = False
    note: str | None = None
    applies_to_source: str | None = None


class VendorRuleUpdate(BaseModel):
    pattern: str | None = None
    bucket: str | None = None
    t2125_line: str | None = None
    category: str | None = None
    needs_receipt: bool | None = None
    note: str | None = None
    applies_to_source: str | None = None
    active: bool | None = None


# ---------------------------------------------------------------------------
# Validation helpers (used by the router, not exposed as schemas)
# ---------------------------------------------------------------------------


def validate_bucket(value: str) -> str:
    if value not in BUCKET_VALUES:
        raise ValueError(f"Invalid bucket: {value!r}. Must be one of {BUCKET_VALUES}.")
    return value


def validate_source(value: str) -> str:
    if value not in STATEMENT_SOURCES:
        raise ValueError(
            f"Invalid source: {value!r}. Must be one of {STATEMENT_SOURCES}."
        )
    return value


def validate_status(value: str) -> str:
    if value not in RECONCILIATION_STATUSES:
        raise ValueError(
            f"Invalid status: {value!r}. Must be one of {RECONCILIATION_STATUSES}."
        )
    return value
