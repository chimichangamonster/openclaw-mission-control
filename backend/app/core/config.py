"""Application settings and environment configuration loading."""

from __future__ import annotations

from pathlib import Path
from typing import Self
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.auth_mode import AuthMode
from app.core.rate_limit_backend import RateLimitBackend

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = BACKEND_ROOT / ".env"
LOCAL_AUTH_TOKEN_MIN_LENGTH = 50
LOCAL_AUTH_TOKEN_PLACEHOLDERS = frozenset(
    {
        "change-me",
        "changeme",
        "replace-me",
        "replace-with-strong-random-token",
    },
)


class Settings(BaseSettings):
    """Typed runtime configuration sourced from environment variables."""

    model_config = SettingsConfigDict(
        # Load `backend/.env` regardless of current working directory.
        # (Important when running uvicorn from repo root or via a process manager.)
        env_file=[DEFAULT_ENV_FILE, ".env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "dev"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/openclaw_agency"

    # Auth mode: "clerk" for Clerk JWT auth, "local" for shared bearer token,
    # "wechat" for WeCom/WeChat OAuth (China deployments).
    auth_mode: AuthMode
    local_auth_token: str = ""

    # Clerk auth (auth only; roles stored in DB)
    clerk_secret_key: str = ""
    clerk_api_url: str = "https://api.clerk.com"
    clerk_verify_iat: bool = True
    clerk_leeway: float = 10.0

    # Signup allowlist: comma-separated emails permitted to create accounts.
    # Empty string = open registration (NOT recommended for production).
    allowed_signup_emails: str = ""

    # WeChat/WeCom OAuth (China deployments)
    wechat_corp_id: str = ""
    wechat_app_secret: str = ""
    wechat_agent_id: str = ""

    # WeChat as secondary login alongside Clerk (dual-mode)
    wechat_login_enabled: bool = False

    cors_origins: str = ""
    base_url: str = ""

    # Security response headers (set to blank to disable a specific header)
    security_header_x_content_type_options: str = "nosniff"
    security_header_x_frame_options: str = "DENY"
    security_header_referrer_policy: str = "strict-origin-when-cross-origin"
    security_header_permissions_policy: str = ""

    # Webhook payload size limit in bytes (default 1 MB).
    webhook_max_payload_bytes: int = 1_048_576

    # Rate limiting
    rate_limit_backend: RateLimitBackend = RateLimitBackend.MEMORY
    rate_limit_redis_url: str = ""

    # Trusted reverse-proxy IPs/CIDRs for client-IP extraction from
    # Forwarded / X-Forwarded-For headers.  Comma-separated.
    # Leave empty to always use the direct peer address.
    trusted_proxies: str = ""

    # Database lifecycle
    db_auto_migrate: bool = False

    # RQ queueing / dispatch
    rq_redis_url: str = "redis://localhost:6379/0"
    rq_queue_name: str = "default"
    rq_dispatch_throttle_seconds: float = 15.0
    rq_dispatch_max_retries: int = 3
    rq_dispatch_retry_base_seconds: float = 10.0
    rq_dispatch_retry_max_seconds: float = 120.0

    # Email OAuth - Zoho
    zoho_oauth_client_id: str = ""
    zoho_oauth_client_secret: str = ""
    zoho_oauth_redirect_uri: str = ""

    # Email OAuth - Microsoft
    microsoft_oauth_client_id: str = ""
    microsoft_oauth_client_secret: str = ""
    microsoft_oauth_redirect_uri: str = ""
    microsoft_oauth_tenant_id: str = "common"

    # Microsoft Graph OAuth (reuses client ID/secret, separate redirect URI)
    microsoft_graph_redirect_uri: str = ""

    # Google Calendar OAuth
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = ""

    # Encryption (Fernet key — shared across email, polymarket, etc.)
    encryption_key: str = ""
    email_token_encryption_key: str = ""  # legacy alias, use ENCRYPTION_KEY instead

    # Email sync
    email_sync_interval_seconds: int = 300
    email_sync_queue_name: str = "email_sync"

    # Polymarket
    polymarket_clob_base_url: str = "https://clob.polymarket.com"
    polymarket_gamma_base_url: str = "https://gamma-api.polymarket.com"
    polymarket_chain_id: int = 137
    polymarket_queue_name: str = "trade_execution"

    # File serving (gateway workspace access)
    gateway_workspaces_root: str = (
        ""  # Parent dir for per-org gateways (e.g., /app/gateway-workspaces)
    )
    gateway_workspace_path: str = (
        ""  # DEPRECATED — legacy fallback, remove after compose mounts dropped
    )

    # Adobe PDF Services (platform-level fallback for BYOK)
    adobe_pdf_client_id: str = ""
    adobe_pdf_client_secret: str = ""

    # OpenRouter (for cost tracking)
    openrouter_api_key: str = ""
    openrouter_management_key: str = ""

    # OpenClaw gateway runtime compatibility
    gateway_min_version: str = "2026.02.9"

    # Logging
    log_level: str = "INFO"
    log_format: str = "text"
    log_use_utc: bool = False
    request_log_slow_ms: int = Field(default=1000, ge=0)
    request_log_include_health: bool = False

    @model_validator(mode="after")
    def _defaults(self) -> Self:
        if self.auth_mode == AuthMode.CLERK:
            if not self.clerk_secret_key.strip():
                raise ValueError(
                    "CLERK_SECRET_KEY must be set and non-empty when AUTH_MODE=clerk.",
                )
        elif self.auth_mode == AuthMode.LOCAL:
            token = self.local_auth_token.strip()
            if (
                not token
                or len(token) < LOCAL_AUTH_TOKEN_MIN_LENGTH
                or token.lower() in LOCAL_AUTH_TOKEN_PLACEHOLDERS
            ):
                raise ValueError(
                    "LOCAL_AUTH_TOKEN must be at least 50 characters and non-placeholder when AUTH_MODE=local.",
                )
        elif self.auth_mode == AuthMode.WECHAT:
            if not self.wechat_corp_id.strip():
                raise ValueError(
                    "WECHAT_CORP_ID must be set when AUTH_MODE=wechat.",
                )
            if not self.wechat_app_secret.strip():
                raise ValueError(
                    "WECHAT_APP_SECRET must be set when AUTH_MODE=wechat.",
                )

        base_url = self.base_url.strip()
        if not base_url:
            raise ValueError("BASE_URL must be set and non-empty.")
        parsed_base_url = urlparse(base_url)
        if parsed_base_url.scheme not in {"http", "https"} or not parsed_base_url.netloc:
            raise ValueError(
                "BASE_URL must be an absolute http(s) URL (e.g. http://localhost:8000).",
            )
        self.base_url = base_url.rstrip("/")

        # Rate-limit: fall back to rq_redis_url if using redis backend
        # with no explicit rate-limit URL. If both are blank, fail fast
        # with a clear configuration error.
        if (
            self.rate_limit_backend == RateLimitBackend.REDIS
            and not self.rate_limit_redis_url.strip()
        ):
            fallback_url = self.rq_redis_url.strip()
            if not fallback_url:
                raise ValueError(
                    "RATE_LIMIT_REDIS_URL or RQ_REDIS_URL must be set and non-empty "
                    "when RATE_LIMIT_BACKEND=redis.",
                )
            self.rate_limit_redis_url = fallback_url

        # In dev, default to applying Alembic migrations at startup to avoid
        # schema drift (e.g. missing newly-added columns).
        if "db_auto_migrate" not in self.model_fields_set and self.environment == "dev":
            self.db_auto_migrate = True
        return self


settings = Settings()
