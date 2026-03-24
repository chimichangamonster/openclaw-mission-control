"""WeCom (Enterprise WeChat) connection per organization."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped


class WeComConnection(TenantScoped, table=True):
    """WeCom integration credentials and config for an organization."""

    __tablename__ = "wecom_connections"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint("organization_id", "corp_id", name="uq_wecom_org_corp"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)  # who configured it

    # WeCom corp config
    corp_id: str = Field(index=True)
    agent_id: str = ""  # WeCom app agent ID (for API replies)

    # Callback verification (inbound messages)
    callback_token: str = ""  # Token for SHA1 signature verification
    encoding_aes_key: str = ""  # 43-char Base64 AES key for message encryption

    # API credentials (outbound replies)
    corp_secret_encrypted: str | None = None  # Fernet-encrypted corpsecret

    # Cached access token (refreshed every ~2 hours)
    access_token_encrypted: str | None = None
    access_token_expires_at: datetime | None = None

    # Routing config
    is_active: bool = Field(default=True)
    target_agent_id: str = Field(default="the-claw")  # which agent handles messages
    target_channel: str = Field(default="general")  # gateway channel to route to

    # Display
    label: str = ""  # user-friendly name for this connection

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
