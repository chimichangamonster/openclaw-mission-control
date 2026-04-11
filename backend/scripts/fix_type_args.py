"""One-shot: replace bare `list` / `dict` with `list[Any]` / `dict[str, Any]` on
mypy-reported [type-arg] lines.

Safer than a global regex because it targets exact file:line pairs. Looks for
`list` / `dict` that is NOT immediately followed by `[` (already subscripted)
and NOT part of a longer identifier (e.g. `listing`, `dictionary`).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MYPY_LOG = Path("mypy.log.tmp")
BACKEND_ROOT = Path(".")

# Match bare `list` or `dict` as a whole word, not followed by `[`.
LIST_RE = re.compile(r"\blist\b(?!\[)")
DICT_RE = re.compile(r"\bdict\b(?!\[)")
PATTERN_RE = re.compile(r"\bPattern\b(?!\[)")
CALLABLE_RE = re.compile(r"\bCallable\b(?!\[)")


def parse_targets(log: Path) -> dict[Path, set[int]]:
    targets: dict[Path, set[int]] = {}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if "[type-arg]" not in line:
            continue
        head = line.split(": error:", 1)[0]
        file_part, _, lineno_part = head.rpartition(":")
        if not file_part or not lineno_part.isdigit():
            continue
        path = Path(file_part.replace("\\", "/"))
        targets.setdefault(path, set()).add(int(lineno_part))
    return targets


def fix_file(path: Path, lines_to_fix: set[int]) -> int:
    if not path.exists():
        print(f"  MISS {path}", file=sys.stderr)
        return 0
    src = path.read_text(encoding="utf-8").splitlines(keepends=True)
    fixed = 0
    for lineno in sorted(lines_to_fix):
        idx = lineno - 1
        if idx < 0 or idx >= len(src):
            continue
        original = src[idx]
        new = original
        # Only replace the first occurrence per line (mypy reports one per line).
        if LIST_RE.search(new):
            new = LIST_RE.sub("list[Any]", new, count=1)
        elif DICT_RE.search(new):
            new = DICT_RE.sub("dict[str, Any]", new, count=1)
        elif PATTERN_RE.search(new):
            new = PATTERN_RE.sub("Pattern[str]", new, count=1)
        elif CALLABLE_RE.search(new):
            new = CALLABLE_RE.sub("Callable[..., Any]", new, count=1)
        if new != original:
            src[idx] = new
            fixed += 1
    if fixed:
        path.write_text("".join(src), encoding="utf-8")
    return fixed


def main() -> int:
    targets = parse_targets(MYPY_LOG)
    total = 0
    for path, lines in sorted(targets.items()):
        fixed = fix_file(BACKEND_ROOT / path, lines)
        if fixed:
            print(f"  {fixed:>3} {path}")
        total += fixed
    print(f"\nTotal lines fixed: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
