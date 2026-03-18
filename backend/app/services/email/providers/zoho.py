"""Zoho Mail API client for message fetching and actions."""

from __future__ import annotations

from datetime import datetime

import httpx

from app.core.logging import get_logger
from app.services.email.types import RawAttachment, RawEmailMessage

logger = get_logger(__name__)

BASE_URL = "https://mail.zoho.com/api/accounts"


def _parse_zoho_date(ms_str: str | int) -> datetime:
    """Zoho returns dates as epoch milliseconds."""
    return datetime.utcfromtimestamp(int(ms_str) / 1000)


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Zoho-oauthtoken {access_token}"}


async def fetch_messages(
    access_token: str,
    account_id: str,
    *,
    folder: str = "inbox",
    limit: int = 50,
    from_message_id: str | None = None,
) -> list[RawEmailMessage]:
    """Fetch messages from a Zoho Mail folder."""
    folder_map = {"inbox": "INBOX", "sent": "SENT", "archive": "ARCHIVE", "trash": "TRASH"}
    zoho_folder = folder_map.get(folder, folder.upper())

    url = f"{BASE_URL}/{account_id}/messages/view"
    params: dict[str, str | int] = {
        "folderId": zoho_folder,
        "limit": limit,
        "sortBy": "date",
        "sortOrder": "desc",
    }
    if from_message_id:
        params["fromMessageId"] = from_message_id

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=_headers(access_token), params=params)
        resp.raise_for_status()
        data = resp.json()

    messages = []
    for msg in data.get("data", []):
        recipients_to = [
            {"email": r.get("address", ""), "name": r.get("name", "")}
            for r in msg.get("toAddress", [])
        ]
        recipients_cc = [
            {"email": r.get("address", ""), "name": r.get("name", "")}
            for r in msg.get("ccAddress", [])
        ] or None

        attachments = [
            RawAttachment(
                filename=a.get("attachmentName", ""),
                content_type=a.get("contentType"),
                size_bytes=a.get("attachmentSize"),
                provider_attachment_id=a.get("attachmentId"),
            )
            for a in msg.get("attachments", [])
        ]

        messages.append(
            RawEmailMessage(
                provider_message_id=str(msg.get("messageId", "")),
                thread_id=str(msg.get("threadId", "")),
                subject=msg.get("subject"),
                sender_email=msg.get("sender", ""),
                sender_name=msg.get("fromAddress", ""),
                recipients_to=recipients_to,
                recipients_cc=recipients_cc,
                body_text=msg.get("summary", ""),
                body_html=msg.get("content"),
                received_at=_parse_zoho_date(msg.get("receivedTime", 0)),
                is_read=msg.get("status2", "0") == "1",
                folder=folder,
                labels=msg.get("labels"),
                has_attachments=bool(msg.get("hasAttachment")),
                attachments=attachments,
            )
        )
    return messages


async def send_message(
    access_token: str,
    account_id: str,
    *,
    to: str,
    subject: str,
    body: str,
    in_reply_to: str | None = None,
) -> dict:
    """Send or reply to an email via Zoho Mail API."""
    url = f"{BASE_URL}/{account_id}/messages"
    payload: dict = {
        "toAddress": to,
        "subject": subject,
        "content": body,
        "mailFormat": "plaintext",
    }
    if in_reply_to:
        payload["inReplyTo"] = in_reply_to

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers=_headers(access_token),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


async def move_message(
    access_token: str,
    account_id: str,
    message_id: str,
    *,
    target_folder: str,
) -> None:
    """Move a message to a different folder."""
    url = f"{BASE_URL}/{account_id}/messages/{message_id}/move"
    folder_map = {"inbox": "INBOX", "archive": "ARCHIVE", "trash": "TRASH"}
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            url,
            headers=_headers(access_token),
            json={"destfolderId": folder_map.get(target_folder, target_folder.upper())},
        )
        resp.raise_for_status()


async def mark_read(
    access_token: str,
    account_id: str,
    message_id: str,
    *,
    read: bool = True,
) -> None:
    """Mark a message as read or unread."""
    url = f"{BASE_URL}/{account_id}/messages/{message_id}"
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            url,
            headers=_headers(access_token),
            json={"status": "read" if read else "unread"},
        )
        resp.raise_for_status()
