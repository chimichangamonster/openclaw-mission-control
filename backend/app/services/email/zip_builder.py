"""Pure helpers for bulk-downloading email attachments as a single zip.

Extracted from `app.api.email.download_all_email_attachments` so the zip
construction can be unit-tested without spinning up an HTTP harness or
mocking provider HTTP calls.
"""

from __future__ import annotations

import io
import os
import zipfile


def build_attachments_zip(items: list[tuple[str, bytes]]) -> bytes:
    """Build a zip archive from (filename, content) pairs.

    Filename collisions disambiguate as `name.ext`, `name (2).ext`,
    `name (3).ext`. Files without an extension get the suffix appended to the
    end (`README`, `README (2)`). Dotfiles like `.env` are treated as
    extensionless. Empty/None filenames fall back to `attachment` and follow
    the same dedup rule.

    Raises ValueError on empty input — caller is expected to 404 first when
    the message has no attachments.
    """
    if not items:
        raise ValueError("Need at least one attachment to build a zip")

    used: set[str] = set()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for filename, content in items:
            unique_name = _disambiguate(filename or "attachment", used)
            used.add(unique_name)
            zf.writestr(unique_name, content)
    return buffer.getvalue()


def _disambiguate(name: str, used: set[str]) -> str:
    """Return a name not in `used`, appending ` (N)` before the extension.

    Treats dotfiles (`.env`, `.gitignore`) as extensionless — appending after
    the whole name rather than corrupting the leading dot.
    """
    if name not in used:
        return name

    base, ext = _split_ext(name)
    counter = 2
    while True:
        candidate = f"{base} ({counter}){ext}"
        if candidate not in used:
            return candidate
        counter += 1


def _split_ext(name: str) -> tuple[str, str]:
    """Like os.path.splitext but treats dotfiles as having no extension."""
    if name.startswith(".") and name.count(".") == 1:
        # `.env` / `.gitignore` — the leading dot is the name, not a separator
        return name, ""
    base, ext = os.path.splitext(name)
    return base, ext


def build_zip_filename(message_id: str) -> str:
    """Build the Content-Disposition filename for the bulk-download zip.

    Uses the first 8 chars of the message UUID. Stable, no special-char
    escaping needed, no information leak.
    """
    prefix = message_id[:8] if message_id else "unknown"
    return f"email-attachments-{prefix}.zip"
