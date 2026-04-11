"""Fix files where `from typing import Any` was inserted before `from __future__
import annotations`. Swap so `from __future__` is first (after docstring).
"""

from __future__ import annotations

import sys
from pathlib import Path

BROKEN = [
    "app/api/bookkeeping/clients.py",
    "app/api/bookkeeping/expenses.py",
    "app/api/bookkeeping/exports.py",
    "app/api/bookkeeping/invoices.py",
    "app/api/bookkeeping/jobs.py",
    "app/api/bookkeeping/placements.py",
    "app/api/bookkeeping/reports.py",
    "app/api/bookkeeping/timesheets.py",
    "app/api/bookkeeping/transactions.py",
    "app/api/bookkeeping/workers.py",
    "app/api/cost_tracker.py",
    "app/api/legal.py",
    "app/api/model_registry.py",
    "app/api/org_config.py",
    "app/api/organization_settings.py",
    "app/api/paper_bets.py",
    "app/api/paper_trading.py",
    "app/api/skill_config.py",
    "app/api/watchlist.py",
    "app/models/audit_log.py",
    "app/models/organization_settings.py",
    "app/services/audit.py",
    "app/services/bookkeeping_categorization.py",
    "app/services/budget_monitor.py",
    "app/services/data_retention.py",
    "app/services/document_intake.py",
    "app/services/email/providers/microsoft.py",
    "app/services/email/providers/zoho.py",
    "app/services/industry_templates.py",
    "app/api/document_intake.py",
    "app/api/industry_templates.py",
]


def fix(path: Path) -> bool:
    if not path.exists():
        return False
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)

    typing_idx: int | None = None
    future_idx: int | None = None
    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if typing_idx is None and stripped.startswith("from typing import Any"):
            typing_idx = i
        elif future_idx is None and stripped.startswith("from __future__ import annotations"):
            future_idx = i
        if typing_idx is not None and future_idx is not None:
            break

    if typing_idx is None or future_idx is None:
        return False
    if typing_idx > future_idx:
        return False  # already in correct order

    # Remove typing line, insert it after the future line
    typing_line = lines.pop(typing_idx)
    future_idx -= 1  # shift because we removed a line before it
    # Insert typing line AFTER the future line (+ blank line after future)
    insert_at = future_idx + 1
    # If the line after future is blank, keep it there then insert typing
    if insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1
    lines.insert(insert_at, typing_line)
    # Ensure blank line separation
    if insert_at + 1 < len(lines) and lines[insert_at + 1].strip() != "":
        lines.insert(insert_at + 1, "\n")

    path.write_text("".join(lines), encoding="utf-8")
    return True


def main() -> int:
    fixed = 0
    for rel in BROKEN:
        if fix(Path(rel)):
            print(f"  fix {rel}")
            fixed += 1
        else:
            print(f"  skip {rel}", file=sys.stderr)
    print(f"\nTotal files reordered: {fixed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
