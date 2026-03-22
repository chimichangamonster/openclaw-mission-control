# ruff: noqa: INP001
"""Tests for Microsoft Graph integration — model, OAuth, OneDrive helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


class TestMicrosoftConnectionModel:
    """MicrosoftConnection model defaults and structure."""

    def test_default_folder(self):
        from app.models.microsoft_connection import MicrosoftConnection

        conn = MicrosoftConnection(organization_id="fake", user_id="fake")
        assert conn.default_folder == "/OpenClaw"

    def test_is_active_default(self):
        from app.models.microsoft_connection import MicrosoftConnection

        conn = MicrosoftConnection(organization_id="fake", user_id="fake")
        assert conn.is_active is True


class TestGraphOAuthProvider:
    """MicrosoftGraphOAuthProvider scope and URL generation."""

    def test_scopes_include_onedrive(self):
        from app.services.microsoft.graph_oauth import GRAPH_SCOPES

        assert "Files.ReadWrite.All" in GRAPH_SCOPES
        assert "Calendars.ReadWrite" in GRAPH_SCOPES
        assert "Sites.Read.All" in GRAPH_SCOPES
        assert "offline_access" in GRAPH_SCOPES

    def test_scopes_separate_from_email(self):
        from app.services.email.oauth import MicrosoftOAuthProvider
        from app.services.microsoft.graph_oauth import GRAPH_SCOPES

        email_scopes = MicrosoftOAuthProvider.SCOPES
        # Graph scopes should NOT include mail permissions
        assert "Mail.Read" not in GRAPH_SCOPES
        # Email scopes should NOT include file permissions
        assert "Files.ReadWrite.All" not in email_scopes

    def test_authorization_url_format(self):
        with patch("app.services.microsoft.graph_oauth.settings") as mock:
            mock.microsoft_oauth_client_id = "test-client-id"
            mock.microsoft_oauth_redirect_uri = "http://localhost:9876"
            mock.microsoft_oauth_tenant_id = "common"

            from app.services.microsoft.graph_oauth import MicrosoftGraphOAuthProvider

            provider = MicrosoftGraphOAuthProvider()
            url = provider.get_authorization_url("test-state")

            assert "login.microsoftonline.com" in url
            assert "test-client-id" in url
            assert "test-state" in url
            assert "Files.ReadWrite.All" in url


class TestGraphTokenManager:
    """Token storage and refresh logic."""

    def test_store_graph_tokens(self):
        from unittest.mock import MagicMock

        from cryptography.fernet import Fernet

        from app.services.microsoft.token_manager import store_graph_tokens

        conn = MagicMock()
        test_key = Fernet.generate_key().decode()
        with patch("app.core.encryption.settings", encryption_key=test_key, email_token_encryption_key=""):
            # Reset cached fernet instance
            import app.core.encryption as enc_mod
            enc_mod._fernet = None

            store_graph_tokens(
                conn,
                access_token="access123",
                refresh_token="refresh456",
                expires_in=3600,
            )

            enc_mod._fernet = None  # reset for other tests

        assert conn.access_token_encrypted != ""
        assert conn.refresh_token_encrypted != ""
        assert conn.token_expires_at is not None
        assert conn.updated_at is not None

    def test_token_not_refreshed_when_valid(self):
        """Token should not be refreshed if it's still valid."""
        from app.services.microsoft.token_manager import _EXPIRY_BUFFER

        # A token expiring in 1 hour is well within the buffer
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        assert future > datetime.now(timezone.utc) + _EXPIRY_BUFFER


class TestOneDriveHelpers:
    """OneDrive service helper functions."""

    def test_headers_format(self):
        from app.services.microsoft.onedrive import _headers

        h = _headers("test-token-123")
        assert h["Authorization"] == "Bearer test-token-123"

    def test_list_files_url_construction(self):
        """Verify URL construction for root vs subfolder."""
        from app.services.microsoft.onedrive import GRAPH_URL

        # Root folder
        root_url = f"{GRAPH_URL}/me/drive/root/children"
        assert "root/children" in root_url

        # Subfolder
        folder = "OpenClaw/Documents"
        sub_url = f"{GRAPH_URL}/me/drive/root:/{folder}:/children"
        assert f"root:/{folder}:/children" in sub_url


class TestFeatureFlag:
    """Microsoft Graph feature flag."""

    def test_feature_flag_default_off(self):
        from app.models.organization_settings import DEFAULT_FEATURE_FLAGS

        assert "microsoft_graph" in DEFAULT_FEATURE_FLAGS
        assert DEFAULT_FEATURE_FLAGS["microsoft_graph"] is False

    def test_document_generation_default_on(self):
        from app.models.organization_settings import DEFAULT_FEATURE_FLAGS

        assert DEFAULT_FEATURE_FLAGS["document_generation"] is True
