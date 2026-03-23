"""Organization settings API — BYOK keys, feature flags, branding, logo upload."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import require_org_member, require_org_role
from app.core.config import settings as app_settings
from app.core.encryption import encrypt_token, decrypt_token
from app.core.file_tokens import create_file_token
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.organization_settings import OrganizationSettings
from app.services.audit import log_audit
from app.services.organizations import OrganizationContext

logger = get_logger(__name__)
router = APIRouter(prefix="/organization-settings", tags=["organization-settings"])

# Admin-level dependency for write operations
_ADMIN_DEP = Depends(require_org_role("admin"))

_LOGO_MAX_SIZE = 5 * 1024 * 1024  # 5 MB
_LOGO_ALLOWED_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
}


def _mask_key(key: str | None) -> str | None:
    """Mask an API key for display, showing only last 4 chars."""
    if not key:
        return None
    if len(key) <= 8:
        return "****"
    return f"{'*' * (len(key) - 4)}{key[-4:]}"


@router.get("/feature-flags")
async def get_feature_flags(
    org_ctx: OrganizationContext = Depends(require_org_member),
):
    """Get feature flags for the current organization (lightweight)."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

    if not settings:
        settings = OrganizationSettings(organization_id=org_id)

    return {"feature_flags": settings.feature_flags}


@router.get("")
async def get_settings(
    org_ctx: OrganizationContext = Depends(require_org_member),
):
    """Get organization settings. API keys are masked."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

    if not settings:
        settings = OrganizationSettings(organization_id=org_id)

    # Decrypt and mask keys for display
    or_key = None
    if settings.openrouter_api_key_encrypted:
        try:
            or_key = _mask_key(decrypt_token(settings.openrouter_api_key_encrypted))
        except Exception:
            or_key = "(invalid)"

    mgmt_key = None
    if settings.openrouter_management_key_encrypted:
        try:
            mgmt_key = _mask_key(decrypt_token(settings.openrouter_management_key_encrypted))
        except Exception:
            mgmt_key = "(invalid)"

    # Adobe PDF Services
    adobe_id = None
    if settings.adobe_pdf_client_id_encrypted:
        try:
            adobe_id = _mask_key(decrypt_token(settings.adobe_pdf_client_id_encrypted))
        except Exception:
            adobe_id = "(invalid)"

    # Logo URL
    branding = settings.branding
    logo_url = None
    if branding.get("logo_path"):
        logo_url = f"{app_settings.base_url}/api/v1/files/download?token={create_file_token(branding['logo_path'], expires_hours=168)}"

    return {
        "openrouter_api_key": or_key,
        "has_openrouter_key": settings.openrouter_api_key_encrypted is not None,
        "openrouter_management_key": mgmt_key,
        "has_management_key": settings.openrouter_management_key_encrypted is not None,
        "adobe_pdf_client_id": adobe_id,
        "has_adobe_pdf_key": settings.adobe_pdf_client_id_encrypted is not None,
        "default_model_tier_max": settings.default_model_tier_max,
        "configured_models": settings.configured_models,
        "feature_flags": settings.feature_flags,
        "agent_defaults": settings.agent_defaults,
        "branding": branding,
        "logo_url": logo_url,
        "has_logo": branding.get("logo_path") is not None,
        # Custom LLM endpoint
        "has_custom_llm_endpoint": bool(settings.custom_llm_endpoint.get("api_url")),
        "custom_llm_endpoint_name": settings.custom_llm_endpoint.get("name"),
        "custom_llm_endpoint_url": settings.custom_llm_endpoint.get("api_url"),
        # Data policy
        "data_policy": settings.data_policy,
        # Timezone and location
        "timezone": settings.timezone,
        "location": settings.location,
        # Caller's role context
        "member_role": org_ctx.member.role,
        "is_admin": org_ctx.member.role in {"admin", "owner"},
    }


class DataPolicyUpdate(BaseModel):
    redaction_level: str | None = None  # "off", "moderate", "strict"
    allow_email_content_to_llm: bool | None = None
    log_llm_inputs: bool | None = None


class SettingsUpdate(BaseModel):
    default_model_tier_max: int | None = None
    configured_models: list[str] | None = None
    feature_flags: dict[str, bool] | None = None
    agent_defaults: dict | None = None
    branding: dict | None = None
    data_policy: DataPolicyUpdate | None = None
    timezone: str | None = None
    location: str | None = None


@router.put("")
async def update_settings(
    payload: SettingsUpdate,
    org_ctx: OrganizationContext = _ADMIN_DEP,
):
    """Update organization settings (non-key fields). Requires admin role."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

        if not settings:
            settings = OrganizationSettings(id=uuid4(), organization_id=org_id, created_at=utcnow(), updated_at=utcnow())
            session.add(settings)

        changes = {}
        if payload.default_model_tier_max is not None:
            changes["default_model_tier_max"] = {"old": settings.default_model_tier_max, "new": payload.default_model_tier_max}
            settings.default_model_tier_max = payload.default_model_tier_max
        if payload.configured_models is not None:
            settings.configured_models_json = json.dumps(payload.configured_models)
            changes["configured_models"] = True
        if payload.feature_flags is not None:
            settings.feature_flags_json = json.dumps(payload.feature_flags)
            changes["feature_flags"] = True
        if payload.agent_defaults is not None:
            settings.agent_defaults_json = json.dumps(payload.agent_defaults)
            changes["agent_defaults"] = True
        if payload.branding is not None:
            settings.branding_json = json.dumps(payload.branding)
            changes["branding"] = True
        if payload.data_policy is not None:
            valid_levels = {"off", "moderate", "strict"}
            current = settings.data_policy
            if payload.data_policy.redaction_level is not None:
                if payload.data_policy.redaction_level not in valid_levels:
                    raise HTTPException(status_code=400, detail=f"redaction_level must be one of: {', '.join(valid_levels)}")
                current["redaction_level"] = payload.data_policy.redaction_level
            if payload.data_policy.allow_email_content_to_llm is not None:
                current["allow_email_content_to_llm"] = payload.data_policy.allow_email_content_to_llm
            if payload.data_policy.log_llm_inputs is not None:
                current["log_llm_inputs"] = payload.data_policy.log_llm_inputs
            settings.data_policy_json = json.dumps(current)
            changes["data_policy"] = True
        if payload.timezone is not None:
            changes["timezone"] = {"old": settings.timezone, "new": payload.timezone}
            settings.timezone = payload.timezone
        if payload.location is not None:
            changes["location"] = {"old": settings.location, "new": payload.location}
            settings.location = payload.location

        settings.updated_at = utcnow()
        await session.commit()

    await log_audit(
        org_id, "settings.update",
        user_id=org_ctx.member.user_id,
        resource_type="organization_settings",
        details={"changed_fields": list(changes.keys())},
    )

    return {"ok": True}


class KeyPayload(BaseModel):
    key: str


# Prefixes that indicate personal-plan OAuth tokens, not API keys.
_OAUTH_PREFIXES = ("sk-ant-sid", "sess-", "eyJhbG")


@router.post("/openrouter-key")
async def set_openrouter_key(
    payload: KeyPayload,
    org_ctx: OrganizationContext = _ADMIN_DEP,
):
    """Store a BYOK OpenRouter API key (Fernet-encrypted). Requires admin role."""
    key = payload.key.strip()

    # Block keys that look like personal-plan OAuth tokens
    for prefix in _OAUTH_PREFIXES:
        if key.startswith(prefix):
            raise HTTPException(
                status_code=422,
                detail=(
                    "This looks like a personal-plan OAuth token, not an API key. "
                    "Provider Terms of Service prohibit routing personal subscriptions "
                    "(Claude Pro/Max, ChatGPT Plus) through third-party platforms. "
                    "Use an API key from openrouter.ai or the provider's developer console."
                ),
            )

    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

        if not settings:
            settings = OrganizationSettings(id=uuid4(), organization_id=org_id, created_at=utcnow(), updated_at=utcnow())
            session.add(settings)

        settings.openrouter_api_key_encrypted = encrypt_token(key)
        settings.updated_at = utcnow()
        await session.commit()

    await log_audit(
        org_id, "key.set",
        user_id=org_ctx.member.user_id,
        resource_type="organization_settings",
        details={"key_type": "openrouter_api_key"},
    )

    return {"ok": True}


@router.delete("/openrouter-key")
async def remove_openrouter_key(
    org_ctx: OrganizationContext = _ADMIN_DEP,
):
    """Remove BYOK OpenRouter key. Requires admin role."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

        if settings and settings.openrouter_api_key_encrypted:
            settings.openrouter_api_key_encrypted = None
            settings.updated_at = utcnow()
            await session.commit()

    await log_audit(
        org_id, "key.remove",
        user_id=org_ctx.member.user_id,
        resource_type="organization_settings",
        details={"key_type": "openrouter_api_key"},
    )

    return {"ok": True}


@router.post("/management-key")
async def set_management_key(
    payload: KeyPayload,
    org_ctx: OrganizationContext = _ADMIN_DEP,
):
    """Store a BYOK OpenRouter management key. Requires admin role."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

        if not settings:
            settings = OrganizationSettings(id=uuid4(), organization_id=org_id, created_at=utcnow(), updated_at=utcnow())
            session.add(settings)

        settings.openrouter_management_key_encrypted = encrypt_token(payload.key)
        settings.updated_at = utcnow()
        await session.commit()

    await log_audit(
        org_id, "key.set",
        user_id=org_ctx.member.user_id,
        resource_type="organization_settings",
        details={"key_type": "openrouter_management_key"},
    )

    return {"ok": True}


@router.delete("/management-key")
async def remove_management_key(
    org_ctx: OrganizationContext = _ADMIN_DEP,
):
    """Remove BYOK management key. Requires admin role."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

        if settings and settings.openrouter_management_key_encrypted:
            settings.openrouter_management_key_encrypted = None
            settings.updated_at = utcnow()
            await session.commit()

    await log_audit(
        org_id, "key.remove",
        user_id=org_ctx.member.user_id,
        resource_type="organization_settings",
        details={"key_type": "openrouter_management_key"},
    )

    return {"ok": True}


class AdobeKeyPayload(BaseModel):
    client_id: str
    client_secret: str


@router.post("/adobe-pdf-key")
async def set_adobe_pdf_key(
    payload: AdobeKeyPayload,
    org_ctx: OrganizationContext = _ADMIN_DEP,
):
    """Store BYOK Adobe PDF Services credentials. Requires admin role."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

        if not settings:
            settings = OrganizationSettings(id=uuid4(), organization_id=org_id, created_at=utcnow(), updated_at=utcnow())
            session.add(settings)

        settings.adobe_pdf_client_id_encrypted = encrypt_token(payload.client_id)
        settings.adobe_pdf_client_secret_encrypted = encrypt_token(payload.client_secret)
        settings.updated_at = utcnow()
        await session.commit()

    await log_audit(
        org_id, "key.set",
        user_id=org_ctx.member.user_id,
        resource_type="organization_settings",
        details={"key_type": "adobe_pdf_services"},
    )

    return {"ok": True}


@router.delete("/adobe-pdf-key")
async def remove_adobe_pdf_key(
    org_ctx: OrganizationContext = _ADMIN_DEP,
):
    """Remove BYOK Adobe PDF Services credentials. Requires admin role."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

        if settings:
            settings.adobe_pdf_client_id_encrypted = None
            settings.adobe_pdf_client_secret_encrypted = None
            settings.updated_at = utcnow()
            await session.commit()

    await log_audit(
        org_id, "key.remove",
        user_id=org_ctx.member.user_id,
        resource_type="organization_settings",
        details={"key_type": "adobe_pdf_services"},
    )

    return {"ok": True}


@router.post("/logo")
async def upload_logo(
    file: UploadFile,
    org_ctx: OrganizationContext = _ADMIN_DEP,
):
    """Upload an organization logo. Requires admin role."""
    org_id = org_ctx.organization.id

    # Validate file type
    content_type = file.content_type or ""
    ext = _LOGO_ALLOWED_TYPES.get(content_type)
    if not ext:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {content_type}. Allowed: PNG, JPG, SVG, WebP.",
        )

    # Read and validate size
    data = await file.read()
    if len(data) > _LOGO_MAX_SIZE:
        raise HTTPException(status_code=413, detail=f"Logo too large ({len(data)} bytes, max {_LOGO_MAX_SIZE}).")

    # Save to workspace: orgs/{org_id}/logo.{ext}
    workspace = app_settings.gateway_workspace_path
    if not workspace:
        raise HTTPException(status_code=503, detail="File storage not configured.")

    org_dir = Path(workspace) / "orgs" / str(org_id)
    org_dir.mkdir(parents=True, exist_ok=True)

    # Remove any existing logo files
    for old in org_dir.glob("logo.*"):
        old.unlink()

    logo_path = org_dir / f"logo{ext}"
    logo_path.write_bytes(data)
    relative_path = f"orgs/{org_id}/logo{ext}"

    # Update branding_json with logo_path
    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

        if not settings:
            settings = OrganizationSettings(id=uuid4(), organization_id=org_id, created_at=utcnow(), updated_at=utcnow())
            session.add(settings)

        branding = settings.branding
        branding["logo_path"] = relative_path
        settings.branding_json = json.dumps(branding)
        settings.updated_at = utcnow()
        await session.commit()

    await log_audit(
        org_id, "branding.logo_uploaded",
        user_id=org_ctx.member.user_id,
        resource_type="organization_settings",
        details={"filename": file.filename, "size": len(data), "content_type": content_type},
    )

    logo_url = f"{app_settings.base_url}/api/v1/files/download?token={create_file_token(relative_path, expires_hours=168)}"
    logger.info("org_settings.logo_uploaded org_id=%s size=%d", org_id, len(data))
    return {"ok": True, "logo_url": logo_url}


@router.delete("/logo")
async def remove_logo(
    org_ctx: OrganizationContext = _ADMIN_DEP,
):
    """Remove the organization logo. Requires admin role."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

        if settings:
            branding = settings.branding
            logo_path = branding.pop("logo_path", None)
            settings.branding_json = json.dumps(branding)
            settings.updated_at = utcnow()
            await session.commit()

            # Delete file from disk
            if logo_path and app_settings.gateway_workspace_path:
                full_path = Path(app_settings.gateway_workspace_path) / logo_path
                if full_path.is_file():
                    full_path.unlink()

    await log_audit(
        org_id, "branding.logo_removed",
        user_id=org_ctx.member.user_id,
        resource_type="organization_settings",
        details={},
    )

    return {"ok": True}


class CustomLLMEndpointPayload(BaseModel):
    api_url: str
    api_key: str
    name: str = "Custom LLM"
    models: list[str] = []


@router.post("/custom-llm-endpoint")
async def set_custom_llm_endpoint(
    payload: CustomLLMEndpointPayload,
    org_ctx: OrganizationContext = _ADMIN_DEP,
):
    """Configure a custom LLM endpoint (enterprise self-hosted). Requires admin role."""
    org_id = org_ctx.organization.id

    # Validate URL format
    if not payload.api_url.startswith("http"):
        raise HTTPException(status_code=400, detail="api_url must start with http:// or https://")

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

        if not settings:
            settings = OrganizationSettings(id=uuid4(), organization_id=org_id, created_at=utcnow(), updated_at=utcnow())
            session.add(settings)

        import json as json_mod
        settings.custom_llm_endpoint_json = json_mod.dumps({
            "api_url": payload.api_url.rstrip("/"),
            "name": payload.name,
            "models": payload.models,
        })
        settings.custom_llm_api_key_encrypted = encrypt_token(payload.api_key)
        settings.updated_at = utcnow()
        await session.commit()

    await log_audit(
        org_id, "key.set",
        user_id=org_ctx.member.user_id,
        resource_type="organization_settings",
        details={"key_type": "custom_llm_endpoint", "endpoint_name": payload.name},
    )

    logger.info("org_settings.custom_llm_set org_id=%s url=%s", org_id, payload.api_url)
    return {"ok": True}


@router.delete("/custom-llm-endpoint")
async def remove_custom_llm_endpoint(
    org_ctx: OrganizationContext = _ADMIN_DEP,
):
    """Remove custom LLM endpoint, reverting to OpenRouter. Requires admin role."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

        if settings:
            settings.custom_llm_endpoint_json = "{}"
            settings.custom_llm_api_key_encrypted = None
            settings.updated_at = utcnow()
            await session.commit()

    await log_audit(
        org_id, "key.remove",
        user_id=org_ctx.member.user_id,
        resource_type="organization_settings",
        details={"key_type": "custom_llm_endpoint"},
    )

    return {"ok": True}


@router.post("/custom-llm-endpoint/health")
async def check_custom_llm_health(
    org_ctx: OrganizationContext = _ADMIN_DEP,
):
    """Health check the configured custom LLM endpoint. Requires admin role."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()

    if not settings:
        raise HTTPException(status_code=404, detail="No organization settings found.")

    endpoint_config = settings.custom_llm_endpoint
    if not endpoint_config.get("api_url"):
        raise HTTPException(status_code=404, detail="No custom LLM endpoint configured.")

    api_key = ""
    if settings.custom_llm_api_key_encrypted:
        try:
            api_key = decrypt_token(settings.custom_llm_api_key_encrypted)
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to decrypt endpoint API key.")

    from app.services.llm_routing import check_endpoint_health

    health = await check_endpoint_health(endpoint_config["api_url"], api_key)
    return {
        "endpoint": endpoint_config["api_url"],
        "name": endpoint_config.get("name", "Custom LLM"),
        **health,
    }


@router.get("/llm-routing")
async def get_llm_routing_info(
    org_ctx: OrganizationContext = Depends(require_org_member),
):
    """Get the current LLM routing configuration for this org."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        from app.services.llm_routing import resolve_llm_endpoint

        endpoint = await resolve_llm_endpoint(session, org_id)

    if endpoint is None:
        return {
            "configured": False,
            "source": None,
            "message": "No LLM endpoint configured. Add an OpenRouter API key or custom endpoint in org settings.",
        }

    return {
        "configured": True,
        "source": endpoint.source,
        "name": endpoint.name,
        "api_url": endpoint.api_url if endpoint.source == "custom" else "openrouter.ai",
        "is_openrouter": endpoint.is_openrouter,
        "models": endpoint.models,
        "data_stays_private": not endpoint.is_openrouter,
    }


@router.get("/audit-log")
async def get_audit_log(
    org_ctx: OrganizationContext = Depends(require_org_member),
    limit: int = 50,
):
    """Get recent audit log entries for the organization."""
    from app.models.audit_log import AuditLog

    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(AuditLog)
            .where(AuditLog.organization_id == org_id)
            .order_by(AuditLog.created_at.desc())  # type: ignore[union-attr]
            .limit(limit)
        )
        rows = result.scalars().all()

    return {
        "entries": [
            {
                "id": str(r.id),
                "action": r.action,
                "resource_type": r.resource_type,
                "resource_id": str(r.resource_id) if r.resource_id else None,
                "details": r.details,
                "user_id": str(r.user_id) if r.user_id else None,
                "ip_address": r.ip_address,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }
