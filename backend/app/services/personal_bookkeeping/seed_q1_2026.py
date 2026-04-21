"""Seed Personal org with Q1 2026 reconciliation data.

Reads the three decisions.md files that Henz reviewed in-session on
2026-04-21 and inserts them as locked PersonalReconciliationMonth records
with fully-classified PersonalTransaction rows.

Idempotent: if a month already exists for the Personal org with status
"locked", the seed skips that month. Re-running is safe.

Run manually from the backend root:
    python -m app.services.personal_bookkeeping.seed_q1_2026

Or with a specific DB URL:
    DATABASE_URL=postgresql+asyncpg://... python -m app.services...

Note: does NOT seed PersonalStatementFile rows (no file storage pipeline
yet — that's Session 2). Transactions are linked to month records but
statement_file_id is left null until re-import once the upload flow exists.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.session import async_session_maker
from app.models.organizations import Organization
from app.models.personal_bookkeeping import (
    PersonalReconciliationMonth,
    PersonalTransaction,
)
from app.services.personal_bookkeeping.classifier import classify
from app.services.personal_bookkeeping.parsers import (
    ParsedTransaction,
    parse_amex_xls,
    parse_td_csv,
)

# Sources — the same files Henz uploaded in session on 2026-04-21.
# Paths are Windows-specific because this script runs from the dev machine;
# production seeding (Session 5) will use a different entry point.
TD_CSV_PATH = Path(r"D:\Downloads\accountactivity (3).csv")
AMEX_XLS_PATH = Path(r"D:\Downloads\Summary (1).xls")

# Henz's locked decisions from .claude/bookkeeping-draft/*/decisions.md.
# Key: (period, source, txn_date_iso, description_fragment, amount_abs)
# Value: (bucket, t2125_line, category, note)
#
# description_fragment is matched with "contains" semantics (case-sensitive)
# so we don't need to copy the full merchant string from the statement.
DecisionKey = tuple[str, str, str, str, float]
DecisionValue = tuple[str, str | None, str | None, str]

Q1_DECISIONS: dict[DecisionKey, DecisionValue] = {
    # --- January 2026: all 4 inflows gifts, 3 TD e-transfers personal,
    # Downtown Auto vehicle, Sandman business travel, rest personal.
    ("2026-01", "TD", "2026-01-12", "TD ATM DEP", 1530.0): ("gift", None, None, "Personal gift"),
    ("2026-01", "TD", "2026-01-19", "E-TRANSFER ***ehp", 1400.0): ("gift", None, None, "Personal gift"),
    ("2026-01", "TD", "2026-01-22", "E-TRANSFER ***Cby", 150.0): ("gift", None, None, "Personal gift"),
    ("2026-01", "TD", "2026-01-26", "TD ATM DEP", 1400.0): ("gift", None, None, "Personal gift"),
    ("2026-01", "AMEX", "2026-01-19", "DOWNTOWN AUTO", 497.22): ("vehicle", None, "Maintenance", "Mechanic — Motor Vehicle %"),
    ("2026-01", "AMEX", "2026-01-30", "SANDMAN", 265.68): ("business", "9200", "Travel", "Calgary airport hotel — business trip"),
    # --- February 2026
    ("2026-02", "TD", "2026-02-02", "E-TRANSFER ***5wh", 1620.0): ("business", None, None, "Consulting income"),
    ("2026-02", "TD", "2026-02-09", "E-TRANSFER ***ccQ", 530.0): ("gift", None, None, "Personal gift"),
    ("2026-02", "TD", "2026-02-11", "E-TRANSFER ***aWz", 1325.0): ("gift", None, None, "Personal gift"),
    ("2026-02", "TD", "2026-02-12", "TD ATM DEP    004543", 2045.0): ("business", None, None, "Consulting income"),
    ("2026-02", "TD", "2026-02-12", "TD ATM DEP    004545", 640.0): ("gift", None, None, "Personal gift"),
    ("2026-02", "TD", "2026-02-24", "TD ATM DEP", 1060.0): ("gift", None, None, "Personal gift"),
    ("2026-02", "AMEX", "2026-02-22", "OPENROUTER", 297.79): ("business", "8871", "Mgmt/Admin", "LLM infrastructure"),
    # --- March 2026
    ("2026-03", "TD", "2026-03-02", "E-TRANSFER ***dSj", 1550.0): ("business", None, None, "Consulting income"),
    ("2026-03", "TD", "2026-03-17", "TD ATM DEP    004514", 1620.0): ("business", None, None, "Consulting income"),
    ("2026-03", "TD", "2026-03-17", "TD ATM DEP    004516", 1020.0): ("gift", None, None, "Personal gift"),
    ("2026-03", "TD", "2026-03-26", "TD ATM DEP    006938", 1840.0): ("gift", None, None, "Personal gift"),
    ("2026-03", "TD", "2026-03-26", "TD ATM DEP    006940", 700.0): ("gift", None, None, "Personal gift"),
    ("2026-03", "AMEX", "2026-03-27", "MEMORY EXPRESS", 288.70): ("business", "8871", "Mgmt/Admin", "IT hardware for consulting"),
    # AMEX ambiguous lines Henz decided personal:
    ("2026-03", "AMEX", "2026-03-11", "UPS*", 38.28): ("personal", None, None, "UPS fee on personal shipment"),
}


@dataclass
class SeedResult:
    period: str
    status: str
    transactions_created: int
    skipped: bool


def _apply_decision(
    period: str, parsed: ParsedTransaction
) -> DecisionValue | None:
    """Look up Henz's locked decision for this row, if any."""
    date_iso = parsed.txn_date.isoformat()
    amt_abs = round(abs(parsed.amount), 2)
    for (p, src, d_iso, frag, amt), val in Q1_DECISIONS.items():
        if p != period or src != parsed.source or d_iso != date_iso:
            continue
        if abs(amt - amt_abs) > 0.005:
            continue
        if frag not in parsed.description:
            continue
        return val
    return None


async def _get_personal_org(session: AsyncSession) -> Organization | None:
    result = await session.execute(
        select(Organization).where(Organization.slug == "personal")
    )
    return result.scalars().first()


async def _seed_month(
    session: AsyncSession,
    org_id: UUID,
    period: str,
    parsed_rows: list[ParsedTransaction],
) -> SeedResult:
    existing = (
        await session.execute(
            select(PersonalReconciliationMonth).where(
                PersonalReconciliationMonth.organization_id == org_id,
                PersonalReconciliationMonth.period == period,
            )
        )
    ).scalars().first()

    if existing and existing.status == "locked":
        return SeedResult(period, "locked", 0, skipped=True)

    if existing is None:
        month = PersonalReconciliationMonth(
            organization_id=org_id,
            period=period,
            status="locked",
        )
        session.add(month)
        await session.flush()
    else:
        month = existing

    business_income = 0.0
    business_expenses = 0.0
    vehicle_expenses = 0.0
    td_count = 0
    amex_count = 0

    for parsed in parsed_rows:
        if parsed.source == "TD":
            td_count += 1
        else:
            amex_count += 1

        cls = await classify(
            description=parsed.description,
            incoming=parsed.incoming,
            source=parsed.source,
            organization_id=org_id,
            session=session,
        )

        # Override with Henz's locked decision if one exists
        decision = _apply_decision(period, parsed)
        if decision is not None:
            bucket, t2125_line, category, note = decision
            classified_by = "user"
            user_note = note
        else:
            bucket = cls.bucket
            t2125_line = cls.t2125_line
            category = cls.category
            classified_by = "auto"
            user_note = cls.note if cls.note else None

        # Aggregate cached totals
        if parsed.source == "AMEX" and bucket == "business":
            business_expenses += parsed.amount
        if parsed.source == "AMEX" and bucket == "vehicle":
            vehicle_expenses += parsed.amount
        if parsed.source == "TD" and bucket == "vehicle":
            vehicle_expenses += parsed.amount
        if bucket == "business" and parsed.incoming:
            business_income += abs(parsed.amount)
        # TD-originating business (consulting income deposits) → business_income
        if parsed.source == "TD" and bucket == "business" and parsed.incoming:
            pass  # Already counted above — TD income uses incoming flag

        txn = PersonalTransaction(
            organization_id=org_id,
            reconciliation_month_id=month.id,
            source=parsed.source,
            txn_date=parsed.txn_date,
            description=parsed.description,
            amount=parsed.amount,
            incoming=parsed.incoming,
            bucket=bucket,
            t2125_line=t2125_line,
            category=category,
            needs_receipt=cls.needs_receipt,
            receipt_filed=False,
            user_note=user_note,
            classified_by=classified_by,
            original_row_hash=parsed.row_hash,
        )
        session.add(txn)

    # Finalize month record
    month.td_line_count = td_count
    month.amex_line_count = amex_count
    month.business_income = round(business_income, 2)
    month.business_expenses = round(business_expenses, 2)
    month.vehicle_expenses = round(vehicle_expenses, 2)
    month.flagged_line_count = 0  # All Q1 decisions locked
    month.status = "locked"
    if business_income > 0:
        month.gst_collected_informational = round(business_income / 1.05 * 0.05, 2)
    if business_expenses > 0:
        month.gst_paid_informational = round(business_expenses / 1.05 * 0.05, 2)

    await session.flush()
    total = td_count + amex_count
    return SeedResult(period, "locked", total, skipped=False)


async def seed_q1() -> list[SeedResult]:
    if not TD_CSV_PATH.exists():
        raise FileNotFoundError(f"TD CSV not found: {TD_CSV_PATH}")
    if not AMEX_XLS_PATH.exists():
        raise FileNotFoundError(f"AMEX XLS not found: {AMEX_XLS_PATH}")

    td_bytes = TD_CSV_PATH.read_bytes()
    amex_bytes = AMEX_XLS_PATH.read_bytes()

    results: list[SeedResult] = []

    async with async_session_maker() as session:
        org = await _get_personal_org(session)
        if org is None:
            raise RuntimeError(
                'No organization with slug="personal" found. Create it first.'
            )

        for period in ("2026-01", "2026-02", "2026-03"):
            td_parsed = parse_td_csv(td_bytes, period=period)
            amex_parsed = parse_amex_xls(amex_bytes, period=period)
            combined = td_parsed + amex_parsed
            result = await _seed_month(session, org.id, period, combined)
            results.append(result)

        await session.commit()

    return results


def main() -> int:
    results = asyncio.run(seed_q1())
    for r in results:
        if r.skipped:
            print(f"  {r.period}: already locked, skipped")
        else:
            print(f"  {r.period}: {r.transactions_created} transactions → {r.status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
