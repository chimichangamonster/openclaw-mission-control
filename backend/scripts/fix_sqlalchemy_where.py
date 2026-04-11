"""Surgical suppression of SQLAlchemy false positives.

Two dominant false-positive patterns:
1. `Argument N to "where" of "Select" has incompatible type "bool"` — mypy
   doesn't understand that `Model.col == value` returns a ColumnElement, not
   a plain Python bool. The ORM descriptors override __eq__ but mypy can't
   see it.
2. `Argument 1 to "order_by" of "GenerativeSelect" has incompatible type
   "datetime"` — same class of problem on order_by.

Both are actual false positives: the code runs correctly. Adding
`# type: ignore[arg-type]` to the exact reported line is safe because we're
only suppressing on lines mypy already reports, and only when the error
matches one of these two patterns.
"""

from __future__ import annotations

import re
from pathlib import Path

MYPY_LOG = Path("mypy.log.tmp")
BACKEND_ROOT = Path(".")

WHERE_RE = re.compile(r'to "where" of "(Select|DMLWhereBase)" has incompatible type "bool"')
ORDER_BY_RE = re.compile(r'to "order_by" of "GenerativeSelect"')
OR_AND_RE = re.compile(r'to "(or_|and_)" has incompatible type "bool"')


def parse_targets(log: Path) -> dict[Path, set[int]]:
    targets: dict[Path, set[int]] = {}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if "[arg-type]" not in line:
            continue
        if not (WHERE_RE.search(line) or ORDER_BY_RE.search(line) or OR_AND_RE.search(line)):
            continue
        head = line.split(": error:", 1)[0]
        file_part, _, lineno_part = head.rpartition(":")
        if not file_part or not lineno_part.isdigit():
            continue
        path = Path(file_part.replace("\\", "/"))
        targets.setdefault(path, set()).add(int(lineno_part))
    return targets


def add_ignore(path: Path, lines_to_fix: set[int]) -> int:
    if not path.exists():
        return 0
    src = path.read_text(encoding="utf-8").splitlines(keepends=True)
    fixed = 0
    for lineno in sorted(lines_to_fix):
        idx = lineno - 1
        if idx < 0 or idx >= len(src):
            continue
        line = src[idx]
        # Skip if already has type: ignore
        if "type: ignore" in line:
            continue
        # Preserve trailing newline
        if line.endswith("\n"):
            stripped = line[:-1].rstrip()
            new = f"{stripped}  # type: ignore[arg-type]\n"
        else:
            new = f"{line.rstrip()}  # type: ignore[arg-type]"
        if new != line:
            src[idx] = new
            fixed += 1
    if fixed:
        path.write_text("".join(src), encoding="utf-8")
    return fixed


def main() -> int:
    targets = parse_targets(MYPY_LOG)
    total = 0
    for path, lines in sorted(targets.items()):
        fixed = add_ignore(BACKEND_ROOT / path, lines)
        if fixed:
            print(f"  {fixed:>3} {path}")
        total += fixed
    print(f"\nTotal type: ignore comments added: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
