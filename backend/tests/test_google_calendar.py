# ruff: noqa: INP001
"""Tests for Google Calendar integration — model, OAuth, calendar helpers, feature flag."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


class TestGoogleCalendarConnectionModel:
    """GoogleCalendarConnection model defaults and structure."""

    def test_default_calendar_id(self):
        from app.models.google_calendar_connection import GoogleCalendarConnection

        conn = GoogleCalendarConnection(organization_id="fake", user_id="fake")
        assert conn.default_calendar_id == "primary"

    def test_is_active_default(self):
        from app.models.google_calendar_connection import GoogleCalendarConnection

        conn = GoogleCalendarConnection(organization_id="fake", user_id="fake")
        assert conn.is_active is True

    def test_empty_tokens_by_default(self):
        from app.models.google_calendar_connection import GoogleCalendarConnection

        conn = GoogleCalendarConnection(organization_id="fake", user_id="fake")
        assert conn.access_token_encrypted == ""
        assert conn.refresh_token_encrypted == ""
        assert conn.token_expires_at is None


class TestGoogleCalendarOAuthProvider:
    """GoogleCalendarOAuthProvider scope and URL generation."""

    def test_scopes_include_calendar(self):
        from app.services.google.calendar_oauth import GOOGLE_CALENDAR_SCOPES

        assert "https://www.googleapis.com/auth/calendar" in GOOGLE_CALENDAR_SCOPES
        assert "email" in GOOGLE_CALENDAR_SCOPES
        assert "profile" in GOOGLE_CALENDAR_SCOPES

    def test_scopes_do_not_include_drive(self):
        from app.services.google.calendar_oauth import GOOGLE_CALENDAR_SCOPES

        assert "drive" not in GOOGLE_CALENDAR_SCOPES

    def test_authorization_url_format(self):
        with patch("app.services.google.calendar_oauth.settings") as mock:
            mock.google_oauth_client_id = "test-google-client-id"
            mock.google_oauth_redirect_uri = "http://localhost:9876/api/v1/google-calendar/callback"

            from app.services.google.calendar_oauth import GoogleCalendarOAuthProvider

            provider = GoogleCalendarOAuthProvider()
            url = provider.get_authorization_url("test-state-xyz")

            assert "accounts.google.com" in url
            assert "test-google-client-id" in url
            assert "test-state-xyz" in url
            assert "calendar" in url
            assert "access_type=offline" in url
            assert "prompt=consent" in url

    def test_token_url_is_google(self):
        from app.services.google.calendar_oauth import GoogleCalendarOAuthProvider

        provider = GoogleCalendarOAuthProvider()
        assert "googleapis.com" in provider.TOKEN_URL

    def test_user_info_url_is_google(self):
        from app.services.google.calendar_oauth import GoogleCalendarOAuthProvider

        provider = GoogleCalendarOAuthProvider()
        assert "googleapis.com" in provider.USER_INFO_URL


class TestGoogleTokenManager:
    """Token storage and refresh logic."""

    def test_store_google_tokens(self):
        from cryptography.fernet import Fernet

        from app.services.google.token_manager import store_google_tokens

        conn = MagicMock()
        test_key = Fernet.generate_key().decode()
        with patch(
            "app.core.encryption.settings", encryption_key=test_key, email_token_encryption_key=""
        ):
            import app.core.encryption as enc_mod

            enc_mod.reset_cache()

            store_google_tokens(
                conn,
                access_token="google-access-123",
                refresh_token="google-refresh-456",
                expires_in=3600,
            )

            enc_mod.reset_cache()  # reset for other tests

        assert conn.access_token_encrypted != ""
        assert conn.refresh_token_encrypted != ""
        assert conn.token_expires_at is not None
        assert conn.updated_at is not None

    def test_token_expiry_is_in_future(self):
        from cryptography.fernet import Fernet

        from app.services.google.token_manager import store_google_tokens

        conn = MagicMock()
        test_key = Fernet.generate_key().decode()
        with patch(
            "app.core.encryption.settings", encryption_key=test_key, email_token_encryption_key=""
        ):
            import app.core.encryption as enc_mod

            enc_mod.reset_cache()

            store_google_tokens(
                conn,
                access_token="a",
                refresh_token="r",
                expires_in=7200,
            )

            enc_mod.reset_cache()

        # Token should expire roughly 2 hours from now
        now = datetime.now(timezone.utc)
        expires = conn.token_expires_at
        # Remove tzinfo for comparison if needed
        if expires.tzinfo is None:
            delta = expires - now.replace(tzinfo=None)
        else:
            delta = expires - now
        assert timedelta(hours=1, minutes=50) < delta < timedelta(hours=2, minutes=10)

    def test_expiry_buffer_is_5_minutes(self):
        from app.services.google.token_manager import _EXPIRY_BUFFER

        assert _EXPIRY_BUFFER == timedelta(minutes=5)


class TestCalendarHelpers:
    """Google Calendar service helper functions."""

    def test_headers_format(self):
        from app.services.google.calendar import _headers

        h = _headers("test-google-token-123")
        assert h["Authorization"] == "Bearer test-google-token-123"
        assert h["Content-Type"] == "application/json"

    def test_event_to_dict_timed(self):
        from app.services.google.calendar import _event_to_dict

        raw = {
            "id": "ev123",
            "summary": "Team Meeting",
            "description": "Weekly standup",
            "location": "Office",
            "start": {"dateTime": "2026-03-25T09:00:00-06:00", "timeZone": "America/Edmonton"},
            "end": {"dateTime": "2026-03-25T09:30:00-06:00", "timeZone": "America/Edmonton"},
            "status": "confirmed",
            "htmlLink": "https://calendar.google.com/event?eid=ev123",
            "attendees": [
                {"email": "a@test.com", "responseStatus": "accepted"},
                {"email": "b@test.com", "responseStatus": "needsAction"},
            ],
            "created": "2026-03-20T12:00:00.000Z",
            "updated": "2026-03-20T12:00:00.000Z",
        }
        result = _event_to_dict(raw)
        assert result["id"] == "ev123"
        assert result["summary"] == "Team Meeting"
        assert result["location"] == "Office"
        assert result["start"] == "2026-03-25T09:00:00-06:00"
        assert result["time_zone"] == "America/Edmonton"
        assert len(result["attendees"]) == 2
        assert result["attendees"][0]["email"] == "a@test.com"
        assert result["html_link"] == "https://calendar.google.com/event?eid=ev123"

    def test_event_to_dict_all_day(self):
        from app.services.google.calendar import _event_to_dict

        raw = {
            "id": "allday1",
            "summary": "Deadline",
            "start": {"date": "2026-03-31"},
            "end": {"date": "2026-04-01"},
            "status": "confirmed",
        }
        result = _event_to_dict(raw)
        assert result["start"] == "2026-03-31"
        assert result["end"] == "2026-04-01"
        assert result["time_zone"] == ""

    def test_event_to_dict_minimal(self):
        from app.services.google.calendar import _event_to_dict

        raw = {"id": "min1"}
        result = _event_to_dict(raw)
        assert result["id"] == "min1"
        assert result["summary"] == ""
        assert result["attendees"] == []
        assert result["start"] == ""

    def test_base_url(self):
        from app.services.google.calendar import BASE_URL

        assert "googleapis.com/calendar/v3" in BASE_URL


class TestFeatureFlag:
    """Google Calendar feature flag."""

    def test_feature_flag_exists(self):
        from app.models.organization_settings import DEFAULT_FEATURE_FLAGS

        assert "google_calendar" in DEFAULT_FEATURE_FLAGS

    def test_feature_flag_default_off(self):
        from app.models.organization_settings import DEFAULT_FEATURE_FLAGS

        assert DEFAULT_FEATURE_FLAGS["google_calendar"] is False

    def test_microsoft_graph_still_exists(self):
        from app.models.organization_settings import DEFAULT_FEATURE_FLAGS

        assert "microsoft_graph" in DEFAULT_FEATURE_FLAGS
        assert DEFAULT_FEATURE_FLAGS["microsoft_graph"] is False


class TestGoogleTokenResult:
    """GoogleTokenResult dataclass."""

    def test_frozen_dataclass(self):
        from app.services.google.calendar_oauth import GoogleTokenResult

        result = GoogleTokenResult(
            access_token="a",
            refresh_token="r",
            expires_in=3600,
            scopes="calendar",
            provider_account_id="123",
            email_address="test@gmail.com",
            display_name="Test User",
        )
        assert result.access_token == "a"
        assert result.email_address == "test@gmail.com"
        assert result.display_name == "Test User"

        with pytest.raises(AttributeError):
            result.access_token = "changed"  # type: ignore[misc]
