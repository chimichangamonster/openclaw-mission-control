"""One-shot script: strip mypy-reported unused `# type: ignore` comments.

Reads /tmp/mypy.log, finds all [unused-ignore] lines, and removes the
`# type: ignore[...]` fragment (or bare `# type: ignore`) from each reported
file+line. Leaves the rest of the line intact. Idempotent.

Usage: python scripts/strip_unused_ignores.py
Run from mission-control/backend.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MYPY_LOG = Path("mypy.log.tmp")
BACKEND_ROOT = Path(".")

IGNORE_RE = re.compile(r"\s*#\s*type:\s*ignore(?:\[[^\]]*\])?")


def parse_targets(log: Path) -> dict[Path, set[int]]:
    targets: dict[Path, set[int]] = {}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if "[unused-ignore]" not in line:
            continue
        head = line.split(": error:", 1)[0]
        file_part, _, lineno_part = head.rpartition(":")
        if not file_part or not lineno_part.isdigit():
            continue
        path = Path(file_part.replace("\\", "/"))
        targets.setdefault(path, set()).add(int(lineno_part))
    return targets


def strip_file(path: Path, lines_to_fix: set[int]) -> int:
    if not path.exists():
        print(f"  MISS {path}", file=sys.stderr)
        return 0
    src_lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    fixed = 0
    for lineno in sorted(lines_to_fix):
        idx = lineno - 1
        if idx < 0 or idx >= len(src_lines):
            continue
        original = src_lines[idx]
        new = IGNORE_RE.sub("", original)
        if new != original:
            # preserve trailing newline
            if original.endswith("\n") and not new.endswith("\n"):
                new = new + "\n"
            src_lines[idx] = new
            fixed += 1
    if fixed:
        path.write_text("".join(src_lines), encoding="utf-8")
    return fixed


def main() -> int:
    targets = parse_targets(MYPY_LOG)
    total = 0
    for path, lines in sorted(targets.items()):
        fixed = strip_file(BACKEND_ROOT / path, lines)
        print(f"  {fixed:>3} {path}")
        total += fixed
    print(f"\nTotal lines fixed: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
