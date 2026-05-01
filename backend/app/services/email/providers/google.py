"""Gmail / Google Workspace API client for message fetching and actions.

Uses the Gmail REST API v1. Incremental sync is keyed on Gmail's ``historyId``
(stored in ``EmailAccount.sync_cursor``); on first sync we list inbox and sent
message IDs, then on subsequent syncs we fetch only changes via
``users.history.list``. Folder concept maps to Gmail labels:

    inbox   -> label INBOX
    sent    -> label SENT
    trash   -> label TRASH
    archive -> message has none of {INBOX, TRASH, SPAM}

Sending uses ``users.messages.send`` with a base64url-encoded RFC 822 message.
"""

from __future__ import annotations

import base64
import re
from datetime import datetime
from email.message import EmailMessage as PyEmailMessage
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.core.logging import get_logger
from app.services.email.types import RawAttachment, RawEmailMessage

logger = get_logger(__name__)

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

_FOLDER_LABEL_MAP = {
    "inbox": "INBOX",
    "sent": "SENT",
    "trash": "TRASH",
}


def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


def _decode_b64url(data: str) -> bytes:
    """Decode Gmail's base64url payload, padding as needed."""
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data = data + ("=" * padding)
    return base64.urlsafe_b64decode(data.encode("ascii"))


def _header(headers: list[dict[str, str]], name: str) -> str | None:
    lname = name.lower()
    for h in headers:
        if h.get("name", "").lower() == lname:
            return h.get("value")
    return None


def _parse_address_list(raw: str | None) -> list[dict[str, str]]:
    """Parse an RFC 2822 address list into ``[{email, name}, ...]``."""
    if not raw:
        return []
    out: list[dict[str, str]] = []
    # Split on commas that aren't inside quoted strings — rough but adequate
    # for the headers Gmail returns. ``email.utils.getaddresses`` is stricter
    # but pulls in extra deps; this matches Zoho/Outlook field shape.
    parts = re.split(r",(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", raw)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.match(r'^\s*(?:"?([^"<]*)"?\s*)?<([^>]+)>\s*$', part)
        if m:
            name = (m.group(1) or "").strip().strip('"')
            email_addr = m.group(2).strip()
        else:
            name = ""
            email_addr = part
        if email_addr:
            out.append({"email": email_addr, "name": name})
    return out


def _walk_payload(payload: dict[str, Any]) -> tuple[str | None, str | None, list[dict[str, Any]]]:
    """Walk a Gmail payload tree, returning (text_body, html_body, attachments).

    Attachments are returned as raw payload dicts so the caller can extract
    ``attachmentId`` / ``filename`` / ``mimeType`` / ``size``.
    """
    text_body: str | None = None
    html_body: str | None = None
    attachments: list[dict[str, Any]] = []

    def visit(node: dict[str, Any]) -> None:
        nonlocal text_body, html_body
        mime = node.get("mimeType", "")
        body = node.get("body", {}) or {}
        filename = node.get("filename") or ""
        attachment_id = body.get("attachmentId")

        if attachment_id or filename:
            # Treat any node with an attachmentId or non-empty filename as an
            # attachment, even when the MIME type would otherwise be inline.
            attachments.append(node)
        elif mime == "text/plain" and text_body is None:
            data = body.get("data")
            if data:
                try:
                    text_body = _decode_b64url(data).decode("utf-8", errors="replace")
                except Exception:
                    logger.warning("gmail.payload.text_decode_failed")
        elif mime == "text/html" and html_body is None:
            data = body.get("data")
            if data:
                try:
                    html_body = _decode_b64url(data).decode("utf-8", errors="replace")
                except Exception:
                    logger.warning("gmail.payload.html_decode_failed")

        for child in node.get("parts", []) or []:
            visit(child)

    visit(payload)
    return text_body, html_body, attachments


def _message_folder(label_ids: list[str]) -> str:
    """Map Gmail label set to the platform's folder enum."""
    if "TRASH" in label_ids:
        return "trash"
    if "SENT" in label_ids:
        return "sent"
    if "INBOX" in label_ids:
        return "inbox"
    return "archive"


def _to_raw_message(msg: dict[str, Any]) -> RawEmailMessage:
    payload = msg.get("payload", {}) or {}
    headers = payload.get("headers", []) or []
    label_ids = msg.get("labelIds", []) or []

    subject = _header(headers, "Subject")
    from_raw = _header(headers, "From") or ""
    from_addrs = _parse_address_list(from_raw)
    sender_email = from_addrs[0]["email"] if from_addrs else ""
    sender_name = from_addrs[0]["name"] if from_addrs else None

    date_raw = _header(headers, "Date")
    if date_raw:
        try:
            received_at = parsedate_to_datetime(date_raw).replace(tzinfo=None)
        except Exception:
            received_at = datetime.utcfromtimestamp(int(msg.get("internalDate", 0)) / 1000)
    else:
        received_at = datetime.utcfromtimestamp(int(msg.get("internalDate", 0)) / 1000)

    text_body, html_body, attachment_nodes = _walk_payload(payload)

    attachments = []
    for node in attachment_nodes:
        body = node.get("body", {}) or {}
        node_headers = node.get("headers", []) or []
        content_id_header = _header(node_headers, "Content-ID")
        content_id = content_id_header.strip("<>") if content_id_header else None
        is_inline = bool(content_id)
        attachments.append(
            RawAttachment(
                filename=node.get("filename") or "",
                content_type=node.get("mimeType"),
                size_bytes=body.get("size"),
                provider_attachment_id=body.get("attachmentId"),
                content_id=content_id,
                is_inline=is_inline,
            )
        )

    return RawEmailMessage(
        provider_message_id=msg.get("id", ""),
        thread_id=msg.get("threadId"),
        subject=subject,
        sender_email=sender_email,
        sender_name=sender_name,
        recipients_to=_parse_address_list(_header(headers, "To")),
        recipients_cc=_parse_address_list(_header(headers, "Cc")) or None,
        body_text=text_body or "",
        body_html=html_body,
        received_at=received_at,
        is_read="UNREAD" not in label_ids,
        folder=_message_folder(label_ids),
        labels=label_ids,
        has_attachments=bool(attachments),
        attachments=attachments,
    )


async def _fetch_message(
    client: httpx.AsyncClient, access_token: str, message_id: str
) -> dict[str, Any] | None:
    """Fetch a single message in 'full' format. Returns None on 404."""
    url = f"{GMAIL_BASE}/messages/{message_id}"
    resp = await client.get(url, headers=_headers(access_token), params={"format": "full"})
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


async def fetch_messages(
    access_token: str,
    *,
    history_cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[RawEmailMessage], str | None]:
    """Fetch new messages from Gmail.

    First sync (no cursor): list the most recent inbox messages and return
    their content + the current ``historyId`` as the cursor.
    Subsequent syncs: use ``users.history.list`` to find new message IDs since
    the cursor, then fetch their content. Returns (messages, next_cursor).
    """
    messages: list[RawEmailMessage] = []
    next_cursor: str | None = history_cursor

    async with httpx.AsyncClient(timeout=30.0) as client:
        if history_cursor is None:
            # Bootstrap: list recent inbox messages, capture profile historyId.
            list_resp = await client.get(
                f"{GMAIL_BASE}/messages",
                headers=_headers(access_token),
                params={"maxResults": limit, "labelIds": "INBOX"},
            )
            list_resp.raise_for_status()
            list_data = list_resp.json()
            message_ids = [m["id"] for m in list_data.get("messages", [])]

            profile_resp = await client.get(
                f"{GMAIL_BASE}/profile", headers=_headers(access_token)
            )
            profile_resp.raise_for_status()
            next_cursor = str(profile_resp.json().get("historyId", "")) or None

            for mid in message_ids:
                full = await _fetch_message(client, access_token, mid)
                if full is not None:
                    messages.append(_to_raw_message(full))
            return messages, next_cursor

        # Incremental: list history changes since cursor.
        history_resp = await client.get(
            f"{GMAIL_BASE}/history",
            headers=_headers(access_token),
            params={
                "startHistoryId": history_cursor,
                "historyTypes": "messageAdded",
                "labelId": "INBOX",
            },
        )
        if history_resp.status_code == 404:
            # historyId too old (Gmail purges history after ~7 days). Re-bootstrap.
            logger.warning(
                "gmail.history.cursor_expired", extra={"cursor": history_cursor}
            )
            return await fetch_messages(access_token, history_cursor=None, limit=limit)
        history_resp.raise_for_status()
        history_data = history_resp.json()

        next_cursor = str(history_data.get("historyId", history_cursor)) or history_cursor

        seen_ids: set[str] = set()
        for entry in history_data.get("history", []):
            for added in entry.get("messagesAdded", []):
                msg_id = added.get("message", {}).get("id")
                if msg_id and msg_id not in seen_ids:
                    seen_ids.add(msg_id)

        for mid in list(seen_ids)[:limit]:
            full = await _fetch_message(client, access_token, mid)
            if full is not None:
                messages.append(_to_raw_message(full))

    return messages, next_cursor


async def fetch_attachments(
    access_token: str,
    message_id: str,
) -> list[dict[str, Any]]:
    """Fetch attachment metadata for a message by re-fetching its payload.

    Gmail does not expose a separate ``attachments`` list endpoint; we walk
    the message payload and return the same shape Microsoft's helper uses.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        full = await _fetch_message(client, access_token, message_id)
    if full is None:
        return []
    _, _, nodes = _walk_payload(full.get("payload", {}) or {})
    out: list[dict[str, Any]] = []
    for node in nodes:
        body = node.get("body", {}) or {}
        node_headers = node.get("headers", []) or []
        content_id_header = _header(node_headers, "Content-ID")
        content_id = content_id_header.strip("<>") if content_id_header else None
        out.append(
            {
                "provider_attachment_id": body.get("attachmentId", ""),
                "filename": node.get("filename") or "",
                "content_type": node.get("mimeType"),
                "size_bytes": body.get("size"),
                "content_id": content_id,
                "is_inline": bool(content_id),
            }
        )
    return out


async def download_attachment(
    access_token: str,
    message_id: str,
    attachment_id: str,
) -> tuple[bytes, str, str]:
    """Download attachment bytes from Gmail.

    Gmail returns ``{data, size}`` with ``data`` as base64url. We return
    ``(content_bytes, filename, content_type)``; the filename and content
    type come from the parent message payload (Gmail's attachment endpoint
    does not return them).
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Look up filename + content type from the parent message
        full = await _fetch_message(client, access_token, message_id)
        filename = "attachment"
        content_type = "application/octet-stream"
        if full is not None:
            _, _, nodes = _walk_payload(full.get("payload", {}) or {})
            for node in nodes:
                if (node.get("body", {}) or {}).get("attachmentId") == attachment_id:
                    filename = node.get("filename") or filename
                    content_type = node.get("mimeType") or content_type
                    break

        att_resp = await client.get(
            f"{GMAIL_BASE}/messages/{message_id}/attachments/{attachment_id}",
            headers=_headers(access_token),
        )
        att_resp.raise_for_status()
        data = att_resp.json().get("data", "")
        content = _decode_b64url(data) if data else b""

    return content, filename, content_type


def _build_rfc822(
    *,
    sender: str,
    to: str,
    subject: str,
    body: str,
    body_html: str | None = None,
    in_reply_to_message_id: str | None = None,
    references: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> bytes:
    """Build an RFC 822 message ready for base64url encoding."""
    msg = PyEmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    if in_reply_to_message_id:
        msg["In-Reply-To"] = in_reply_to_message_id
        msg["References"] = references or in_reply_to_message_id

    if body_html:
        msg.set_content(body or "")
        msg.add_alternative(body_html, subtype="html")
    else:
        msg.set_content(body or "")

    if attachments:
        for att in attachments:
            content_bytes = att["content_bytes"]
            content_type = att.get("content_type") or "application/octet-stream"
            maintype, _, subtype = content_type.partition("/")
            msg.add_attachment(
                content_bytes,
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=att["filename"],
            )

    return bytes(msg)


async def send_message(
    access_token: str,
    *,
    sender: str,
    to: str,
    subject: str,
    body: str,
    body_html: str | None = None,
    in_reply_to_message_id: str | None = None,
    thread_id: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Send a message via Gmail.

    For replies, pass the original RFC 822 ``Message-Id`` as
    ``in_reply_to_message_id`` and the Gmail thread ID as ``thread_id`` so
    Gmail threads the reply correctly.
    """
    raw = _build_rfc822(
        sender=sender,
        to=to,
        subject=subject,
        body=body,
        body_html=body_html,
        in_reply_to_message_id=in_reply_to_message_id,
        attachments=attachments,
    )
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    payload: dict[str, Any] = {"raw": encoded}
    if thread_id:
        payload["threadId"] = thread_id

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{GMAIL_BASE}/messages/send",
            headers=_headers(access_token),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]


async def move_message(
    access_token: str,
    message_id: str,
    *,
    target_folder: str,
) -> None:
    """Move a message between folders by adjusting Gmail labels.

    archive -> remove INBOX
    trash   -> add TRASH (and remove INBOX)
    inbox   -> add INBOX, remove TRASH
    """
    add: list[str] = []
    remove: list[str] = []
    if target_folder == "archive":
        remove.append("INBOX")
    elif target_folder == "trash":
        add.append("TRASH")
        remove.append("INBOX")
    elif target_folder == "inbox":
        add.append("INBOX")
        remove.append("TRASH")
    else:
        raise ValueError(f"Unsupported Gmail target folder: {target_folder!r}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{GMAIL_BASE}/messages/{message_id}/modify",
            headers=_headers(access_token),
            json={"addLabelIds": add, "removeLabelIds": remove},
        )
        resp.raise_for_status()


async def mark_read(
    access_token: str,
    message_id: str,
    *,
    read: bool = True,
) -> None:
    """Mark a Gmail message as read or unread by toggling the UNREAD label."""
    add = [] if read else ["UNREAD"]
    remove = ["UNREAD"] if read else []
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{GMAIL_BASE}/messages/{message_id}/modify",
            headers=_headers(access_token),
            json={"addLabelIds": add, "removeLabelIds": remove},
        )
        resp.raise_for_status()
