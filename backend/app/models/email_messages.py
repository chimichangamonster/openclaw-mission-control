"""Synced email message model."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, Text, UniqueConstraint
from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped

RUNTIME_ANNOTATION_TYPES = (datetime,)


class EmailMessage(TenantScoped, table=True):
    """Individual email message synced from a connected email account."""

    __tablename__ = "email_messages"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint(
            "email_account_id",
            "provider_message_id",
            name="uq_email_messages_account_provider_msg",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    email_account_id: UUID = Field(foreign_key="email_accounts.id", index=True)
    provider_message_id: str = Field(index=True)
    thread_id: str | None = None
    subject: str | None = None
    sender_email: str = ""
    sender_name: str | None = None
    recipients_to: list[dict[str, str]] = Field(default_factory=list, sa_column=Column(JSON))
    recipients_cc: list[dict[str, str]] | None = Field(default=None, sa_column=Column(JSON))
    body_text: str | None = Field(default=None, sa_column=Column(Text))
    body_html: str | None = Field(default=None, sa_column=Column(Text))
    received_at: datetime = Field(default_factory=utcnow, index=True)
    is_read: bool = Field(default=False)
    is_starred: bool = Field(default=False)
    folder: str = Field(default="inbox", index=True)  # inbox, sent, archive, trash
    labels: list[str] | None = Field(default=None, sa_column=Column(JSON))
    has_attachments: bool = Field(default=False)
    triage_status: str = Field(default="pending", index=True)  # pending, triaged, actioned, ignored
    triage_category: str | None = None
    linked_task_id: UUID | None = Field(default=None, foreign_key="tasks.id", index=True)
    synced_at: datetime = Field(default_factory=utcnow)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
