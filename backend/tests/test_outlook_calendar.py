# ruff: noqa: INP001
"""Tests for Outlook Calendar service — event normalization and URL construction."""

from __future__ import annotations

import pytest

from app.services.microsoft.outlook_calendar import (
    GRAPH_URL,
    _event_to_dict,
    _headers,
)


class TestOutlookHeaders:
    def test_headers_format(self):
        h = _headers("test-token")
        assert h["Authorization"] == "Bearer test-token"
        assert h["Content-Type"] == "application/json"


class TestEventToDict:
    def test_timed_event(self):
        raw = {
            "id": "abc123",
            "subject": "Team Meeting",
            "body": {"contentType": "text", "content": "Weekly sync"},
            "location": {"displayName": "Board Room"},
            "start": {"dateTime": "2026-03-25T14:00:00", "timeZone": "America/Edmonton"},
            "end": {"dateTime": "2026-03-25T15:00:00", "timeZone": "America/Edmonton"},
            "isAllDay": False,
            "showAs": "busy",
            "webLink": "https://outlook.office.com/event/abc123",
            "attendees": [
                {
                    "emailAddress": {"address": "samir@wastegurus.ca", "name": "Samir"},
                    "status": {"response": "accepted"},
                    "type": "required",
                }
            ],
            "createdDateTime": "2026-03-24T10:00:00Z",
            "lastModifiedDateTime": "2026-03-24T10:00:00Z",
        }
        result = _event_to_dict(raw)
        assert result["id"] == "abc123"
        assert result["summary"] == "Team Meeting"
        assert result["description"] == "Weekly sync"
        assert result["location"] == "Board Room"
        assert result["start"] == "2026-03-25T14:00:00"
        assert result["end"] == "2026-03-25T15:00:00"
        assert result["time_zone"] == "America/Edmonton"
        assert result["html_link"] == "https://outlook.office.com/event/abc123"
        assert len(result["attendees"]) == 1
        assert result["attendees"][0]["email"] == "samir@wastegurus.ca"
        assert result["attendees"][0]["response"] == "accepted"

    def test_all_day_event(self):
        raw = {
            "id": "def456",
            "subject": "Q1 Deadline",
            "body": None,
            "location": None,
            "start": {"dateTime": "2026-03-31T00:00:00", "timeZone": "America/Edmonton"},
            "end": {"dateTime": "2026-04-01T00:00:00", "timeZone": "America/Edmonton"},
            "isAllDay": True,
            "attendees": [],
            "createdDateTime": "2026-03-24T10:00:00Z",
            "lastModifiedDateTime": "2026-03-24T10:00:00Z",
        }
        result = _event_to_dict(raw)
        assert result["summary"] == "Q1 Deadline"
        # All-day events should be date-only
        assert result["start"] == "2026-03-31"
        assert result["end"] == "2026-04-01"
        assert result["description"] == ""
        assert result["location"] == ""

    def test_minimal_event(self):
        raw = {"id": "min1", "start": {}, "end": {}}
        result = _event_to_dict(raw)
        assert result["id"] == "min1"
        assert result["summary"] == ""
        assert result["start"] == ""
        assert result["end"] == ""
        assert result["attendees"] == []

    def test_missing_body_and_location(self):
        raw = {
            "id": "x",
            "subject": "Quick call",
            "start": {"dateTime": "2026-03-25T09:00:00"},
            "end": {"dateTime": "2026-03-25T09:30:00"},
            "isAllDay": False,
            "attendees": [],
        }
        result = _event_to_dict(raw)
        assert result["description"] == ""
        assert result["location"] == ""


class TestGraphUrls:
    def test_base_url(self):
        assert GRAPH_URL == "https://graph.microsoft.com/v1.0"

    def test_events_endpoint(self):
        assert f"{GRAPH_URL}/me/events" == "https://graph.microsoft.com/v1.0/me/events"

    def test_calendar_view_endpoint(self):
        assert f"{GRAPH_URL}/me/calendarView" == "https://graph.microsoft.com/v1.0/me/calendarView"


class TestEventFormatCompatibility:
    """Verify that Outlook event dicts have the same keys as Google Calendar events."""

    def test_same_keys_as_google(self):
        google_keys = {
            "id", "summary", "description", "location", "start", "end",
            "time_zone", "status", "html_link", "attendees", "created", "updated",
        }
        raw = {
            "id": "test",
            "subject": "Test",
            "body": {"content": "desc"},
            "location": {"displayName": "Here"},
            "start": {"dateTime": "2026-03-25T14:00:00", "timeZone": "MT"},
            "end": {"dateTime": "2026-03-25T15:00:00", "timeZone": "MT"},
            "isAllDay": False,
            "showAs": "busy",
            "webLink": "https://example.com",
            "attendees": [],
            "createdDateTime": "2026-03-24T10:00:00Z",
            "lastModifiedDateTime": "2026-03-24T10:00:00Z",
        }
        result = _event_to_dict(raw)
        assert set(result.keys()) == google_keys
