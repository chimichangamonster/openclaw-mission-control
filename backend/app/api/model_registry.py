"""Model registry API — browse models, refresh from OpenRouter, manage version pins."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import ORG_MEMBER_DEP, ORG_RATE_LIMIT_DEP, require_org_role
from app.core.logging import get_logger
from app.db.session import async_session_maker
from app.models.organization_settings import OrganizationSettings
from app.services.model_registry import get_registry
from app.services.organizations import OrganizationContext

logger = get_logger(__name__)

router = APIRouter(
    prefix="/models",
    tags=["models"],
    dependencies=[ORG_RATE_LIMIT_DEP],
)

_ADMIN_DEP = Depends(require_org_role("admin"))


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ModelPinsUpdate(BaseModel):
    pins: dict[str, str]  # e.g. {"primary": "anthropic/claude-sonnet-4-20260514"}


# ---------------------------------------------------------------------------
# Registry endpoints
# ---------------------------------------------------------------------------


@router.get("/registry")
async def list_models(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    status_filter: str | None = None,
) -> dict:
    """List all known models in the registry."""
    registry = get_registry()
    entries = registry.list_models(status=status_filter)
    return {
        "models": [asdict(e) for e in entries],
        "total": len(entries),
        "last_refresh": (
            datetime.fromtimestamp(registry.last_refresh, tz=UTC).isoformat()
            if registry.last_refresh
            else None
        ),
        "families": registry.list_families(),
    }


@router.post("/registry/refresh", dependencies=[_ADMIN_DEP])
async def refresh_registry(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> dict:
    """Trigger a refresh of the model registry from OpenRouter."""
    from app.services.openrouter_keys import get_openrouter_key_for_org

    async with async_session_maker() as session:
        api_key = await get_openrouter_key_for_org(session, ctx.organization.id)

    registry = get_registry()
    result = await registry.refresh(api_key=api_key)
    return {
        "total_models": result.total_models,
        "new_models": result.new_models,
        "deprecated_models": result.deprecated_models,
        "refresh_time_ms": result.refresh_time_ms,
    }


@router.get("/registry/{family:path}/versions")
async def get_family_versions(
    family: str,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> dict:
    """Get all versions of a model family."""
    registry = get_registry()
    versions = registry.get_family_versions(family)
    return {
        "family": family,
        "versions": [asdict(v) for v in versions],
    }


# ---------------------------------------------------------------------------
# Model pins endpoints
# ---------------------------------------------------------------------------


@router.get("/pins")
async def get_model_pins(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> dict:
    """Get the current model version pins for this organization."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(
                OrganizationSettings.organization_id == ctx.organization.id
            )
        )
        org_settings = result.scalars().first()

    pins = org_settings.model_pins if org_settings else {}

    # Check for deprecation warnings
    registry = get_registry()
    warnings = registry.check_pins(pins) if pins else []

    return {
        "pins": pins,
        "warnings": [asdict(w) for w in warnings],
    }


@router.put("/pins", dependencies=[_ADMIN_DEP])
async def update_model_pins(
    payload: ModelPinsUpdate,
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> dict:
    """Set model version pins for this organization.

    Validates that each pinned model ID exists in the registry.
    """
    registry = get_registry()

    # Validate pin values if registry is populated
    if registry.list_models():
        for pin_key, model_id in payload.pins.items():
            entry = registry.get_model(model_id)
            if entry is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Model '{model_id}' not found in registry. Refresh the registry first.",
                )

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrganizationSettings).where(
                OrganizationSettings.organization_id == ctx.organization.id
            )
        )
        org_settings = result.scalars().first()

        if not org_settings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization settings not found",
            )

        org_settings.model_pins_json = json.dumps(payload.pins)
        session.add(org_settings)
        await session.commit()

    # Audit log
    from app.services.audit import log_audit

    await log_audit(
        org_id=ctx.organization.id,
        action="settings.model_pins.update",
        user_id=ctx.member.user_id,
        details={"pins": payload.pins},
    )

    logger.info(
        "model_pins.updated",
        extra={"org_id": str(ctx.organization.id), "pins": payload.pins},
    )

    return {"ok": True, "pins": payload.pins}
