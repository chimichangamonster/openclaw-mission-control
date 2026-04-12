"""Audit log for security-sensitive operations."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlmodel import Field

from app.core.time import utcnow
from app.models.base import QueryModel


class AuditLog(QueryModel, table=True):
    """Immutable log of security-sensitive operations per organization."""

    __tablename__ = "audit_logs"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    user_id: UUID | None = Field(default=None, foreign_key="users.id")
    action: str = Field(index=True)  # e.g. "settings.update", "key.rotate", "member.add"
    resource_type: str = Field(default="")  # e.g. "organization_settings", "organization_member"
    resource_id: UUID | None = Field(default=None)
    details_json: str = Field(default="{}")
    ip_address: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow, index=True)

    @property
    def details(self) -> dict[str, Any]:
        return json.loads(self.details_json)  # type: ignore[no-any-return]
