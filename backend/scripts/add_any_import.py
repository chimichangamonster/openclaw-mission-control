"""Add `Any` to `from typing import ...` in files that now reference it but
don't import it. If the file already imports from typing, splice `Any` in;
otherwise add a fresh `from typing import Any` line after the module docstring
or at the top.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MYPY_LOG = Path("mypy.log.tmp")
BACKEND_ROOT = Path(".")

TYPING_IMPORT_RE = re.compile(
    r"^(from typing import )(.+)$",
    re.MULTILINE,
)


def files_needing_any(log: Path) -> set[Path]:
    files: set[Path] = set()
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if "[name-defined]" not in line or '"Any"' not in line:
            continue
        head = line.split(": error:", 1)[0]
        file_part, _, _lineno = head.rpartition(":")
        if file_part:
            files.add(Path(file_part.replace("\\", "/")))
    return files


def splice_any(path: Path) -> bool:
    if not path.exists():
        return False
    src = path.read_text(encoding="utf-8")
    # Already has Any?
    if re.search(r"\bfrom typing import[^\n]*\bAny\b", src):
        return False
    m = TYPING_IMPORT_RE.search(src)
    if m:
        existing = m.group(2).strip()
        # Insert Any into the sorted list (keep it simple: prepend)
        parts = [p.strip() for p in existing.split(",")]
        if "Any" not in parts:
            parts.insert(0, "Any")
            new_line = f"{m.group(1)}{', '.join(parts)}"
            src = src[: m.start()] + new_line + src[m.end():]
            path.write_text(src, encoding="utf-8")
            return True
        return False
    # No existing typing import — add one after the module docstring / from-future line
    lines = src.splitlines(keepends=True)
    insert_at = 0
    # Skip module docstring
    if lines and lines[0].lstrip().startswith(('"""', "'''")):
        quote = lines[0].lstrip()[:3]
        # Single-line docstring
        if lines[0].count(quote) >= 2:
            insert_at = 1
        else:
            for i, ln in enumerate(lines[1:], start=1):
                if quote in ln:
                    insert_at = i + 1
                    break
    # Skip from __future__ imports
    while insert_at < len(lines) and lines[insert_at].startswith("from __future__"):
        insert_at += 1
    # Skip blank lines
    while insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1
    lines.insert(insert_at, "from typing import Any\n\n")
    path.write_text("".join(lines), encoding="utf-8")
    return True


def main() -> int:
    files = files_needing_any(MYPY_LOG)
    fixed = 0
    for rel in sorted(files):
        if splice_any(BACKEND_ROOT / rel):
            print(f"  +Any {rel}")
            fixed += 1
        else:
            print(f"  skip {rel}", file=sys.stderr)
    print(f"\nTotal files updated: {fixed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
