"""Microsoft Outlook Calendar operations via Graph API — list, create, update, delete events."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

GRAPH_URL = "https://graph.microsoft.com/v1.0"


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def list_calendars(token: str) -> list[dict[str, Any]]:
    """List all calendars accessible to the authenticated user."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GRAPH_URL}/me/calendars",
            headers=_headers(token),
        )
        resp.raise_for_status()
        items = resp.json().get("value", [])
    return [
        {
            "id": cal["id"],
            "name": cal.get("name", ""),
            "color": cal.get("color", ""),
            "is_default": cal.get("isDefaultCalendar", False),
            "can_edit": cal.get("canEdit", True),
        }
        for cal in items
    ]


async def list_events(
    token: str,
    *,
    time_min: datetime | None = None,
    time_max: datetime | None = None,
    max_results: int = 50,
    q: str | None = None,
) -> list[dict[str, Any]]:
    """List events from the user's default calendar."""
    # Use calendarView for time-range queries (auto-expands recurring events)
    if time_min and time_max:
        url = f"{GRAPH_URL}/me/calendarView"
        params: dict[str, Any] = {
            "startDateTime": (
                time_min.isoformat() + "Z" if not time_min.tzinfo else time_min.isoformat()
            ),
            "endDateTime": (
                time_max.isoformat() + "Z" if not time_max.tzinfo else time_max.isoformat()
            ),
            "$top": max_results,
            "$orderby": "start/dateTime",
            "$select": "id,subject,body,location,start,end,isAllDay,attendees,webLink,createdDateTime,lastModifiedDateTime,showAs",
        }
        if q:
            params["$filter"] = f"contains(subject,'{q}')"
    else:
        url = f"{GRAPH_URL}/me/events"
        params = {
            "$top": max_results,
            "$orderby": "start/dateTime",
            "$select": "id,subject,body,location,start,end,isAllDay,attendees,webLink,createdDateTime,lastModifiedDateTime,showAs",
        }
        if q:
            params["$filter"] = f"contains(subject,'{q}')"

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=_headers(token), params=params)
        resp.raise_for_status()
        items = resp.json().get("value", [])

    return [_event_to_dict(ev) for ev in items]


async def create_event(
    token: str,
    *,
    summary: str,
    start: str,
    end: str,
    description: str = "",
    location: str = "",
    attendees: list[str] | None = None,
    time_zone: str = "America/Edmonton",
    is_all_day: bool = False,
) -> dict[str, Any]:
    """Create a calendar event in Outlook.

    Args:
        start/end: ISO 8601 datetime (e.g., "2026-03-25T14:00:00") or
                   date for all-day events (e.g., "2026-03-25").
    """
    # Auto-detect all-day from date format
    if len(start) <= 10:
        is_all_day = True

    body: dict[str, Any] = {
        "subject": summary,
        "body": {"contentType": "text", "content": description},
        "isAllDay": is_all_day,
    }

    if is_all_day:
        body["start"] = {"dateTime": f"{start}T00:00:00", "timeZone": time_zone}
        body["end"] = {"dateTime": f"{end}T00:00:00", "timeZone": time_zone}
    else:
        body["start"] = {"dateTime": start, "timeZone": time_zone}
        body["end"] = {"dateTime": end, "timeZone": time_zone}

    if location:
        body["location"] = {"displayName": location}

    if attendees:
        body["attendees"] = [
            {
                "emailAddress": {"address": email},
                "type": "required",
            }
            for email in attendees
        ]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GRAPH_URL}/me/events",
            headers=_headers(token),
            json=body,
        )
        resp.raise_for_status()
        return _event_to_dict(resp.json())


async def update_event(
    token: str,
    event_id: str,
    *,
    summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    description: str | None = None,
    location: str | None = None,
    time_zone: str = "America/Edmonton",
) -> dict[str, Any]:
    """Update an existing Outlook calendar event (partial update via PATCH)."""
    body: dict[str, Any] = {}
    if summary is not None:
        body["subject"] = summary
    if description is not None:
        body["body"] = {"contentType": "text", "content": description}
    if location is not None:
        body["location"] = {"displayName": location}
    if start is not None:
        is_all_day = len(start) <= 10
        if is_all_day:
            body["start"] = {"dateTime": f"{start}T00:00:00", "timeZone": time_zone}
            body["isAllDay"] = True
        else:
            body["start"] = {"dateTime": start, "timeZone": time_zone}
    if end is not None:
        is_all_day = len(end) <= 10
        if is_all_day:
            body["end"] = {"dateTime": f"{end}T00:00:00", "timeZone": time_zone}
        else:
            body["end"] = {"dateTime": end, "timeZone": time_zone}

    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{GRAPH_URL}/me/events/{event_id}",
            headers=_headers(token),
            json=body,
        )
        resp.raise_for_status()
        return _event_to_dict(resp.json())


async def delete_event(token: str, event_id: str) -> None:
    """Delete a calendar event from Outlook."""
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{GRAPH_URL}/me/events/{event_id}",
            headers=_headers(token),
        )
        resp.raise_for_status()


def _event_to_dict(ev: dict[str, Any]) -> dict[str, Any]:
    """Normalize an Outlook calendar event to the same shape as Google events."""
    start = ev.get("start", {})
    end = ev.get("end", {})
    is_all_day = ev.get("isAllDay", False)

    # Normalize start/end to ISO strings
    start_str = start.get("dateTime", "")
    end_str = end.get("dateTime", "")

    # For all-day events, return date-only format
    if is_all_day and start_str:
        start_str = start_str[:10]
        end_str = end_str[:10]

    return {
        "id": ev.get("id", ""),
        "summary": ev.get("subject", ""),
        "description": (ev.get("body") or {}).get("content", ""),
        "location": (ev.get("location") or {}).get("displayName", ""),
        "start": start_str,
        "end": end_str,
        "time_zone": start.get("timeZone", ""),
        "status": ev.get("showAs", ""),
        "html_link": ev.get("webLink", ""),
        "attendees": [
            {
                "email": (a.get("emailAddress") or {}).get("address", ""),
                "response": (a.get("status") or {}).get("response", ""),
            }
            for a in ev.get("attendees", [])
        ],
        "created": ev.get("createdDateTime", ""),
        "updated": ev.get("lastModifiedDateTime", ""),
    }
