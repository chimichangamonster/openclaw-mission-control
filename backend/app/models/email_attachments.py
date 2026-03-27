"""Email attachment metadata model."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field

from app.core.time import utcnow
from app.models.base import QueryModel

RUNTIME_ANNOTATION_TYPES = (datetime,)


class EmailAttachment(QueryModel, table=True):
    """Attachment metadata for a synced email message."""

    __tablename__ = "email_attachments"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email_message_id: UUID = Field(foreign_key="email_messages.id", index=True)
    filename: str = ""
    content_type: str | None = None
    size_bytes: int | None = None
    provider_attachment_id: str | None = None
    content_id: str | None = Field(default=None)
    is_inline: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)
