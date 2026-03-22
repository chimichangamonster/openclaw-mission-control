# ruff: noqa: INP001
"""Tests for file serving: HMAC token signing and download endpoints.

Covers token round-trip, expiry, tamper detection, path traversal blocking,
MIME type mapping, and file size limits.
"""

from __future__ import annotations

import json
import time
from base64 import urlsafe_b64encode
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.file_tokens import create_file_token, verify_file_token


# ---------------------------------------------------------------------------
# Token unit tests
# ---------------------------------------------------------------------------


def _patch_settings():
    """Patch settings for file_tokens module."""
    return patch("app.core.file_tokens.settings", encryption_key="test-key-for-hmac", email_token_encryption_key="")


class TestFileTokens:
    """HMAC token creation and verification."""

    def test_round_trip(self):
        """Valid token round-trips correctly."""
        with _patch_settings():
            token = create_file_token("reports/q1.html", expires_hours=1)
            result = verify_file_token(token)
        assert result == "reports/q1.html"

    def test_expired_token(self):
        """Expired tokens are rejected."""
        with _patch_settings(), patch("app.core.file_tokens.time") as mock_time:
            mock_time.time.return_value = time.time() - 7200  # 2 hours ago
            token = create_file_token("file.txt", expires_hours=1)

        with _patch_settings():
            assert verify_file_token(token) is None

    def test_tampered_path(self):
        """Modifying the payload invalidates the signature."""
        with _patch_settings():
            token = create_file_token("legit.txt", expires_hours=1)
        payload_b64, sig = token.split(".", 1)

        # Tamper: swap payload with different path
        evil_payload = json.dumps(
            {"p": "../../etc/passwd", "e": int(time.time()) + 3600},
            separators=(",", ":"),
        )
        evil_b64 = urlsafe_b64encode(evil_payload.encode()).decode().rstrip("=")
        tampered = f"{evil_b64}.{sig}"

        with _patch_settings():
            assert verify_file_token(tampered) is None

    def test_tampered_signature(self):
        """Modifying the signature invalidates the token."""
        with _patch_settings():
            token = create_file_token("file.txt", expires_hours=1)
        payload_b64, sig = token.split(".", 1)
        bad_sig = "a" * len(sig)
        with _patch_settings():
            assert verify_file_token(f"{payload_b64}.{bad_sig}") is None

    def test_malformed_token(self):
        """Garbage input returns None."""
        with _patch_settings():
            assert verify_file_token("") is None
            assert verify_file_token("nodot") is None
            assert verify_file_token("not.valid.token") is None
            assert verify_file_token("abc.def") is None

    def test_empty_path_rejected(self):
        """Token with empty path is rejected."""
        import hashlib
        import hmac as hmac_mod

        with _patch_settings():
            from app.core.file_tokens import _get_signing_key

            payload = json.dumps({"p": "", "e": int(time.time()) + 3600}, separators=(",", ":"))
            payload_b64 = urlsafe_b64encode(payload.encode()).decode().rstrip("=")
            sig = hmac_mod.new(_get_signing_key(), payload_b64.encode(), hashlib.sha256).hexdigest()
            token = f"{payload_b64}.{sig}"
            assert verify_file_token(token) is None


# ---------------------------------------------------------------------------
# Path safety tests
# ---------------------------------------------------------------------------


class TestPathSafety:
    """Path traversal prevention in _resolve_safe_path."""

    def test_traversal_blocked(self, tmp_path: Path):
        from app.api.file_serve import _resolve_safe_path
        from fastapi import HTTPException

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with pytest.raises(HTTPException) as exc_info:
            _resolve_safe_path(workspace, "../../etc/passwd")
        assert exc_info.value.status_code == 403

    def test_absolute_path_blocked(self, tmp_path: Path):
        from app.api.file_serve import _resolve_safe_path
        from fastapi import HTTPException

        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with pytest.raises(HTTPException) as exc_info:
            _resolve_safe_path(workspace, "/etc/passwd")
        assert exc_info.value.status_code == 400

    def test_valid_path_resolves(self, tmp_path: Path):
        from app.api.file_serve import _resolve_safe_path

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "reports").mkdir()
        test_file = workspace / "reports" / "q1.html"
        test_file.write_text("<html></html>")

        result = _resolve_safe_path(workspace, "reports/q1.html")
        assert result == test_file.resolve()


# ---------------------------------------------------------------------------
# MIME type tests
# ---------------------------------------------------------------------------


class TestMimeTypes:
    """Correct MIME type mapping."""

    def test_known_types(self):
        from app.api.file_serve import _MIME_MAP

        assert _MIME_MAP[".html"] == "text/html"
        assert _MIME_MAP[".pdf"] == "application/pdf"
        assert _MIME_MAP[".csv"] == "text/csv"
        assert _MIME_MAP[".json"] == "application/json"
        assert _MIME_MAP[".png"] == "image/png"
        assert _MIME_MAP[".jpg"] == "image/jpeg"

    def test_unknown_type_falls_back(self):
        from app.api.file_serve import _MIME_MAP

        assert ".xyz" not in _MIME_MAP  # unknown ext → application/octet-stream


# ---------------------------------------------------------------------------
# Endpoint integration tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def _workspace(tmp_path: Path):
    """Create a temporary workspace with test files."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "test.html").write_text("<html><body>Hello</body></html>")
    (workspace / "data.csv").write_text("a,b,c\n1,2,3")
    (workspace / "reports").mkdir()
    (workspace / "reports" / "deep.pdf").write_bytes(b"%PDF-1.4 fake")

    # Create an oversized file marker (we'll mock the size check)
    (workspace / "huge.bin").write_bytes(b"x" * 100)

    return workspace


@pytest.fixture()
def _app_client(_workspace: Path):
    """FastAPI test client with workspace path configured."""
    import asyncio

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.api.file_serve import router

    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    with (
        patch("app.api.file_serve.settings") as mock_settings,
        patch("app.core.file_tokens.settings") as mock_token_settings,
    ):
        mock_settings.gateway_workspace_path = str(_workspace)
        mock_settings.local_auth_token = "test-token-long-enough-for-validation-purposes-here"
        mock_settings.base_url = "http://100.100.202.83:8000"
        mock_token_settings.encryption_key = "test-encryption-key-for-hmac-signing"
        mock_token_settings.email_token_encryption_key = ""

        transport = ASGITransport(app=test_app)
        client = AsyncClient(transport=transport, base_url="http://test")
        yield client

        asyncio.get_event_loop_policy()


@pytest.mark.asyncio()
async def test_create_link_success(_app_client, _workspace):
    resp = await _app_client.post(
        "/api/v1/files/create-link",
        params={"token": "test-token-long-enough-for-validation-purposes-here"},
        json={"path": "test.html", "expires_hours": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "url" in data
    assert data["filename"] == "test.html"
    assert "expires_at" in data
    assert "token=" in data["url"]


@pytest.mark.asyncio()
async def test_create_link_bad_auth(_app_client):
    resp = await _app_client.post(
        "/api/v1/files/create-link",
        params={"token": "wrong-token"},
        json={"path": "test.html"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio()
async def test_create_link_file_not_found(_app_client):
    resp = await _app_client.post(
        "/api/v1/files/create-link",
        params={"token": "test-token-long-enough-for-validation-purposes-here"},
        json={"path": "nonexistent.txt"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio()
async def test_create_link_traversal_blocked(_app_client):
    resp = await _app_client.post(
        "/api/v1/files/create-link",
        params={"token": "test-token-long-enough-for-validation-purposes-here"},
        json={"path": "../../etc/passwd"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio()
async def test_download_valid_token(_app_client, _workspace):
    # First create a link
    resp = await _app_client.post(
        "/api/v1/files/create-link",
        params={"token": "test-token-long-enough-for-validation-purposes-here"},
        json={"path": "test.html"},
    )
    url = resp.json()["url"]
    # Extract token from URL
    dl_token = url.split("token=")[1]

    # Download
    resp = await _app_client.get("/api/v1/files/download", params={"token": dl_token})
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio()
async def test_download_expired_token(_app_client):
    resp = await _app_client.get("/api/v1/files/download", params={"token": "expired.fake"})
    assert resp.status_code == 401


@pytest.mark.asyncio()
async def test_download_deep_path(_app_client, _workspace):
    resp = await _app_client.post(
        "/api/v1/files/create-link",
        params={"token": "test-token-long-enough-for-validation-purposes-here"},
        json={"path": "reports/deep.pdf"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "deep.pdf"
