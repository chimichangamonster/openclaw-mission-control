"""Statement parsers for TD chequing CSV and AMEX Cobalt XLS.

Ported from .claude/bookkeeping-draft/reconcile_month.py. Identical parsing
logic — deterministic, not LLM-backed. Same behavior tested against the
Q1 2026 reference data.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ParsedTransaction:
    """One raw line from a bank statement, pre-classification."""

    txn_date: date
    description: str
    amount: float  # Signed: positive = debit/charge, negative = credit/refund
    incoming: bool  # True for TD credit-column entries and AMEX negative amounts
    source: str  # "TD" | "AMEX"
    row_hash: str  # SHA-256 of normalized fields, for idempotent re-imports


_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _hash_row(source: str, iso_date: str, description: str, amount: float) -> str:
    raw = f"{source}|{iso_date}|{description.strip()}|{amount:.2f}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_td_csv(file_bytes: bytes, period: str | None = None) -> list[ParsedTransaction]:
    """Parse a TD EasyWeb Account Activity CSV.

    Expected columns (no header):
        date (YYYY-MM-DD), description, debit, credit, balance

    Args:
        file_bytes: raw CSV bytes.
        period: optional "YYYY-MM" filter. If provided, only transactions
            matching that period are returned.

    Returns:
        List of ParsedTransaction, in file order.
    """
    out: list[ParsedTransaction] = []
    text = file_bytes.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if not row or len(row) < 5:
            continue
        date_str, desc, debit, credit, _balance = row[0], row[1], row[2], row[3], row[4]
        date_str = date_str.strip().strip('"')
        desc = desc.strip().strip('"')
        debit = debit.strip().strip('"')
        credit = credit.strip().strip('"')

        if period is not None and not date_str.startswith(period):
            continue

        try:
            y, m, d = date_str.split("-")
            txn_date = date(int(y), int(m), int(d))
        except (ValueError, AttributeError):
            continue

        if credit:
            try:
                amount = -float(credit.replace(",", ""))
            except ValueError:
                continue
            incoming = True
        elif debit:
            try:
                amount = float(debit.replace(",", ""))
            except ValueError:
                continue
            incoming = False
        else:
            continue

        out.append(
            ParsedTransaction(
                txn_date=txn_date,
                description=desc,
                amount=amount,
                incoming=incoming,
                source="TD",
                row_hash=_hash_row("TD", date_str, desc, amount),
            )
        )
    return out


def parse_amex_xls(
    file_bytes: bytes, period: str | None = None
) -> list[ParsedTransaction]:
    """Parse an AMEX Cobalt transaction-details XLS (BIFF/.xls, not .xlsx).

    Expected layout (AMEX Canada export):
        row 11: header with Date / Description / Amount / ... columns
        row 12+: transaction rows
        Dates like "30 Mar. 2026"; amounts like "$1,234.56" or "-$600.00"

    Args:
        file_bytes: raw .xls bytes.
        period: optional "YYYY-MM" filter.
    """
    import xlrd  # Local import — only needed during parse, not at startup

    out: list[ParsedTransaction] = []
    book = xlrd.open_workbook(file_contents=file_bytes)
    sheet = book.sheet_by_index(0)

    for r in range(12, sheet.nrows):
        date_cell = sheet.cell_value(r, 0)
        amount_cell = sheet.cell_value(r, 3)
        desc_cell = sheet.cell_value(r, 2)

        if not date_cell or amount_cell == "":
            continue

        m = re.match(r"(\d{1,2}) (\w+)\. (\d{4})", str(date_cell))
        if not m:
            continue
        day, mon_name, year = m.groups()
        mon_num = _MONTHS.get(mon_name)
        if mon_num is None:
            continue

        iso_date = f"{year}-{mon_num:02d}-{int(day):02d}"
        if period is not None and not iso_date.startswith(period):
            continue

        try:
            txn_date = date(int(year), mon_num, int(day))
        except ValueError:
            continue

        amt_str = str(amount_cell).replace("$", "").replace(",", "").strip()
        try:
            amount = float(amt_str)
        except ValueError:
            continue

        # AMEX: negative amounts are payments/refunds incoming to Henz's benefit
        incoming = amount < 0
        description = str(desc_cell).strip()

        out.append(
            ParsedTransaction(
                txn_date=txn_date,
                description=description,
                amount=amount,
                incoming=incoming,
                source="AMEX",
                row_hash=_hash_row("AMEX", iso_date, description, amount),
            )
        )
    out.sort(key=lambda t: t.txn_date)
    return out
