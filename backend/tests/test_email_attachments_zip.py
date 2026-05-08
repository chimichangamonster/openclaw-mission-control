# ruff: noqa: INP001
"""Tests for bulk attachment download (item 131b).

Locks the pure-helper that builds an in-memory zip from a list of (filename,
content_bytes) pairs:
- All attachments included, inline ones filtered upstream by the caller
- Filename collisions disambiguated as `name.ext`, `name (2).ext`, ...
- Empty input raises a clear error (caller should 404 before reaching here)
- Unicode filenames preserved
- Missing extension handled (collision adds suffix before nothing)

Source-level assertion that the bulk-download endpoint exists in
`app/api/email.py`.
"""

from __future__ import annotations

import inspect
import io
import zipfile

import pytest


def test_build_attachments_zip_empty_raises():
    """Empty input is a programming error — caller must 404 first."""
    from app.services.email.zip_builder import build_attachments_zip

    with pytest.raises(ValueError, match="at least one attachment"):
        build_attachments_zip([])


def test_build_attachments_zip_single_file():
    """Single file zips correctly with original filename."""
    from app.services.email.zip_builder import build_attachments_zip

    payload = [("invoice.pdf", b"%PDF-1.4 fake content")]
    blob = build_attachments_zip(payload)

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = zf.namelist()
        assert names == ["invoice.pdf"]
        assert zf.read("invoice.pdf") == b"%PDF-1.4 fake content"


def test_build_attachments_zip_disambiguates_collisions():
    """Two files with same name get `(2)`, `(3)` suffixes before extension."""
    from app.services.email.zip_builder import build_attachments_zip

    payload = [
        ("scan.pdf", b"first"),
        ("scan.pdf", b"second"),
        ("scan.pdf", b"third"),
    ]
    blob = build_attachments_zip(payload)

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = zf.namelist()
        assert names == ["scan.pdf", "scan (2).pdf", "scan (3).pdf"]
        assert zf.read("scan.pdf") == b"first"
        assert zf.read("scan (2).pdf") == b"second"
        assert zf.read("scan (3).pdf") == b"third"


def test_build_attachments_zip_disambiguates_no_extension():
    """Files without an extension get `(2)` appended to the end."""
    from app.services.email.zip_builder import build_attachments_zip

    payload = [
        ("README", b"first"),
        ("README", b"second"),
    ]
    blob = build_attachments_zip(payload)

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        assert zf.namelist() == ["README", "README (2)"]


def test_build_attachments_zip_disambiguates_dotfiles():
    """Dotfiles like `.env` should not be treated as having an extension."""
    from app.services.email.zip_builder import build_attachments_zip

    payload = [
        (".env", b"first"),
        (".env", b"second"),
    ]
    blob = build_attachments_zip(payload)

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        # ".env" is treated as a name with no extension — disambiguates by
        # appending ` (2)`, not by inserting before the dot.
        assert zf.namelist() == [".env", ".env (2)"]


def test_build_attachments_zip_preserves_unicode():
    """Unicode filenames must round-trip through the zip."""
    from app.services.email.zip_builder import build_attachments_zip

    payload = [("发票.pdf", b"chinese-invoice"), ("résumé.docx", b"french-cv")]
    blob = build_attachments_zip(payload)

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        assert "发票.pdf" in zf.namelist()
        assert "résumé.docx" in zf.namelist()


def test_build_attachments_zip_handles_missing_filename():
    """Empty/None filename gets a fallback name; multiple fall through dedup."""
    from app.services.email.zip_builder import build_attachments_zip

    payload = [("", b"a"), ("", b"b")]
    blob = build_attachments_zip(payload)

    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = zf.namelist()
        assert len(names) == 2
        # Both should be unique even though source filename was empty.
        assert names[0] != names[1]


def test_build_zip_filename_uses_message_id_prefix():
    """The downloaded zip's filename derives from the message UUID prefix."""
    from app.services.email.zip_builder import build_zip_filename

    # UUID first-8 chars
    name = build_zip_filename("7c1a3b9d-4f2e-4a8b-9c1d-3e5f7a9b0c2d")
    assert name == "email-attachments-7c1a3b9d.zip"


def test_build_zip_filename_short_id_safe():
    """Filename builder doesn't crash on short / unusual ids."""
    from app.services.email.zip_builder import build_zip_filename

    name = build_zip_filename("abc")
    assert name == "email-attachments-abc.zip"


def test_bulk_download_endpoint_exists_in_email_api():
    """Source-level assertion: the bulk-download route is registered."""
    from app.api import email as email_api

    src = inspect.getsource(email_api)
    # Endpoint pattern + handler name
    assert "/attachments/download-all" in src, (
        "Bulk attachment download endpoint missing from app/api/email.py — "
        "expected route ending in /attachments/download-all"
    )
    assert "download_all_email_attachments" in src or "download_attachments_zip" in src, (
        "Expected handler `download_all_email_attachments` or "
        "`download_attachments_zip` not found in email.py"
    )
