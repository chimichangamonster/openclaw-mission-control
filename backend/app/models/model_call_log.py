"""Per-call audit log for mc-backend LLM API traffic.

Records every LLM call mc-backend makes directly (session titling, embeddings,
document intake, etc.) with rich error metadata. Covers the ~10% of platform
LLM traffic that flows through mc-backend; gateway-driven traffic is tracked
separately via the gateway's OpenRouter Activity data (Layer 2 follow-up).

Source of truth for the reliability axis in the model-benchmark skill.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, Index, Text
from sqlmodel import Field

from app.core.time import utcnow
from app.models.tenancy import TenantScoped


class ModelCallLog(TenantScoped, table=True):
    """One row per LLM call from mc-backend.

    Includes failed calls — the reliability signal depends on capturing errors,
    not just successes. error_body truncated to 500 chars to bound storage.
    """

    __tablename__ = "model_call_log"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        Index("ix_model_call_log_model_created", "model", "created_at"),
        Index("ix_model_call_log_status_created", "status", "created_at"),
        Index("ix_model_call_log_org_created", "organization_id", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID | None = Field(default=None, foreign_key="organizations.id", index=True)
    model: str = Field(index=True)
    provider: str  # "openrouter" | "custom" | "anthropic_direct"
    provider_name: str | None = None  # e.g. "Anthropic" (extracted from OpenRouter error metadata)
    skill_name: str  # caller identifier: "session_titler" | "embedding" | "document_intake" | ...
    status: str = Field(index=True)  # "success" | "error" | "timeout"
    http_status: int | None = None
    error_type: str | None = None  # "rate_limit" | "server_error" | "timeout" | "auth" | ...
    error_body: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    latency_ms: int
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost_usd: float | None = None
    created_at: datetime = Field(default_factory=utcnow, index=True)
