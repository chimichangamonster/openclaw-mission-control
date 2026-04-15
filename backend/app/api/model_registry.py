"""Model registry API — browse models, refresh from OpenRouter, manage version pins."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import select

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import ORG_MEMBER_DEP, ORG_RATE_LIMIT_DEP, get_session, require_org_role
from app.core.logging import get_logger
from app.db.session import async_session_maker
from app.models.model_call_log import ModelCallLog
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
) -> dict[str, Any]:
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
) -> dict[str, Any]:
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
) -> dict[str, Any]:
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
) -> dict[str, Any]:
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
) -> dict[str, Any]:
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


# ---------------------------------------------------------------------------
# Benchmark endpoint — aggregates model_call_log for Phase 3c Step 3
# ---------------------------------------------------------------------------


def _percentile(values: list[int], pct: float) -> int:
    """Nearest-rank percentile over a list of integers. Returns 0 on empty."""
    if not values:
        return 0
    sorted_vals = sorted(values)
    # Clamp to [0, len-1]; nearest-rank style.
    idx = max(0, min(len(sorted_vals) - 1, int(len(sorted_vals) * pct) - 1))
    if idx < 0:
        idx = 0
    return int(sorted_vals[idx])


@router.get("/benchmark")
async def benchmark_models(
    ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = Depends(get_session),
    days: int = Query(default=1, ge=1, le=365),
    skill: str | None = Query(default=None),
) -> dict[str, Any]:
    """Aggregate model_call_log over the window and group by (model, skill_name).

    Returns per-(model, skill) reliability, latency, cost. Powers the
    model-benchmark skill and any ad-hoc analyst lookups. Deliberately does
    NOT scope by organization_id — model performance is a platform-level
    concern, and org-scoping would hide patterns (e.g. a model that fails only
    for one org's prompts). Callers who need org slicing can filter client-side
    or we'll add an ``?org_id`` param when a use case appears.
    """
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)

    stmt = select(
        ModelCallLog.model,
        ModelCallLog.skill_name,
        ModelCallLog.status,
        ModelCallLog.latency_ms,
        ModelCallLog.tokens_in,
        ModelCallLog.tokens_out,
        ModelCallLog.cost_usd,
    ).where(ModelCallLog.created_at >= cutoff)
    if skill:
        stmt = stmt.where(ModelCallLog.skill_name == skill)
    result = await session.execute(stmt)
    rows = result.all()

    # Group into buckets keyed by (model, skill_name).
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for model, skill_name, status_val, latency_ms, tokens_in, tokens_out, cost_usd in rows:
        key = (model, skill_name)
        b = buckets.setdefault(
            key,
            {
                "model": model,
                "skill_name": skill_name,
                "success_count": 0,
                "error_count": 0,
                "timeout_count": 0,
                "latencies": [],
                "tokens_in_sum": 0,
                "tokens_out_sum": 0,
                "cost_sum": 0.0,
            },
        )
        if status_val == "success":
            b["success_count"] += 1
        elif status_val == "timeout":
            b["timeout_count"] += 1
        else:
            b["error_count"] += 1
        if latency_ms is not None:
            b["latencies"].append(int(latency_ms))
        if tokens_in is not None:
            b["tokens_in_sum"] += int(tokens_in)
        if tokens_out is not None:
            b["tokens_out_sum"] += int(tokens_out)
        if cost_usd is not None:
            b["cost_sum"] += float(cost_usd)

    out_rows: list[dict[str, Any]] = []
    for b in buckets.values():
        total = b["success_count"] + b["error_count"] + b["timeout_count"]
        latencies: list[int] = b["latencies"]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        out_rows.append(
            {
                "model": b["model"],
                "skill_name": b["skill_name"],
                "total_calls": total,
                "success_count": b["success_count"],
                "error_count": b["error_count"],
                "timeout_count": b["timeout_count"],
                "success_rate": round(b["success_count"] / total, 4) if total else 0.0,
                "avg_latency_ms": round(avg_latency, 2),
                "p95_latency_ms": _percentile(latencies, 0.95),
                "total_tokens_in": b["tokens_in_sum"],
                "total_tokens_out": b["tokens_out_sum"],
                "total_cost_usd": round(b["cost_sum"], 6),
            }
        )

    # Sort deterministically: descending total_calls, then model, then skill.
    out_rows.sort(key=lambda r: (-r["total_calls"], r["model"], r["skill_name"]))

    return {
        "window_days": days,
        "skill_filter": skill,
        "generated_at": datetime.now(UTC).isoformat(),
        "rows": out_rows,
    }
