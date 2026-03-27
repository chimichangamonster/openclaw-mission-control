"""Shared data types for the email integration service layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class OAuthTokenResult:
    """Tokens and metadata returned after a successful OAuth2 code exchange."""

    access_token: str
    refresh_token: str
    expires_in: int
    scopes: str
    provider_account_id: str
    email_address: str
    display_name: str | None = None


@dataclass(frozen=True)
class RawEmailMessage:
    """Normalized email message fetched from a provider API."""

    provider_message_id: str
    thread_id: str | None
    subject: str | None
    sender_email: str
    sender_name: str | None
    recipients_to: list[dict[str, str]]
    recipients_cc: list[dict[str, str]] | None
    body_text: str | None
    body_html: str | None
    received_at: datetime
    is_read: bool
    folder: str
    labels: list[str] | None
    has_attachments: bool
    attachments: list[RawAttachment] = field(default_factory=list)


@dataclass(frozen=True)
class RawAttachment:
    """Attachment metadata from a provider API response."""

    filename: str
    content_type: str | None
    size_bytes: int | None
    provider_attachment_id: str | None
    content_id: str | None = None
    is_inline: bool = False
