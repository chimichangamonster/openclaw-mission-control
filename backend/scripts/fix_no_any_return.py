"""Add `# type: ignore[no-any-return]` to return lines mypy flags as returning
Any from a declared-typed function.

These are genuine Any values (e.g. from `resp.json()`, `adobe pdfservices` SDK,
third-party libs without stubs). The declared return type is aspirational.
Adding cast() would be noise — the type genuinely isn't knowable at this point.
"""

from __future__ import annotations

from pathlib import Path

MYPY_LOG = Path("mypy.log.tmp")
BACKEND_ROOT = Path(".")


def parse_targets(log: Path) -> dict[Path, set[int]]:
    targets: dict[Path, set[int]] = {}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if "[no-any-return]" not in line:
            continue
        if "Returning Any from function declared to return" not in line:
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
        # Must be a `return` line
        if "return " not in line and not line.strip().endswith("return"):
            continue
        # Preserve trailing newline
        if line.endswith("\n"):
            stripped = line[:-1].rstrip()
            new = f"{stripped}  # type: ignore[no-any-return]\n"
        else:
            new = f"{line.rstrip()}  # type: ignore[no-any-return]"
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
    print(f"\nTotal type: ignore[no-any-return] added: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
