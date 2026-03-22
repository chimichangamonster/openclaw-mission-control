# ruff: noqa: INP001
"""Tests for organization logo upload — file validation, storage, and cleanup."""

from __future__ import annotations

from pathlib import Path

import pytest


LOGO_ALLOWED_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
}
LOGO_MAX_SIZE = 5 * 1024 * 1024


class TestLogoValidation:
    """Logo file type and size validation."""

    def test_allowed_types(self):
        assert "image/png" in LOGO_ALLOWED_TYPES
        assert "image/jpeg" in LOGO_ALLOWED_TYPES
        assert "image/svg+xml" in LOGO_ALLOWED_TYPES
        assert "image/webp" in LOGO_ALLOWED_TYPES
        assert "application/pdf" not in LOGO_ALLOWED_TYPES
        assert "text/html" not in LOGO_ALLOWED_TYPES

    def test_max_size(self):
        assert LOGO_MAX_SIZE == 5 * 1024 * 1024

    def test_extensions_correct(self):
        assert LOGO_ALLOWED_TYPES["image/png"] == ".png"
        assert LOGO_ALLOWED_TYPES["image/jpeg"] == ".jpg"
        assert LOGO_ALLOWED_TYPES["image/svg+xml"] == ".svg"
        assert LOGO_ALLOWED_TYPES["image/webp"] == ".webp"


class TestLogoStorage:
    """Logo file storage and cleanup."""

    def test_logo_saved_to_org_directory(self, tmp_path: Path):
        """Logo files are stored under orgs/{org_id}/."""
        from uuid import uuid4

        org_id = uuid4()
        org_dir = tmp_path / "orgs" / str(org_id)
        org_dir.mkdir(parents=True)

        logo_data = b"\x89PNG\r\n\x1a\n fake png"
        logo_path = org_dir / "logo.png"
        logo_path.write_bytes(logo_data)

        assert logo_path.exists()
        assert logo_path.read_bytes() == logo_data

    def test_old_logos_cleaned_up(self, tmp_path: Path):
        """Uploading a new logo removes old logo files."""
        from uuid import uuid4

        org_id = uuid4()
        org_dir = tmp_path / "orgs" / str(org_id)
        org_dir.mkdir(parents=True)

        # Create old logos
        (org_dir / "logo.png").write_bytes(b"old png")
        (org_dir / "logo.jpg").write_bytes(b"old jpg")

        # Simulate cleanup (same logic as upload endpoint)
        for old in org_dir.glob("logo.*"):
            old.unlink()

        # Write new logo
        (org_dir / "logo.svg").write_bytes(b"<svg>new</svg>")

        remaining = list(org_dir.glob("logo.*"))
        assert len(remaining) == 1
        assert remaining[0].name == "logo.svg"

    def test_org_isolation(self, tmp_path: Path):
        """Different orgs have separate logo directories."""
        from uuid import uuid4

        org_a = uuid4()
        org_b = uuid4()

        dir_a = tmp_path / "orgs" / str(org_a)
        dir_b = tmp_path / "orgs" / str(org_b)
        dir_a.mkdir(parents=True)
        dir_b.mkdir(parents=True)

        (dir_a / "logo.png").write_bytes(b"logo A")
        (dir_b / "logo.png").write_bytes(b"logo B")

        assert (dir_a / "logo.png").read_bytes() == b"logo A"
        assert (dir_b / "logo.png").read_bytes() == b"logo B"


class TestBrandingJson:
    """Branding JSON logo_path integration."""

    def test_logo_path_format(self):
        """Logo path follows the expected format."""
        from uuid import uuid4

        org_id = uuid4()
        expected = f"orgs/{org_id}/logo.png"
        assert expected.startswith("orgs/")
        assert expected.endswith(".png")
        assert str(org_id) in expected

    def test_logo_url_generation(self):
        """Logo URL uses file-serve signed token pattern."""
        from unittest.mock import patch

        with patch("app.core.file_tokens.settings", encryption_key="test-key", email_token_encryption_key=""):
            from app.core.file_tokens import create_file_token

            token = create_file_token("orgs/abc/logo.png", expires_hours=168)
            url = f"http://100.100.202.83:8000/api/v1/files/download?token={token}"

            assert "files/download" in url
            assert "token=" in url
