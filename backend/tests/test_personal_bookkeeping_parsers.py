# ruff: noqa: INP001
"""Tests for TD CSV and AMEX XLS statement parsers.

Uses synthetic fixtures (tiny byte blobs) that mirror the real TD EasyWeb
export and AMEX Cobalt XLS format. Real statement files live outside the
repo on Henz's dev machine and are not committed.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO

import xlwt

from app.services.personal_bookkeeping.parsers import parse_amex_xls, parse_td_csv

# --- TD CSV ---

TD_CSV_SAMPLE = (
    b'"2026-01-02","PETRO-CANADA 89","33.58",,"821.41"\n'
    b'"2026-01-12","TD ATM DEP    007702",,"1530","1675.31"\n'
    b'"2026-01-12","AMEX CARDS   X9K7W7","800",,"838.87"\n'
    b'"2026-02-02","SOBEYS LIQUOR","41.74",,"350.14"\n'
)


def test_parse_td_csv_basic() -> None:
    rows = parse_td_csv(TD_CSV_SAMPLE)
    assert len(rows) == 4
    assert all(r.source == "TD" for r in rows)


def test_parse_td_csv_debit_positive_credit_negative() -> None:
    rows = parse_td_csv(TD_CSV_SAMPLE)
    petro, deposit, cc_payment, sobeys = rows
    # Debit lines — positive amount, not incoming
    assert petro.amount == 33.58
    assert petro.incoming is False
    assert cc_payment.amount == 800.0
    assert cc_payment.incoming is False
    # Credit line — negative amount, incoming
    assert deposit.amount == -1530.0
    assert deposit.incoming is True


def test_parse_td_csv_period_filter() -> None:
    rows_jan = parse_td_csv(TD_CSV_SAMPLE, period="2026-01")
    assert len(rows_jan) == 3
    assert all(r.txn_date.month == 1 for r in rows_jan)

    rows_feb = parse_td_csv(TD_CSV_SAMPLE, period="2026-02")
    assert len(rows_feb) == 1
    assert rows_feb[0].description == "SOBEYS LIQUOR"


def test_parse_td_csv_row_hash_stable() -> None:
    rows_a = parse_td_csv(TD_CSV_SAMPLE)
    rows_b = parse_td_csv(TD_CSV_SAMPLE)
    for a, b in zip(rows_a, rows_b, strict=True):
        assert a.row_hash == b.row_hash
    # All hashes unique for different rows
    assert len({r.row_hash for r in rows_a}) == len(rows_a)


def test_parse_td_csv_date_parsed() -> None:
    rows = parse_td_csv(TD_CSV_SAMPLE)
    assert rows[0].txn_date == date(2026, 1, 2)
    assert rows[3].txn_date == date(2026, 2, 2)


def test_parse_td_csv_skips_malformed_lines() -> None:
    bad = (
        b'"2026-01-02","GOOD LINE","33.58",,"821.41"\n'
        b'"not-a-date","bad row","10",,"0"\n'
        b',,,\n'
    )
    rows = parse_td_csv(bad)
    assert len(rows) == 1
    assert rows[0].description == "GOOD LINE"


# --- AMEX XLS ---


def _build_amex_xls(transactions: list[tuple[str, str, str]]) -> bytes:
    """Build a minimal AMEX-style .xls in memory.

    transactions: list of (date_str, description, amount_str) tuples.
    Mirrors the layout parse_amex_xls expects (header at row 11, data row 12+).
    """
    wb = xlwt.Workbook()
    sh = wb.add_sheet("Summary")
    # Header padding — AMEX export has 11 rows of header/summary
    for r in range(11):
        sh.write(r, 0, "")
    headers = ["Date", "Date Processed", "Description", "Amount", "Foreign Spend Amount",
               "Commission", "Exchange Rate", "Merchant", "Merchant Address", "Additional"]
    for c, h in enumerate(headers):
        sh.write(11, c, h)
    for i, (d, desc, amt) in enumerate(transactions, start=12):
        sh.write(i, 0, d)
        sh.write(i, 1, d)
        sh.write(i, 2, desc)
        sh.write(i, 3, amt)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_amex_xls_basic() -> None:
    data = _build_amex_xls([
        ("5 Jan. 2026", "PAYPAL *GODADDY.COM 4805058855", "$23.09"),
        ("20 Jan. 2026", "GOOGLE *GOOGLE ONE G.CO/HELPPAY#", "$28.34"),
        ("30 Jan. 2026", "PAYMENT RECEIVED - THANK YOU", "-$600.00"),
    ])
    rows = parse_amex_xls(data)
    assert len(rows) == 3
    assert all(r.source == "AMEX" for r in rows)


def test_parse_amex_xls_amount_sign_and_incoming() -> None:
    data = _build_amex_xls([
        ("5 Jan. 2026", "GODADDY", "$23.09"),
        ("30 Jan. 2026", "PAYMENT RECEIVED", "-$600.00"),
    ])
    rows = parse_amex_xls(data)
    godaddy, payment = rows[0], rows[1]
    assert godaddy.amount == 23.09
    assert godaddy.incoming is False
    assert payment.amount == -600.00
    assert payment.incoming is True


def test_parse_amex_xls_period_filter() -> None:
    data = _build_amex_xls([
        ("5 Jan. 2026", "LINE JAN", "$10.00"),
        ("10 Feb. 2026", "LINE FEB", "$20.00"),
        ("15 Mar. 2026", "LINE MAR", "$30.00"),
    ])
    rows_feb = parse_amex_xls(data, period="2026-02")
    assert len(rows_feb) == 1
    assert rows_feb[0].description == "LINE FEB"


def test_parse_amex_xls_sorted_by_date() -> None:
    # Deliberately out of order to prove sort behavior
    data = _build_amex_xls([
        ("30 Jan. 2026", "LATE", "$1.00"),
        ("2 Jan. 2026", "EARLY", "$2.00"),
        ("15 Jan. 2026", "MIDDLE", "$3.00"),
    ])
    rows = parse_amex_xls(data)
    assert [r.description for r in rows] == ["EARLY", "MIDDLE", "LATE"]


def test_parse_amex_xls_comma_thousands() -> None:
    data = _build_amex_xls([
        ("5 Jan. 2026", "BIG CHARGE", "$1,234.56"),
    ])
    rows = parse_amex_xls(data)
    assert rows[0].amount == 1234.56


def test_parse_amex_xls_skips_malformed() -> None:
    data = _build_amex_xls([
        ("5 Jan. 2026", "GOOD", "$10.00"),
        ("bad date", "BAD DATE", "$20.00"),
        ("10 Jan. 2026", "BAD AMOUNT", "not a number"),
    ])
    rows = parse_amex_xls(data)
    assert len(rows) == 1
    assert rows[0].description == "GOOD"
