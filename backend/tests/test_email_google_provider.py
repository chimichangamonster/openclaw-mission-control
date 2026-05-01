# ruff: noqa: INP001
"""Unit tests for the Gmail / Google Workspace email provider.

Covers:
- The OAuth factory wiring for the new "google" provider.
- Pure-function helpers in services/email/providers/google.py:
  header lookup, RFC 2822 address parsing, payload walking,
  folder/label mapping, base64url decoding, RFC 822 build.
- The send_email and sync dispatchers route the "google" provider
  to the Gmail module without requiring live HTTP.
"""

from __future__ import annotations

import base64
from email import message_from_bytes, policy
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.models.email_accounts import EmailAccount
from app.services.email.oauth import (
    GoogleEmailOAuthProvider,
    MicrosoftOAuthProvider,
    ZohoOAuthProvider,
    get_oauth_provider,
)
from app.services.email.providers.google import (
    _build_rfc822,
    _decode_b64url,
    _header,
    _message_folder,
    _parse_address_list,
    _to_raw_message,
    _walk_payload,
)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_returns_google_provider():
    assert isinstance(get_oauth_provider("google"), GoogleEmailOAuthProvider)
    assert isinstance(get_oauth_provider("zoho"), ZohoOAuthProvider)
    assert isinstance(get_oauth_provider("microsoft"), MicrosoftOAuthProvider)


def test_factory_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unknown email provider"):
        get_oauth_provider("yahoo")


def test_google_provider_scopes_include_gmail():
    """Scopes must include readonly + send + modify so triage and reply work."""
    scopes = GoogleEmailOAuthProvider.SCOPES
    assert "gmail.readonly" in scopes
    assert "gmail.send" in scopes
    assert "gmail.modify" in scopes


# ---------------------------------------------------------------------------
# Header lookup
# ---------------------------------------------------------------------------


def test_header_lookup_case_insensitive():
    headers = [
        {"name": "Subject", "value": "Hello"},
        {"name": "From", "value": "alice@example.com"},
    ]
    assert _header(headers, "subject") == "Hello"
    assert _header(headers, "SUBJECT") == "Hello"
    assert _header(headers, "from") == "alice@example.com"


def test_header_lookup_returns_none_when_missing():
    assert _header([{"name": "Subject", "value": "Hi"}], "Date") is None


# ---------------------------------------------------------------------------
# Address list parsing
# ---------------------------------------------------------------------------


def test_parse_address_list_bare_email():
    assert _parse_address_list("alice@example.com") == [
        {"email": "alice@example.com", "name": ""}
    ]


def test_parse_address_list_named_with_brackets():
    out = _parse_address_list('"Alice Smith" <alice@example.com>')
    assert out == [{"email": "alice@example.com", "name": "Alice Smith"}]


def test_parse_address_list_multiple_recipients():
    out = _parse_address_list("alice@example.com, Bob <bob@example.com>")
    assert out == [
        {"email": "alice@example.com", "name": ""},
        {"email": "bob@example.com", "name": "Bob"},
    ]


def test_parse_address_list_handles_empty():
    assert _parse_address_list("") == []
    assert _parse_address_list(None) == []


# ---------------------------------------------------------------------------
# Folder / label mapping
# ---------------------------------------------------------------------------


def test_message_folder_inbox():
    assert _message_folder(["INBOX", "UNREAD"]) == "inbox"


def test_message_folder_sent():
    assert _message_folder(["SENT"]) == "sent"


def test_message_folder_trash_takes_precedence_over_inbox():
    """Even if INBOX is still set somehow, TRASH wins."""
    assert _message_folder(["TRASH", "INBOX"]) == "trash"


def test_message_folder_archive_when_no_special_labels():
    assert _message_folder(["IMPORTANT", "CATEGORY_PERSONAL"]) == "archive"
    assert _message_folder([]) == "archive"


# ---------------------------------------------------------------------------
# Base64url
# ---------------------------------------------------------------------------


def test_decode_b64url_handles_missing_padding():
    raw = b"hello world"
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    assert _decode_b64url(encoded) == raw


# ---------------------------------------------------------------------------
# Payload walking
# ---------------------------------------------------------------------------


def test_walk_payload_extracts_text_and_html_parts():
    text_data = base64.urlsafe_b64encode(b"plain body").decode().rstrip("=")
    html_data = base64.urlsafe_b64encode(b"<p>html body</p>").decode().rstrip("=")
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": text_data}},
            {"mimeType": "text/html", "body": {"data": html_data}},
        ],
    }
    text, html, attachments = _walk_payload(payload)
    assert text == "plain body"
    assert html == "<p>html body</p>"
    assert attachments == []


def test_walk_payload_treats_filenamed_part_as_attachment():
    """Even an HTML part with a filename is an attachment, not the body."""
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "application/pdf",
                "filename": "invoice.pdf",
                "body": {"attachmentId": "att-123", "size": 4096},
            },
            {
                "mimeType": "text/plain",
                "body": {
                    "data": base64.urlsafe_b64encode(b"body").decode().rstrip("=")
                },
            },
        ],
    }
    text, _, attachments = _walk_payload(payload)
    assert text == "body"
    assert len(attachments) == 1
    assert attachments[0]["filename"] == "invoice.pdf"


# ---------------------------------------------------------------------------
# Full Gmail message → RawEmailMessage shape
# ---------------------------------------------------------------------------


def test_to_raw_message_full_shape():
    body_data = base64.urlsafe_b64encode(b"hello there").decode().rstrip("=")
    gmail_msg = {
        "id": "abc123",
        "threadId": "thread-1",
        "labelIds": ["INBOX", "UNREAD"],
        "internalDate": "1714000000000",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Subject", "value": "Test subject"},
                {"name": "From", "value": '"Alice" <alice@example.com>'},
                {"name": "To", "value": "bob@example.com"},
                {"name": "Cc", "value": "carol@example.com"},
                {"name": "Date", "value": "Wed, 24 Apr 2026 12:00:00 +0000"},
            ],
            "body": {"data": body_data},
        },
    }
    raw = _to_raw_message(gmail_msg)
    assert raw.provider_message_id == "abc123"
    assert raw.thread_id == "thread-1"
    assert raw.subject == "Test subject"
    assert raw.sender_email == "alice@example.com"
    assert raw.sender_name == "Alice"
    assert raw.recipients_to == [{"email": "bob@example.com", "name": ""}]
    assert raw.recipients_cc == [{"email": "carol@example.com", "name": ""}]
    assert raw.body_text == "hello there"
    assert raw.is_read is False  # UNREAD label present
    assert raw.folder == "inbox"
    assert raw.has_attachments is False


def test_to_raw_message_marks_read_when_unread_label_absent():
    body_data = base64.urlsafe_b64encode(b"x").decode().rstrip("=")
    gmail_msg = {
        "id": "x",
        "threadId": "x",
        "labelIds": ["INBOX"],  # no UNREAD
        "internalDate": "1714000000000",
        "payload": {
            "mimeType": "text/plain",
            "headers": [{"name": "From", "value": "a@b.c"}],
            "body": {"data": body_data},
        },
    }
    assert _to_raw_message(gmail_msg).is_read is True


# ---------------------------------------------------------------------------
# RFC 822 build
# ---------------------------------------------------------------------------


def test_build_rfc822_plain_text():
    raw = _build_rfc822(
        sender="alice@example.com",
        to="bob@example.com",
        subject="Hi",
        body="hello world",
    )
    parsed = message_from_bytes(raw, policy=policy.default)
    assert parsed["From"] == "alice@example.com"
    assert parsed["To"] == "bob@example.com"
    assert parsed["Subject"] == "Hi"
    assert "hello world" in parsed.get_content()


def test_build_rfc822_with_html_alternative():
    raw = _build_rfc822(
        sender="alice@example.com",
        to="bob@example.com",
        subject="Hi",
        body="plain",
        body_html="<p>html</p>",
    )
    parsed = message_from_bytes(raw)
    # Should be multipart/alternative with both bodies present
    payload_strs = [
        part.get_payload(decode=True).decode("utf-8", errors="replace")
        for part in parsed.walk()
        if not part.is_multipart()
    ]
    assert any("plain" in s for s in payload_strs)
    assert any("<p>html</p>" in s for s in payload_strs)


def test_build_rfc822_threading_headers_for_reply():
    raw = _build_rfc822(
        sender="alice@example.com",
        to="bob@example.com",
        subject="Re: Hi",
        body="reply body",
        in_reply_to_message_id="<original@example.com>",
    )
    parsed = message_from_bytes(raw)
    assert parsed["In-Reply-To"] == "<original@example.com>"
    assert parsed["References"] == "<original@example.com>"


def test_build_rfc822_with_attachment():
    raw = _build_rfc822(
        sender="alice@example.com",
        to="bob@example.com",
        subject="With file",
        body="see attached",
        attachments=[
            {
                "filename": "report.pdf",
                "content_bytes": b"%PDF-fake",
                "content_type": "application/pdf",
            }
        ],
    )
    parsed = message_from_bytes(raw)
    found_attachment = False
    for part in parsed.walk():
        if part.get_filename() == "report.pdf":
            found_attachment = True
            assert part.get_content_type() == "application/pdf"
    assert found_attachment, "PDF attachment should be in the message"


# ---------------------------------------------------------------------------
# Dispatcher routing
# ---------------------------------------------------------------------------


def _make_account(provider: str = "google") -> EmailAccount:
    return EmailAccount(
        id=uuid4(),
        organization_id=uuid4(),
        user_id=uuid4(),
        provider=provider,
        email_address="henry@magnetiksolutions.com",
        display_name="Henry Chin",
        access_token_encrypted="enc",
        refresh_token_encrypted="enc",
    )


@pytest.mark.asyncio
async def test_email_send_dispatch_routes_google_to_gmail_module():
    """services.email_send.send_email should dispatch google to gmail send."""
    from app.services import email_send as send_module

    account = _make_account("google")

    fake_token = AsyncMock(return_value="access-token")
    fake_send = AsyncMock(return_value={"id": "sent-1"})

    with (
        patch.object(send_module, "get_valid_access_token", fake_token),
        patch(
            "app.services.email.providers.google.send_message",
            fake_send,
        ),
    ):
        result = await send_module.send_email(
            session=AsyncMock(),
            account=account,
            to="client@example.com",
            subject="Hi",
            body="body",
        )

    assert result == {"id": "sent-1"}
    fake_send.assert_awaited_once()
    call_kwargs = fake_send.await_args.kwargs
    # Sender should be formatted with display name when available
    assert call_kwargs["sender"] == "Henry Chin <henry@magnetiksolutions.com>"
    assert call_kwargs["to"] == "client@example.com"
    assert call_kwargs["subject"] == "Hi"


@pytest.mark.asyncio
async def test_email_send_dispatch_uses_bare_address_when_no_display_name():
    from app.services import email_send as send_module

    account = _make_account("google")
    account.display_name = None

    fake_send = AsyncMock(return_value={"id": "x"})
    with (
        patch.object(send_module, "get_valid_access_token", AsyncMock(return_value="t")),
        patch("app.services.email.providers.google.send_message", fake_send),
    ):
        await send_module.send_email(
            session=AsyncMock(),
            account=account,
            to="c@e.com",
            subject="s",
            body="b",
        )

    assert fake_send.await_args.kwargs["sender"] == "henry@magnetiksolutions.com"


@pytest.mark.asyncio
async def test_sync_dispatch_routes_google_to_gmail_fetch():
    """services.email.sync._fetch_from_provider routes google correctly + advances cursor."""
    from app.services.email import sync as sync_module

    account = _make_account("google")
    account.sync_cursor = "old-cursor"

    fake_fetch = AsyncMock(return_value=([], "new-cursor"))
    with patch("app.services.email.providers.google.fetch_messages", fake_fetch):
        await sync_module._fetch_from_provider("access-token", account)

    fake_fetch.assert_awaited_once_with(
        "access-token", history_cursor="old-cursor"
    )
    assert account.sync_cursor == "new-cursor"
