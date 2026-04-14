"""ChatProject — pure organizational tag for grouping chat sessions.

No LLM coupling. Projects are metadata only — name, color, sort order, archived
state. The agent does not see the project unless the user explicitly types it
into the chat. Session-to-project assignments are stored in OrgConfigData under
category `session_project_assignments` to avoid FK-dangling with gateway-owned
session keys.

See docs/technical/chat-reorganization-plan.md Tier 1.4 for the full rationale.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped


class ChatProject(TenantScoped, table=True):
    """Per-org chat project tag. Metadata only — no system prompts, no memory."""

    __tablename__ = "chat_projects"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    name: str
    description: str | None = None
    color: str | None = None
    sort_order: int = 0
    archived: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
