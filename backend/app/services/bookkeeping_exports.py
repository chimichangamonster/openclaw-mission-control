"""QuickBooks export and expense summary services for bookkeeping."""

from __future__ import annotations

from datetime import date
from typing import Any

GST_RATE = 0.05  # Alberta: 5% GST, no PST

# Map expense categories to QuickBooks account names
_QB_CATEGORY_MAP = {
    "materials": "Construction Materials",
    "fuel": "Vehicle Fuel",
    "tools": "Tools & Equipment",
    "ppe": "Safety & PPE",
    "food": "Meals & Entertainment",
    "vehicle": "Vehicle Parts & Maintenance",
    "office": "Office Supplies",
    "equipment": "Equipment Rental",
    "parking": "Vehicle Fuel",
}


def _escape_csv(value: str) -> str:
    if "," in value or '"' in value or "\n" in value:
        return f'"{value.replace(chr(34), chr(34) + chr(34))}"'
    return value


def _format_iif_date(d: date | str) -> str:
    """Format date as MM/DD/YYYY for QuickBooks IIF."""
    if isinstance(d, str):
        parts = d.split("-")
        return f"{int(parts[1])}/{int(parts[2])}/{parts[0]}"
    return f"{d.month}/{d.day}/{d.year}"


def _map_category(category: str | None) -> str:
    return _QB_CATEGORY_MAP.get(category or "", "Other Expenses")


def generate_csv(transactions: list[dict[str, Any]]) -> str:
    """Generate QuickBooks Online-compatible CSV (Journal Entry format).

    Args:
        transactions: List of dicts with type, date, amount, gst_amount, description, job_id, category.

    Returns:
        CSV string with headers.
    """
    headers = ["Date", "Transaction Type", "Account", "Amount", "GST Amount", "Description", "Job", "Category"]
    rows = []
    for t in transactions:
        rows.append(",".join([
            str(t.get("date", "")),
            str(t.get("type", "")),
            "Revenue" if t.get("type") == "income" else "Expenses",
            f"{t.get('amount', 0):.2f}",
            f"{t.get('gst_amount', 0):.2f}",
            _escape_csv(str(t.get("description", ""))),
            str(t.get("job_id", "")),
            str(t.get("category", "")),
        ]))
    return "\n".join([",".join(headers)] + rows)


def generate_iif(transactions: list[dict[str, Any]]) -> str:
    """Generate QuickBooks Desktop IIF format (tab-delimited).

    Each transaction is a TRNS/SPL/ENDTRNS block. GST is split into a
    separate SPL line for Input Tax Credits.
    """
    lines = [
        "!TRNS\tTRNSTYPE\tDATE\tACCNT\tAMOUNT\tMEMO",
        "!SPL\tTRNSTYPE\tDATE\tACCNT\tAMOUNT\tMEMO",
        "!ENDTRNS",
    ]

    for t in transactions:
        dt = _format_iif_date(t["date"])
        desc = t.get("description", "")
        amount = t.get("amount", 0)
        gst = t.get("gst_amount", 0)

        if t.get("type") == "expense":
            net = amount - gst
            lines.append(f"TRNS\tCHECK\t{dt}\tChequing\t{-amount:.2f}\t{desc}")
            lines.append(f"SPL\tCHECK\t{dt}\t{_map_category(t.get('category'))}\t{net:.2f}\t{desc}")
            if gst > 0:
                lines.append(f"SPL\tCHECK\t{dt}\tGST Input Tax Credits\t{gst:.2f}\tGST on {desc}")
            lines.append("ENDTRNS")
        else:
            net_income = amount - gst
            lines.append(f"TRNS\tINVOICE\t{dt}\tAccounts Receivable\t{amount:.2f}\t{desc}")
            lines.append(f"SPL\tINVOICE\t{dt}\tRevenue\t{-net_income:.2f}\t{desc}")
            if gst > 0:
                lines.append(f"SPL\tINVOICE\t{dt}\tGST Collected\t{-gst:.2f}\tGST on {desc}")
            lines.append("ENDTRNS")

    return "\n".join(lines)


def generate_expense_summary(expenses: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate expenses by category and job.

    Returns:
        Dict with total, totalGst, byCategory, byJob.
    """
    by_category: dict[str, dict[str, float | int]] = {}
    by_job: dict[str, dict[str, float | int]] = {}
    total = 0.0
    total_gst = 0.0

    for e in expenses:
        amt = e.get("amount", 0)
        gst = e.get("gst_amount", 0)
        total += amt
        total_gst += gst

        cat = e.get("category") or "uncategorized"
        if cat not in by_category:
            by_category[cat] = {"count": 0, "total": 0.0, "gst": 0.0}
        by_category[cat]["count"] += 1  # type: ignore[operator]
        by_category[cat]["total"] += amt
        by_category[cat]["gst"] += gst

        job = str(e.get("job_id") or "unassigned")
        if job not in by_job:
            by_job[job] = {"count": 0, "total": 0.0, "gst": 0.0}
        by_job[job]["count"] += 1  # type: ignore[operator]
        by_job[job]["total"] += amt
        by_job[job]["gst"] += gst

    return {
        "total": round(total, 2),
        "total_gst": round(total_gst, 2),
        "by_category": by_category,
        "by_job": by_job,
    }
