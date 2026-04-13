"""Schemas for email account and message endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel import SQLModel

from app.schemas.common import NonEmptyStr

RUNTIME_ANNOTATION_TYPES = (datetime, UUID, NonEmptyStr)


# --- Email Accounts ---


class EmailAccountRead(SQLModel):
    """Serialized email account (no tokens exposed)."""

    id: UUID
    organization_id: UUID
    user_id: UUID
    provider: str
    email_address: str
    display_name: str | None = None
    sync_enabled: bool
    visibility: str = "shared"
    last_sync_at: datetime | None = None
    last_sync_error: str | None = None
    created_at: datetime
    updated_at: datetime


class EmailAccountUpdate(SQLModel):
    """Payload for updating an email account."""

    sync_enabled: bool | None = None
    display_name: str | None = None
    visibility: str | None = None


# --- Email Messages ---


class EmailMessageRead(SQLModel):
    """Serialized email message for list views (no HTML body)."""

    id: UUID
    organization_id: UUID
    email_account_id: UUID
    provider_message_id: str
    thread_id: str | None = None
    subject: str | None = None
    sender_email: str
    sender_name: str | None = None
    recipients_to: list[dict[str, str]] = []
    recipients_cc: list[dict[str, str]] | None = None
    body_text: str | None = None
    received_at: datetime
    is_read: bool
    is_starred: bool
    folder: str
    labels: list[str] | None = None
    has_attachments: bool
    triage_status: str
    triage_category: str | None = None
    triage_trace_id: str | None = None
    linked_task_id: UUID | None = None
    synced_at: datetime
    created_at: datetime


class EmailMessageDetail(EmailMessageRead):
    """Full email message including HTML body."""

    body_html: str | None = None


class EmailMessageUpdate(SQLModel):
    """Payload for updating email message metadata."""

    is_read: bool | None = None
    is_starred: bool | None = None
    triage_status: str | None = None
    triage_category: str | None = None
    triage_trace_id: str | None = None
    linked_task_id: UUID | None = None


class EmailReplyCreate(SQLModel):
    """Payload for replying to an email."""

    body_text: NonEmptyStr
    body_html: str | None = None


class EmailForwardCreate(SQLModel):
    """Payload for forwarding an email."""

    to: NonEmptyStr
    body_text: str | None = None


class EmailSendCreate(SQLModel):
    """Payload for sending a new email (not a reply)."""

    to: NonEmptyStr
    subject: NonEmptyStr
    body: NonEmptyStr
    body_html: str | None = None


class EmailSyncTriggerResponse(SQLModel):
    """Response for triggering an email sync."""

    ok: bool = True
    enqueued: bool = True


class EmailAttachmentRead(SQLModel):
    """Serialized email attachment metadata."""

    id: UUID
    email_message_id: UUID
    filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    is_inline: bool = False
    created_at: datetime
