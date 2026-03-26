"""Schemas for gateway passthrough API request and response payloads."""

from __future__ import annotations

from sqlmodel import SQLModel

from app.schemas.common import NonEmptyStr

RUNTIME_ANNOTATION_TYPES = (NonEmptyStr,)


class ChatAttachment(SQLModel):
    """Reference to a previously-uploaded file attached to a chat message."""

    filename: str
    workspace_path: str
    content_type: str
    size_bytes: int
    sanitized_workspace_path: str | None = None


class GatewaySessionMessageRequest(SQLModel):
    """Request payload for sending a message into a gateway session."""

    content: NonEmptyStr
    attachments: list[ChatAttachment] | None = None


class ChatUploadResponse(SQLModel):
    """Response after uploading a file for chat attachment."""

    filename: str
    workspace_path: str
    content_type: str
    size_bytes: int
    sanitized_workspace_path: str | None = None


class CreateSessionRequest(SQLModel):
    """Request payload for creating a new named chat session."""

    label: NonEmptyStr


class CreateSessionResponse(SQLModel):
    """Response after creating a new chat session."""

    session_key: str
    session: object


class RenameSessionRequest(SQLModel):
    """Request payload for renaming a chat session."""

    label: NonEmptyStr


class GatewayResolveQuery(SQLModel):
    """Query parameters used to resolve which gateway to target."""

    board_id: str | None = None
    gateway_url: str | None = None
    gateway_token: str | None = None
    gateway_disable_device_pairing: bool | None = None
    gateway_allow_insecure_tls: bool | None = None


class GatewaysStatusResponse(SQLModel):
    """Aggregated gateway status response including session metadata."""

    connected: bool
    gateway_url: str
    sessions_count: int | None = None
    sessions: list[object] | None = None
    main_session: object | None = None
    main_session_error: str | None = None
    error: str | None = None


class GatewaySessionsResponse(SQLModel):
    """Gateway sessions list response payload."""

    sessions: list[object]
    main_session: object | None = None


class GatewaySessionResponse(SQLModel):
    """Single gateway session response payload."""

    session: object


class GatewaySessionHistoryResponse(SQLModel):
    """Gateway session history response payload."""

    history: list[object]


class GatewayCommandsResponse(SQLModel):
    """Gateway command catalog and protocol metadata."""

    protocol_version: int
    methods: list[str]
    events: list[str]
