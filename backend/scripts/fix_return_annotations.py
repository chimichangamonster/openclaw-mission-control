"""Add `-> Any` to functions mypy flags as missing a return type annotation.

Parses mypy log for [no-untyped-def] "missing a return type annotation" entries,
locates the function signature (which may span multiple lines), and inserts
` -> Any` before the terminating `:`.

Only targets "missing a return type annotation" — not "missing a type annotation
for one or more arguments" (those need per-arg reasoning).
"""

from __future__ import annotations

import sys
from pathlib import Path

MYPY_LOG = Path("mypy.log.tmp")
BACKEND_ROOT = Path(".")


def parse_targets(log: Path) -> dict[Path, set[int]]:
    targets: dict[Path, set[int]] = {}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if "[no-untyped-def]" not in line:
            continue
        if "missing a return type annotation" not in line:
            continue
        head = line.split(": error:", 1)[0]
        file_part, _, lineno_part = head.rpartition(":")
        if not file_part or not lineno_part.isdigit():
            continue
        path = Path(file_part.replace("\\", "/"))
        targets.setdefault(path, set()).add(int(lineno_part))
    return targets


def find_signature_end(lines: list[str], def_line_idx: int) -> int | None:
    """Walk forward from `def` line until we find the line ending in `):` or `) ->`.

    Returns the index of the line containing the closing paren + colon.
    """
    depth = 0
    found_def = False
    for i in range(def_line_idx, min(def_line_idx + 30, len(lines))):
        line = lines[i]
        if not found_def:
            if "def " in line:
                found_def = True
        if not found_def:
            continue
        for ch in line:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
        if depth == 0 and found_def:
            # Found the closing paren on this line
            return i
    return None


def annotate_file(path: Path, lines_to_fix: set[int]) -> int:
    if not path.exists():
        return 0
    src = path.read_text(encoding="utf-8").splitlines(keepends=True)
    fixed = 0
    # Process in reverse so earlier line numbers stay stable
    for lineno in sorted(lines_to_fix, reverse=True):
        idx = lineno - 1
        if idx < 0 or idx >= len(src):
            continue
        # Some def lines span multiple lines; find the signature-end line
        end_idx = find_signature_end(src, idx)
        if end_idx is None:
            continue
        line = src[end_idx]
        # Skip if already has `->`
        if " -> " in line:
            continue
        # Look for `):` and insert ` -> Any` before it
        # Handle both `):` and `) :` (rare)
        if "):" in line:
            new = line.replace("):", ") -> Any:", 1)
        else:
            continue
        if new != line:
            src[end_idx] = new
            fixed += 1
    if fixed:
        path.write_text("".join(src), encoding="utf-8")
    return fixed


def main() -> int:
    only_file = sys.argv[1] if len(sys.argv) > 1 else None
    targets = parse_targets(MYPY_LOG)
    total = 0
    for path, lines in sorted(targets.items()):
        if only_file and only_file not in str(path):
            continue
        fixed = annotate_file(BACKEND_ROOT / path, lines)
        if fixed:
            print(f"  {fixed:>3} {path}")
        total += fixed
    print(f"\nTotal return annotations added: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
