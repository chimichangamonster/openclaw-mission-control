"""Personal (sole-prop) bookkeeping API.

Every route is gated by both the ``personal_bookkeeping`` feature flag and
the ``personal`` org slug as defense-in-depth. Future clients who need
their own sole-prop tool will be configured explicitly during onboarding.

Companion models: ``app/models/personal_bookkeeping.py``.
Companion services: ``app/services/personal_bookkeeping/`` (parsers, classifier).
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import (
    ORG_ACTOR_DEP,
    SESSION_DEP,
    require_feature,
    require_org_role,
)
from app.core.config import settings
from app.core.encryption import encrypt_bytes
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.personal_bookkeeping import (
    BUCKET_VALUES,
    STATEMENT_SOURCES,
    PersonalReconciliationMonth,
    PersonalStatementFile,
    PersonalTransaction,
    PersonalVendorRule,
)
from app.schemas.personal_bookkeeping import (
    PromoteToRuleRequest,
    ReconciliationMonthCreate,
    ReconciliationMonthRead,
    StatementFileRead,
    StatementFileUpdate,
    StatementImportResult,
    TransactionRead,
    TransactionUpdate,
    VendorRuleCreate,
    VendorRuleRead,
    VendorRuleUpdate,
)
from app.services.organizations import OrganizationContext
from app.services.personal_bookkeeping.classifier import classify
from app.services.personal_bookkeeping.parsers import (
    ParsedTransaction,
    parse_amex_xls,
    parse_td_csv,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Slug defense-in-depth
# ---------------------------------------------------------------------------


async def require_personal_org(
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> OrganizationContext:
    """Block any org other than ``slug='personal'`` even if the flag is on.

    The feature flag is the real control plane — this is belt+suspenders.
    If we ever enable the flag for a second org by mistake, the slug gate
    prevents cross-org statement imports from hitting the wrong tables.
    """
    if org_ctx.organization.slug != "personal":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Personal bookkeeping is only available on the Personal org.",
        )
    return org_ctx


PERSONAL_ORG_DEP = Depends(require_personal_org)


router = APIRouter(
    prefix="/personal-bookkeeping",
    tags=["personal-bookkeeping"],
    dependencies=[
        Depends(require_feature("personal_bookkeeping")),
        PERSONAL_ORG_DEP,
    ],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _validate_period(period: str) -> str:
    if not _PERIOD_RE.match(period):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid period {period!r}. Expected YYYY-MM.",
        )
    return period


def _retention_date_for(period: str) -> date:
    """CRA 6-year rule: keep statement files until Dec 31 of (tax_year + 6)."""
    year = int(period.split("-")[0])
    return date(year + 6, 12, 31)


def _statements_root() -> Path:
    root = settings.personal_bookkeeping_statements_root
    if not root:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Personal bookkeeping storage not configured "
                "(PERSONAL_BOOKKEEPING_STATEMENTS_ROOT not set)."
            ),
        )
    return Path(root)


async def _get_month(
    session: AsyncSession, org_id: UUID, period: str
) -> PersonalReconciliationMonth | None:
    result = await session.execute(
        select(PersonalReconciliationMonth).where(
            PersonalReconciliationMonth.organization_id == org_id,
            PersonalReconciliationMonth.period == period,
        )
    )
    return result.scalars().first()


async def _get_or_create_month(
    session: AsyncSession, org_id: UUID, period: str
) -> PersonalReconciliationMonth:
    existing = await _get_month(session, org_id, period)
    if existing is not None:
        return existing
    month = PersonalReconciliationMonth(
        organization_id=org_id,
        period=period,
        status="draft",
    )
    session.add(month)
    await session.flush()
    return month


async def _recompute_month_totals(
    session: AsyncSession, month: PersonalReconciliationMonth
) -> None:
    """Rebuild cached aggregates on a month record from its live transactions."""
    result = await session.execute(
        select(PersonalTransaction).where(
            PersonalTransaction.reconciliation_month_id == month.id
        )
    )
    txns = list(result.scalars().all())

    business_income = 0.0
    business_expenses = 0.0
    vehicle_expenses = 0.0
    td_count = 0
    amex_count = 0
    flagged = 0

    for t in txns:
        if t.source == "TD":
            td_count += 1
        elif t.source == "AMEX":
            amex_count += 1

        if t.bucket in ("ambiguous", "income_pending"):
            flagged += 1

        if t.bucket == "business":
            if t.incoming:
                business_income += abs(t.amount)
            else:
                business_expenses += t.amount
        elif t.bucket == "vehicle":
            vehicle_expenses += t.amount

    month.td_line_count = td_count
    month.amex_line_count = amex_count
    month.business_income = round(business_income, 2)
    month.business_expenses = round(business_expenses, 2)
    month.vehicle_expenses = round(vehicle_expenses, 2)
    month.flagged_line_count = flagged
    month.gst_collected_informational = (
        round(business_income / 1.05 * 0.05, 2) if business_income > 0 else 0.0
    )
    month.gst_paid_informational = (
        round(business_expenses / 1.05 * 0.05, 2) if business_expenses > 0 else 0.0
    )
    month.updated_at = utcnow()


def _to_month_read(m: PersonalReconciliationMonth) -> ReconciliationMonthRead:
    return ReconciliationMonthRead(
        id=m.id,
        period=m.period,
        status=m.status,
        td_line_count=m.td_line_count,
        amex_line_count=m.amex_line_count,
        business_income=m.business_income,
        business_expenses=m.business_expenses,
        vehicle_expenses=m.vehicle_expenses,
        gst_collected_informational=m.gst_collected_informational,
        gst_paid_informational=m.gst_paid_informational,
        flagged_line_count=m.flagged_line_count,
        locked_at=m.locked_at,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _to_txn_read(t: PersonalTransaction) -> TransactionRead:
    return TransactionRead(
        id=t.id,
        reconciliation_month_id=t.reconciliation_month_id,
        statement_file_id=t.statement_file_id,
        source=t.source,
        txn_date=t.txn_date,
        description=t.description,
        amount=t.amount,
        incoming=t.incoming,
        bucket=t.bucket,
        t2125_line=t.t2125_line,
        category=t.category,
        needs_receipt=t.needs_receipt,
        receipt_filed=t.receipt_filed,
        user_note=t.user_note,
        classified_by=t.classified_by,
        classified_at=t.classified_at,
        original_row_hash=t.original_row_hash,
    )


def _to_rule_read(r: PersonalVendorRule) -> VendorRuleRead:
    return VendorRuleRead(
        id=r.id,
        pattern=r.pattern,
        bucket=r.bucket,
        t2125_line=r.t2125_line,
        category=r.category,
        needs_receipt=r.needs_receipt,
        note=r.note,
        applies_to_source=r.applies_to_source,
        source_month=r.source_month,
        active=r.active,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def _to_statement_read(s: PersonalStatementFile) -> StatementFileRead:
    return StatementFileRead(
        id=s.id,
        reconciliation_month_id=s.reconciliation_month_id,
        period=s.period,
        source=s.source,
        original_filename=s.original_filename,
        content_type=s.content_type,
        sha256=s.sha256,
        byte_size=s.byte_size,
        local_path=s.local_path,
        retention_until=s.retention_until,
        uploaded_at=s.uploaded_at,
    )


# ===========================================================================
# Months
# ===========================================================================


@router.get("/months", response_model=list[ReconciliationMonthRead])
async def list_months(
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[ReconciliationMonthRead]:
    result = await session.execute(
        select(PersonalReconciliationMonth)
        .where(PersonalReconciliationMonth.organization_id == org_ctx.organization.id)
        .order_by(PersonalReconciliationMonth.period.desc())  # type: ignore[attr-defined]
    )
    return [_to_month_read(m) for m in result.scalars().all()]


@router.get("/months/{period}", response_model=ReconciliationMonthRead)
async def get_month(
    period: str,
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> ReconciliationMonthRead:
    _validate_period(period)
    month = await _get_month(session, org_ctx.organization.id, period)
    if month is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return _to_month_read(month)


@router.post(
    "/months",
    response_model=ReconciliationMonthRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_org_role("operator"))],
)
async def create_month(
    payload: ReconciliationMonthCreate,
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> ReconciliationMonthRead:
    _validate_period(payload.period)
    month = await _get_or_create_month(session, org_ctx.organization.id, payload.period)
    await session.commit()
    return _to_month_read(month)


@router.post(
    "/months/{period}/lock",
    response_model=ReconciliationMonthRead,
    dependencies=[Depends(require_org_role("operator"))],
)
async def lock_month(
    period: str,
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> ReconciliationMonthRead:
    _validate_period(period)
    month = await _get_month(session, org_ctx.organization.id, period)
    if month is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if month.status == "locked":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Month already locked.",
        )

    await _recompute_month_totals(session, month)
    if month.flagged_line_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot lock: {month.flagged_line_count} flagged line(s) "
                "(ambiguous or income_pending) must be resolved first."
            ),
        )

    month.status = "locked"
    month.locked_at = utcnow()
    if org_ctx.member.user_id:
        month.locked_by_user_id = org_ctx.member.user_id
    await session.commit()
    return _to_month_read(month)


# ===========================================================================
# Statement upload + import
# ===========================================================================


@router.post(
    "/months/{period}/statements",
    response_model=StatementImportResult,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_org_role("operator"))],
)
async def upload_statement(
    period: str,
    source: str = Form(...),
    file: UploadFile = File(...),
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> StatementImportResult:
    """Upload a TD CSV or AMEX XLS, encrypt at rest, classify, import rows.

    Idempotent on the row-hash level: re-uploading a superset statement
    inserts only the new rows. The file itself is de-duped by SHA-256 of
    the raw bytes — identical re-upload returns 409.
    """
    _validate_period(period)
    if source not in STATEMENT_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid source {source!r}. Expected one of {STATEMENT_SOURCES}.",
        )

    month = await _get_or_create_month(session, org_ctx.organization.id, period)
    if month.status == "locked":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot import into a locked month.",
        )

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file."
        )

    file_sha = hashlib.sha256(raw_bytes).hexdigest()

    # Reject exact-duplicate file uploads at the org level
    dup = (
        await session.execute(
            select(PersonalStatementFile).where(
                PersonalStatementFile.organization_id == org_ctx.organization.id,
                PersonalStatementFile.sha256 == file_sha,
            )
        )
    ).scalars().first()
    if dup is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This exact statement file has already been uploaded.",
        )

    # Parse before touching disk — a parse failure shouldn't leave a rogue file
    try:
        if source == "TD":
            parsed: list[ParsedTransaction] = parse_td_csv(raw_bytes, period=period)
        else:
            parsed = parse_amex_xls(raw_bytes, period=period)
    except Exception as exc:
        logger.warning(
            "personal_bookkeeping.parse_failed source=%s period=%s err=%s",
            source, period, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse {source} statement: {exc}",
        ) from exc

    # Encrypt and persist to disk
    root = _statements_root()
    org_dir = root / str(org_ctx.organization.id)
    org_dir.mkdir(parents=True, exist_ok=True)
    disk_path = org_dir / f"{file_sha}.enc"
    disk_path.write_bytes(encrypt_bytes(raw_bytes))

    statement = PersonalStatementFile(
        organization_id=org_ctx.organization.id,
        reconciliation_month_id=month.id,
        period=period,
        source=source,
        original_filename=file.filename or f"{source.lower()}-{period}",
        content_type=file.content_type or "application/octet-stream",
        sha256=file_sha,
        byte_size=len(raw_bytes),
        file_path=str(disk_path),
        retention_until=_retention_date_for(period),
        uploaded_by_user_id=org_ctx.member.user_id,
    )
    session.add(statement)
    await session.flush()

    # Preload existing row-hashes for this org to de-dup
    existing_hashes = set(
        (
            await session.execute(
                select(PersonalTransaction.original_row_hash).where(
                    PersonalTransaction.organization_id == org_ctx.organization.id,
                )
            )
        ).scalars().all()
    )

    inserted = 0
    skipped = 0
    summary: dict[str, int] = {}

    for p in parsed:
        if p.row_hash in existing_hashes:
            skipped += 1
            continue
        cls = await classify(
            description=p.description,
            incoming=p.incoming,
            source=p.source,
            organization_id=org_ctx.organization.id,
            session=session,
        )
        txn = PersonalTransaction(
            organization_id=org_ctx.organization.id,
            reconciliation_month_id=month.id,
            statement_file_id=statement.id,
            source=p.source,
            txn_date=p.txn_date,
            description=p.description,
            amount=p.amount,
            incoming=p.incoming,
            bucket=cls.bucket,
            t2125_line=cls.t2125_line,
            category=cls.category,
            needs_receipt=cls.needs_receipt,
            user_note=cls.note or None,
            classified_by="auto",
            original_row_hash=p.row_hash,
        )
        session.add(txn)
        existing_hashes.add(p.row_hash)
        inserted += 1
        summary[cls.bucket] = summary.get(cls.bucket, 0) + 1

    await session.flush()
    await _recompute_month_totals(session, month)
    await session.commit()

    return StatementImportResult(
        statement_file_id=statement.id,
        inserted_count=inserted,
        skipped_count=skipped,
        classification_summary=summary,
    )


@router.get(
    "/months/{period}/statements",
    response_model=list[StatementFileRead],
)
async def list_statements(
    period: str,
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[StatementFileRead]:
    _validate_period(period)
    result = await session.execute(
        select(PersonalStatementFile)
        .where(
            PersonalStatementFile.organization_id == org_ctx.organization.id,
            PersonalStatementFile.period == period,
        )
        .order_by(PersonalStatementFile.uploaded_at.desc())  # type: ignore[attr-defined]
    )
    return [_to_statement_read(s) for s in result.scalars().all()]


@router.patch(
    "/statements/{statement_id}",
    response_model=StatementFileRead,
    dependencies=[Depends(require_org_role("operator"))],
)
async def update_statement(
    statement_id: UUID,
    payload: StatementFileUpdate,
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> StatementFileRead:
    result = await session.execute(
        select(PersonalStatementFile).where(
            PersonalStatementFile.id == statement_id,
            PersonalStatementFile.organization_id == org_ctx.organization.id,
        )
    )
    statement = result.scalars().first()
    if statement is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # Only local_path is mutable — file bytes are authoritative
    if payload.local_path is not None:
        statement.local_path = payload.local_path or None

    await session.commit()
    return _to_statement_read(statement)


# ===========================================================================
# Transactions
# ===========================================================================


@router.get(
    "/months/{period}/transactions",
    response_model=list[TransactionRead],
)
async def list_transactions(
    period: str,
    bucket: str | None = None,
    source: str | None = None,
    needs_receipt: bool | None = None,
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[TransactionRead]:
    _validate_period(period)
    month = await _get_month(session, org_ctx.organization.id, period)
    if month is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    query = select(PersonalTransaction).where(
        PersonalTransaction.organization_id == org_ctx.organization.id,
        PersonalTransaction.reconciliation_month_id == month.id,
    )
    if bucket is not None:
        if bucket not in BUCKET_VALUES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid bucket {bucket!r}.",
            )
        query = query.where(PersonalTransaction.bucket == bucket)
    if source is not None:
        if source not in STATEMENT_SOURCES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid source {source!r}.",
            )
        query = query.where(PersonalTransaction.source == source)
    if needs_receipt is not None:
        query = query.where(PersonalTransaction.needs_receipt == needs_receipt)

    query = query.order_by(PersonalTransaction.txn_date.desc())  # type: ignore[attr-defined]
    result = await session.execute(query)
    return [_to_txn_read(t) for t in result.scalars().all()]


@router.patch(
    "/transactions/{txn_id}",
    response_model=TransactionRead,
    dependencies=[Depends(require_org_role("operator"))],
)
async def update_transaction(
    txn_id: UUID,
    payload: TransactionUpdate,
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> TransactionRead:
    result = await session.execute(
        select(PersonalTransaction).where(
            PersonalTransaction.id == txn_id,
            PersonalTransaction.organization_id == org_ctx.organization.id,
        )
    )
    txn = result.scalars().first()
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    month = await session.get(
        PersonalReconciliationMonth, txn.reconciliation_month_id
    )
    if month is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if month.status == "locked":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot edit transactions in a locked month.",
        )

    if payload.bucket is not None:
        if payload.bucket not in BUCKET_VALUES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid bucket {payload.bucket!r}.",
            )
        txn.bucket = payload.bucket
    if payload.t2125_line is not None:
        txn.t2125_line = payload.t2125_line or None
    if payload.category is not None:
        txn.category = payload.category or None
    if payload.needs_receipt is not None:
        txn.needs_receipt = payload.needs_receipt
    if payload.receipt_filed is not None:
        txn.receipt_filed = payload.receipt_filed
    if payload.user_note is not None:
        txn.user_note = payload.user_note or None

    txn.classified_by = "user"
    txn.classified_at = utcnow()
    txn.updated_at = utcnow()

    await session.flush()
    await _recompute_month_totals(session, month)
    await session.commit()

    return _to_txn_read(txn)


@router.post(
    "/transactions/{txn_id}/promote-to-rule",
    response_model=VendorRuleRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_org_role("operator"))],
)
async def promote_to_rule(
    txn_id: UUID,
    payload: PromoteToRuleRequest,
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> VendorRuleRead:
    """Create a vendor rule from a classified transaction.

    Does NOT re-classify existing transactions — that's a separate explicit
    user action (avoids surprise bulk mutations).
    """
    result = await session.execute(
        select(PersonalTransaction).where(
            PersonalTransaction.id == txn_id,
            PersonalTransaction.organization_id == org_ctx.organization.id,
        )
    )
    txn = result.scalars().first()
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    month = await session.get(
        PersonalReconciliationMonth, txn.reconciliation_month_id
    )
    source_month = month.period if month is not None else "manual"

    pattern = payload.pattern or re.escape(txn.description.strip().upper())
    # Sanity-check regex compiles
    try:
        re.compile(pattern)
    except re.error as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid regex pattern: {exc}",
        ) from exc

    applies_to_source: str | None = None
    if payload.applies_to_source is not None:
        if payload.applies_to_source not in STATEMENT_SOURCES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid applies_to_source {payload.applies_to_source!r}.",
            )
        applies_to_source = payload.applies_to_source

    rule = PersonalVendorRule(
        organization_id=org_ctx.organization.id,
        pattern=pattern,
        bucket=txn.bucket,
        t2125_line=txn.t2125_line,
        category=txn.category,
        needs_receipt=txn.needs_receipt,
        note=txn.user_note,
        applies_to_source=applies_to_source,
        source_month=source_month,
        active=True,
    )
    session.add(rule)
    await session.commit()
    return _to_rule_read(rule)


# ===========================================================================
# Vendor rules
# ===========================================================================


@router.get("/vendor-rules", response_model=list[VendorRuleRead])
async def list_vendor_rules(
    active: bool | None = None,
    source_month: str | None = None,
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> list[VendorRuleRead]:
    query = select(PersonalVendorRule).where(
        PersonalVendorRule.organization_id == org_ctx.organization.id,
    )
    if active is not None:
        query = query.where(PersonalVendorRule.active == active)
    if source_month is not None:
        query = query.where(PersonalVendorRule.source_month == source_month)
    query = query.order_by(PersonalVendorRule.created_at.desc())  # type: ignore[attr-defined]
    result = await session.execute(query)
    return [_to_rule_read(r) for r in result.scalars().all()]


@router.post(
    "/vendor-rules",
    response_model=VendorRuleRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_org_role("operator"))],
)
async def create_vendor_rule(
    payload: VendorRuleCreate,
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> VendorRuleRead:
    if payload.bucket not in BUCKET_VALUES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid bucket {payload.bucket!r}.",
        )
    if payload.applies_to_source is not None and payload.applies_to_source not in STATEMENT_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid applies_to_source {payload.applies_to_source!r}.",
        )
    try:
        re.compile(payload.pattern)
    except re.error as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid regex pattern: {exc}",
        ) from exc

    rule = PersonalVendorRule(
        organization_id=org_ctx.organization.id,
        pattern=payload.pattern,
        bucket=payload.bucket,
        t2125_line=payload.t2125_line,
        category=payload.category,
        needs_receipt=payload.needs_receipt,
        note=payload.note,
        applies_to_source=payload.applies_to_source,
        source_month="manual",
        active=True,
    )
    session.add(rule)
    await session.commit()
    return _to_rule_read(rule)


@router.patch(
    "/vendor-rules/{rule_id}",
    response_model=VendorRuleRead,
    dependencies=[Depends(require_org_role("operator"))],
)
async def update_vendor_rule(
    rule_id: UUID,
    payload: VendorRuleUpdate,
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
    session: AsyncSession = SESSION_DEP,
) -> VendorRuleRead:
    result = await session.execute(
        select(PersonalVendorRule).where(
            PersonalVendorRule.id == rule_id,
            PersonalVendorRule.organization_id == org_ctx.organization.id,
        )
    )
    rule = result.scalars().first()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if payload.pattern is not None:
        try:
            re.compile(payload.pattern)
        except re.error as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid regex pattern: {exc}",
            ) from exc
        rule.pattern = payload.pattern
    if payload.bucket is not None:
        if payload.bucket not in BUCKET_VALUES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid bucket {payload.bucket!r}.",
            )
        rule.bucket = payload.bucket
    if payload.t2125_line is not None:
        rule.t2125_line = payload.t2125_line or None
    if payload.category is not None:
        rule.category = payload.category or None
    if payload.needs_receipt is not None:
        rule.needs_receipt = payload.needs_receipt
    if payload.note is not None:
        rule.note = payload.note or None
    if payload.applies_to_source is not None:
        if payload.applies_to_source not in STATEMENT_SOURCES and payload.applies_to_source != "":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid applies_to_source {payload.applies_to_source!r}.",
            )
        rule.applies_to_source = payload.applies_to_source or None
    if payload.active is not None:
        rule.active = payload.active

    rule.updated_at = utcnow()
    await session.commit()
    return _to_rule_read(rule)
