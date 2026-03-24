"""Pydantic schemas for WeCom API endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class WeComConnectionCreate(BaseModel):
    """Request body for creating a WeCom connection."""

    corp_id: str = Field(..., min_length=1, description="WeCom Corp ID")
    agent_id: str = Field(default="", description="WeCom app agent ID")
    callback_token: str = Field(..., min_length=1, description="Callback verification token")
    encoding_aes_key: str = Field(
        ..., min_length=43, max_length=43, description="43-char Base64 AES key"
    )
    corp_secret: str = Field(default="", description="Corp secret (will be encrypted)")
    target_agent_id: str = Field(default="the-claw", description="Gateway agent to handle messages")
    target_channel: str = Field(default="general", description="Gateway channel")
    label: str = Field(default="", description="Display label")


class WeComConnectionUpdate(BaseModel):
    """Request body for updating a WeCom connection."""

    agent_id: str | None = None
    callback_token: str | None = None
    encoding_aes_key: str | None = None
    corp_secret: str | None = None
    target_agent_id: str | None = None
    target_channel: str | None = None
    label: str | None = None
    is_active: bool | None = None


class WeComConnectionResponse(BaseModel):
    """WeCom connection info returned to the client (secrets masked)."""

    id: UUID
    organization_id: UUID
    corp_id: str
    agent_id: str
    callback_token: str
    has_corp_secret: bool
    target_agent_id: str
    target_channel: str
    label: str
    is_active: bool
    callback_url: str  # computed: the URL WeCom should POST to
    created_at: datetime
    updated_at: datetime


class WeComTestResult(BaseModel):
    """Result of testing WeCom API connectivity."""

    success: bool
    message: str
    corp_name: str | None = None
