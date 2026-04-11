"""Google Calendar API client — list calendars, CRUD events."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

BASE_URL = "https://www.googleapis.com/calendar/v3"


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def list_calendars(token: str) -> list[dict[str, Any]]:
    """List all calendars accessible to the authenticated user."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BASE_URL}/users/me/calendarList",
            headers=_headers(token),
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
    return [
        {
            "id": cal["id"],
            "summary": cal.get("summary", ""),
            "description": cal.get("description", ""),
            "primary": cal.get("primary", False),
            "time_zone": cal.get("timeZone", ""),
            "background_color": cal.get("backgroundColor", ""),
        }
        for cal in items
    ]


async def list_events(
    token: str,
    calendar_id: str = "primary",
    *,
    time_min: datetime | None = None,
    time_max: datetime | None = None,
    max_results: int = 50,
    q: str | None = None,
) -> list[dict[str, Any]]:
    """List events from a calendar, optionally filtered by time range or query."""
    params: dict[str, Any] = {
        "maxResults": max_results,
        "singleEvents": "true",
        "orderBy": "startTime",
    }
    if time_min:
        params["timeMin"] = (
            time_min.isoformat() + "Z" if not time_min.tzinfo else time_min.isoformat()
        )
    if time_max:
        params["timeMax"] = (
            time_max.isoformat() + "Z" if not time_max.tzinfo else time_max.isoformat()
        )
    if q:
        params["q"] = q

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BASE_URL}/calendars/{calendar_id}/events",
            headers=_headers(token),
            params=params,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])

    return [_event_to_dict(ev) for ev in items]


async def create_event(
    token: str,
    calendar_id: str = "primary",
    *,
    summary: str,
    start: str,
    end: str,
    description: str = "",
    location: str = "",
    attendees: list[str] | None = None,
    time_zone: str = "America/Edmonton",
    reminders: list[dict] | None = None,
) -> dict[str, Any]:
    """Create a calendar event.

    Args:
        start/end: ISO 8601 datetime string (e.g., "2026-03-25T14:00:00") or
                   date string for all-day events (e.g., "2026-03-25").
    """
    body: dict[str, Any] = {
        "summary": summary,
        "description": description,
        "location": location,
    }

    # Detect all-day vs timed events
    if len(start) <= 10:  # date only (YYYY-MM-DD)
        body["start"] = {"date": start}
        body["end"] = {"date": end}
    else:
        body["start"] = {"dateTime": start, "timeZone": time_zone}
        body["end"] = {"dateTime": end, "timeZone": time_zone}

    if attendees:
        body["attendees"] = [{"email": email} for email in attendees]

    if reminders:
        body["reminders"] = {"useDefault": False, "overrides": reminders}

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/calendars/{calendar_id}/events",
            headers=_headers(token),
            json=body,
        )
        resp.raise_for_status()
        return _event_to_dict(resp.json())


async def update_event(
    token: str,
    calendar_id: str,
    event_id: str,
    *,
    summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    description: str | None = None,
    location: str | None = None,
    time_zone: str = "America/Edmonton",
) -> dict[str, Any]:
    """Update an existing calendar event (partial update via PATCH)."""
    body: dict[str, Any] = {}
    if summary is not None:
        body["summary"] = summary
    if description is not None:
        body["description"] = description
    if location is not None:
        body["location"] = location
    if start is not None:
        if len(start) <= 10:
            body["start"] = {"date": start}
        else:
            body["start"] = {"dateTime": start, "timeZone": time_zone}
    if end is not None:
        if len(end) <= 10:
            body["end"] = {"date": end}
        else:
            body["end"] = {"dateTime": end, "timeZone": time_zone}

    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{BASE_URL}/calendars/{calendar_id}/events/{event_id}",
            headers=_headers(token),
            json=body,
        )
        resp.raise_for_status()
        return _event_to_dict(resp.json())


async def delete_event(
    token: str,
    calendar_id: str,
    event_id: str,
) -> None:
    """Delete a calendar event."""
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{BASE_URL}/calendars/{calendar_id}/events/{event_id}",
            headers=_headers(token),
        )
        resp.raise_for_status()


def _event_to_dict(ev: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Google Calendar event to a flat dict."""
    start = ev.get("start", {})
    end = ev.get("end", {})
    return {
        "id": ev.get("id", ""),
        "summary": ev.get("summary", ""),
        "description": ev.get("description", ""),
        "location": ev.get("location", ""),
        "start": start.get("dateTime") or start.get("date", ""),
        "end": end.get("dateTime") or end.get("date", ""),
        "time_zone": start.get("timeZone", ""),
        "status": ev.get("status", ""),
        "html_link": ev.get("htmlLink", ""),
        "attendees": [
            {"email": a.get("email", ""), "response": a.get("responseStatus", "")}
            for a in ev.get("attendees", [])
        ],
        "created": ev.get("created", ""),
        "updated": ev.get("updated", ""),
    }
