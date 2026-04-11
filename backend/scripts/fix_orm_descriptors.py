"""Surgically suppress SQLAlchemy ORM descriptor false positives.

mypy can't see that `Model.datetime_col.desc()` / `Model.col.in_()` / etc. are
valid ORM operations — it resolves `Model.datetime_col` to `datetime` and
complains that `datetime` has no `.desc` method.

Only suppresses errors where the reported "has no attribute X" is one of the
ORM operator names. Safe because:
1. Narrow to known ORM method names (desc, asc, is_, isnot, in_)
2. Only adds ignore on the exact reported line
3. Only adds [attr-defined] code, not bare suppression
"""

from __future__ import annotations

import re
from pathlib import Path

MYPY_LOG = Path("mypy.log.tmp")
BACKEND_ROOT = Path(".")

ORM_METHODS = {"desc", "asc", "is_", "isnot", "in_"}

ATTR_RE = re.compile(r'has no attribute "([a-z_]+)"')


def parse_targets(log: Path) -> dict[Path, set[int]]:
    targets: dict[Path, set[int]] = {}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if "[attr-defined]" not in line:
            continue
        m = ATTR_RE.search(line)
        if not m or m.group(1) not in ORM_METHODS:
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
        if "type: ignore" in line:
            continue
        if line.endswith("\n"):
            stripped = line[:-1].rstrip()
            new = f"{stripped}  # type: ignore[attr-defined]\n"
        else:
            new = f"{line.rstrip()}  # type: ignore[attr-defined]"
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
    print(f"\nTotal ORM-descriptor type: ignore added: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
