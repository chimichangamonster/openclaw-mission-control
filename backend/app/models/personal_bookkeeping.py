"""Personal (sole-prop) bookkeeping models.

Deliberately separate from ``bk_*`` tables, which serve client-service
businesses with jobs/invoices. These models support monthly statement
reconciliation, T2125 line-code tagging, receipt tracking, and
per-org vendor rule learning for a sole-proprietor workflow.

Gated by ``personal_bookkeeping`` feature flag + Personal-org-slug check
on every endpoint. Never generalised across orgs without a deliberate build.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, Index, Text, UniqueConstraint
from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped

# Bucket enum values. Kept as strings (not a DB enum) so adding a bucket
# later doesn't require a migration — only a code change + classifier update.
BUCKET_VALUES = (
    "business",        # Deductible business expense (with t2125_line set)
    "personal",        # Henz's personal spending, out of scope for T2125
    "vehicle",         # Goes to Motor Vehicle % sheet — business-km pct applies
    "gift",            # Incoming money confirmed as a personal gift, not revenue
    "transfer",        # Internal (CC payment, ATM, bank fees) — not an expense
    "ambiguous",       # Needs Henz's review; blocks month lock until cleared
    "income_pending",  # Incoming money awaiting classification (business vs gift)
)

RECONCILIATION_STATUSES = ("draft", "reviewed", "locked")
STATEMENT_SOURCES = ("TD", "AMEX")


class PersonalReconciliationMonth(TenantScoped, table=True):
    """One reconciliation period (a calendar month) for Personal bookkeeping.

    Holds cached totals so the Reports tab can render YTD views without
    re-aggregating every transaction on every request.
    """

    __tablename__ = "personal_reconciliation_months"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint("organization_id", "period", name="uq_personal_recon_org_period"),
        Index("ix_personal_recon_org_status", "organization_id", "status"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    period: str = Field(index=True)  # "YYYY-MM"
    status: str = Field(default="draft")  # draft | reviewed | locked

    td_line_count: int = 0
    amex_line_count: int = 0

    business_income: float = 0.0
    business_expenses: float = 0.0
    vehicle_expenses: float = 0.0
    gst_collected_informational: float = 0.0  # 5% of business income ÷ 1.05
    gst_paid_informational: float = 0.0  # 5% of business expenses ÷ 1.05

    flagged_line_count: int = 0  # ambiguous + income_pending — must be zero to lock

    locked_at: datetime | None = None
    locked_by_user_id: UUID | None = Field(default=None, foreign_key="users.id")

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class PersonalTransaction(TenantScoped, table=True):
    """One line from a TD or AMEX statement, tagged against a T2125 line."""

    __tablename__ = "personal_transactions"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        Index("ix_personal_txn_month", "reconciliation_month_id"),
        Index("ix_personal_txn_org_bucket", "organization_id", "bucket"),
        Index("ix_personal_txn_hash", "organization_id", "original_row_hash"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    reconciliation_month_id: UUID = Field(
        foreign_key="personal_reconciliation_months.id",
    )
    statement_file_id: UUID | None = Field(
        default=None,
        foreign_key="personal_statement_files.id",
    )

    source: str  # TD | AMEX
    txn_date: date
    description: str = Field(sa_column=Column(Text, nullable=False))
    amount: float  # Signed. Positive = debit/charge; negative = credit/refund.
    incoming: bool = False  # True if this appeared in a credit column (incoming money)

    bucket: str = Field(default="ambiguous", index=True)
    t2125_line: str | None = None  # e.g. "8810", "8871", "9200"
    category: str | None = None  # Human label: "Office", "Mgmt/Admin", "Travel"

    needs_receipt: bool = False
    receipt_filed: bool = False
    receipt_asset_id: UUID | None = None  # Linked receipt file (Session 4)

    user_note: str | None = Field(default=None, sa_column=Column(Text))
    classified_by: str = "auto"  # auto | user
    classified_at: datetime = Field(default_factory=utcnow)

    # SHA-256 of (source + iso_date + description + amount_str) — used to
    # de-dup when the same statement is re-uploaded.
    original_row_hash: str = Field(index=True)

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class PersonalVendorRule(TenantScoped, table=True):
    """Learned or seeded rule that auto-classifies a statement line by vendor.

    Seeded from reconcile_month.py seed rules on first org setup. Grows as
    Henz classifies ambiguous lines and confirms rules to promote.
    """

    __tablename__ = "personal_vendor_rules"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        Index("ix_personal_vendor_rule_org_active", "organization_id", "active"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)

    pattern: str = Field(sa_column=Column(Text, nullable=False))  # Python regex
    bucket: str  # One of BUCKET_VALUES
    t2125_line: str | None = None
    category: str | None = None
    needs_receipt: bool = False
    note: str | None = Field(default=None, sa_column=Column(Text))

    # "TD" | "AMEX" | None (both). Controls whether rule applies to one source.
    applies_to_source: str | None = None

    # "seed" for built-in rules, "YYYY-MM" for rules learned during a month.
    source_month: str = "seed"
    active: bool = True

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class PersonalStatementFile(TenantScoped, table=True):
    """Uploaded TD CSV or AMEX XLS statement, encrypted at rest.

    Authoritative server-side copy for CRA 6-year retention. ``local_path``
    is an optional reference to Henz's own mirror (OneDrive folder) — MC
    never reads from it, only displays it so Henz can find the local copy.
    """

    __tablename__ = "personal_statement_files"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "sha256",
            name="uq_personal_statement_org_sha256",
        ),
        Index("ix_personal_statement_org_period", "organization_id", "period"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)

    reconciliation_month_id: UUID | None = Field(
        default=None,
        foreign_key="personal_reconciliation_months.id",
    )
    period: str  # "YYYY-MM" — redundant with month FK but allows query before month exists

    source: str  # TD | AMEX
    original_filename: str
    content_type: str
    sha256: str = Field(index=True)
    byte_size: int

    file_path: str = Field(sa_column=Column(Text, nullable=False))
    local_path: str | None = Field(default=None, sa_column=Column(Text))

    retention_until: date  # CRA 6-year rule: Dec 31 of (tax_year + 6)
    replaced_by_id: UUID | None = Field(
        default=None,
        foreign_key="personal_statement_files.id",
    )

    uploaded_at: datetime = Field(default_factory=utcnow)
    uploaded_by_user_id: UUID | None = Field(default=None, foreign_key="users.id")
