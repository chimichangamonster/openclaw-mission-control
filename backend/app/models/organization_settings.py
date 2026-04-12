"""Per-organization settings — BYOK keys, feature flags, model config, branding."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field

from app.core.time import utcnow
from app.models.base import QueryModel

# Default feature flags — all enabled for backwards compatibility
DEFAULT_FEATURE_FLAGS = {
    "paper_trading": True,
    "paper_bets": True,
    "email": True,
    "polymarket": False,
    "crypto_trading": False,
    "watchlist": True,
    "cost_tracker": True,
    "cron_jobs": True,
    "approvals": True,
    "document_generation": True,
    "microsoft_graph": False,
    "google_calendar": False,
    "bookkeeping": True,
    "wechat": False,
    "pentest": False,
}


class OrganizationSettings(QueryModel, table=True):
    """Per-organization configuration — API keys, feature flags, branding."""

    __tablename__ = "organization_settings"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (UniqueConstraint("organization_id", name="uq_org_settings_org"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    organization_id: UUID = Field(foreign_key="organizations.id", index=True)

    # BYOK — Fernet-encrypted API keys (nullable = use platform default)
    openrouter_api_key_encrypted: str | None = Field(default=None)
    openrouter_management_key_encrypted: str | None = Field(default=None)

    # Adobe PDF Services (client_id + client_secret, both Fernet-encrypted)
    adobe_pdf_client_id_encrypted: str | None = Field(default=None)
    adobe_pdf_client_secret_encrypted: str | None = Field(default=None)

    # Custom LLM endpoint (enterprise — self-hosted models)
    # JSON: {"api_url": "https://llm.corp.internal/v1", "api_key_encrypted": "...", "models": ["llama-3.1-70b"], "name": "Corp LLM"}
    custom_llm_endpoint_json: str = Field(default="{}")
    custom_llm_api_key_encrypted: str | None = Field(default=None)

    # Model configuration
    default_model_tier_max: int = Field(default=3)
    configured_models_json: str = Field(default="[]")
    model_pins_json: str = Field(default="{}")

    # Feature flags
    feature_flags_json: str = Field(default=json.dumps(DEFAULT_FEATURE_FLAGS))

    # Agent defaults (identity_profile template for new agents)
    agent_defaults_json: str = Field(default="{}")

    # Data privacy policy
    data_policy_json: str = Field(
        default='{"redaction_level":"moderate","allow_email_content_to_llm":true,"log_llm_inputs":false}'
    )

    # Industry template
    industry_template_id: str | None = Field(default=None)  # "construction", "staffing", etc.

    # Timezone and location
    timezone: str = Field(default="America/Edmonton")
    location: str = Field(default="")

    # Branding / org context
    branding_json: str = Field(default="{}")

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @property
    def feature_flags(self) -> dict[str, bool]:
        base = dict(DEFAULT_FEATURE_FLAGS)
        base.update(json.loads(self.feature_flags_json))
        return base

    @property
    def configured_models(self) -> list[str]:
        return json.loads(self.configured_models_json)  # type: ignore[no-any-return]

    @property
    def model_pins(self) -> dict[str, str]:
        return json.loads(self.model_pins_json)  # type: ignore[no-any-return]

    @property
    def agent_defaults(self) -> dict[str, Any]:
        return json.loads(self.agent_defaults_json)  # type: ignore[no-any-return]

    @property
    def custom_llm_endpoint(self) -> dict[str, Any]:
        return json.loads(self.custom_llm_endpoint_json)  # type: ignore[no-any-return]

    @property
    def data_policy(self) -> dict[str, Any]:
        return json.loads(self.data_policy_json)  # type: ignore[no-any-return]

    @property
    def branding(self) -> dict[str, Any]:
        return json.loads(self.branding_json)  # type: ignore[no-any-return]
