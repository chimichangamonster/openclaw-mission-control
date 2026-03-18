"""Microsoft Graph Mail API client for message fetching and actions."""

from __future__ import annotations

from datetime import datetime

import httpx

from app.core.logging import get_logger
from app.services.email.types import RawAttachment, RawEmailMessage

logger = get_logger(__name__)

GRAPH_URL = "https://graph.microsoft.com/v1.0"


def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


def _parse_graph_date(date_str: str) -> datetime:
    """Parse ISO 8601 datetime from Graph API."""
    return datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)


def _extract_recipients(recipients: list[dict] | None) -> list[dict[str, str]]:
    if not recipients:
        return []
    return [
        {
            "email": r.get("emailAddress", {}).get("address", ""),
            "name": r.get("emailAddress", {}).get("name", ""),
        }
        for r in recipients
    ]


async def fetch_messages(
    access_token: str,
    *,
    folder: str = "inbox",
    limit: int = 50,
    delta_link: str | None = None,
) -> tuple[list[RawEmailMessage], str | None]:
    """Fetch messages from Outlook. Returns (messages, next_delta_link)."""
    if delta_link:
        url = delta_link
    else:
        folder_map = {"inbox": "inbox", "sent": "sentItems", "archive": "archive", "trash": "deletedItems"}
        graph_folder = folder_map.get(folder, folder)
        url = f"{GRAPH_URL}/me/mailFolders/{graph_folder}/messages/delta"

    messages: list[RawEmailMessage] = []
    next_delta: str | None = None

    async with httpx.AsyncClient() as client:
        params: dict[str, str | int] = {"$top": limit}
        if not delta_link:
            params["$select"] = (
                "id,conversationId,subject,from,toRecipients,ccRecipients,"
                "body,receivedDateTime,isRead,parentFolderId,hasAttachments"
            )

        resp = await client.get(url, headers=_headers(access_token), params=params if not delta_link else {})
        resp.raise_for_status()
        data = resp.json()

    next_delta = data.get("@odata.deltaLink")
    next_link = data.get("@odata.nextLink")
    if not next_delta and next_link:
        next_delta = next_link

    for msg in data.get("value", []):
        from_data = msg.get("from", {}).get("emailAddress", {})
        body = msg.get("body", {})

        messages.append(
            RawEmailMessage(
                provider_message_id=msg.get("id", ""),
                thread_id=msg.get("conversationId"),
                subject=msg.get("subject"),
                sender_email=from_data.get("address", ""),
                sender_name=from_data.get("name"),
                recipients_to=_extract_recipients(msg.get("toRecipients")),
                recipients_cc=_extract_recipients(msg.get("ccRecipients")) or None,
                body_text=body.get("content", "") if body.get("contentType") == "text" else "",
                body_html=body.get("content", "") if body.get("contentType") == "html" else None,
                received_at=_parse_graph_date(msg["receivedDateTime"]) if "receivedDateTime" in msg else datetime.utcnow(),
                is_read=msg.get("isRead", False),
                folder=folder,
                labels=None,
                has_attachments=msg.get("hasAttachments", False),
                attachments=[],
            )
        )
    return messages, next_delta


async def send_message(
    access_token: str,
    *,
    to: str,
    subject: str,
    body: str,
    content_type: str = "Text",
    reply_to_message_id: str | None = None,
) -> dict:
    """Send or reply to an email via Graph API."""
    if reply_to_message_id:
        url = f"{GRAPH_URL}/me/messages/{reply_to_message_id}/reply"
        payload = {"comment": body}
    else:
        url = f"{GRAPH_URL}/me/sendMail"
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": content_type, "content": body},
                "toRecipients": [{"emailAddress": {"address": to}}],
            }
        }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=_headers(access_token), json=payload)
        resp.raise_for_status()
        if resp.status_code == 202 or not resp.content:
            return {"ok": True}
        return resp.json()


async def move_message(
    access_token: str,
    message_id: str,
    *,
    target_folder: str,
) -> None:
    """Move a message to a different folder."""
    folder_map = {"archive": "archive", "trash": "deletedItems", "inbox": "inbox"}
    url = f"{GRAPH_URL}/me/messages/{message_id}/move"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers=_headers(access_token),
            json={"destinationId": folder_map.get(target_folder, target_folder)},
        )
        resp.raise_for_status()


async def mark_read(
    access_token: str,
    message_id: str,
    *,
    read: bool = True,
) -> None:
    """Mark a message as read or unread."""
    url = f"{GRAPH_URL}/me/messages/{message_id}"
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            url,
            headers=_headers(access_token),
            json={"isRead": read},
        )
        resp.raise_for_status()
