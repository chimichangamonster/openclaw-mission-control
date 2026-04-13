"""Observability endpoints — quality scoring, trace metadata, Langfuse proxy.

Gated by the ``observability`` feature flag. Admin role required for mutations.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import ORG_ACTOR_DEP, require_feature, require_org_role
from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.observability import QualityScoreCreate
from app.services.organizations import OrganizationContext

router = APIRouter(
    prefix="/observability",
    tags=["observability"],
    dependencies=[Depends(require_feature("observability"))],
)

logger = get_logger(__name__)

_ADMIN_DEP = Depends(require_org_role("admin"))


def _langfuse_auth() -> tuple[str, str]:
    """Return (public_key, secret_key) for Langfuse HTTP Basic auth."""
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Langfuse is not configured.",
        )
    return settings.langfuse_public_key, settings.langfuse_secret_key


@router.post("/score", dependencies=[_ADMIN_DEP])
async def submit_quality_score(
    body: QualityScoreCreate,
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> dict[str, Any]:
    """Submit a quality score for a Langfuse trace.

    Used by admins to attach human feedback (accuracy, helpfulness, relevance)
    to agent decisions for quality tracking.
    """
    from app.services.langfuse_client import get_langfuse, score_trace

    if not get_langfuse():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Langfuse is not configured. Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY.",
        )

    score_trace(
        trace_id=body.trace_id,
        name=body.name,
        value=body.value,
        comment=body.comment,
    )

    logger.info(
        "observability.score_submitted org_id=%s trace_id=%s name=%s value=%.2f",
        org_ctx.organization.id,
        body.trace_id,
        body.name,
        body.value,
    )

    return {
        "trace_id": body.trace_id,
        "name": body.name,
        "value": body.value,
        "status": "submitted",
    }


@router.get("/status")
async def observability_status(
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> dict[str, Any]:
    """Check whether Langfuse observability is configured and reachable."""
    from app.services.langfuse_client import get_langfuse

    client = get_langfuse()
    return {
        "configured": client is not None,
        "host": getattr(client, "base_url", None) if client else None,
    }


# ── Langfuse proxy endpoints ────────────────────────────────────────


@router.get("/traces")
async def list_traces(
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
    limit: int = Query(default=50, ge=1, le=200),
    page: int = Query(default=1, ge=1),
    name: str | None = Query(default=None),
) -> dict[str, Any]:
    """Proxy paginated trace list from Langfuse."""
    auth = _langfuse_auth()
    params: dict[str, Any] = {"limit": limit, "page": page}
    if name:
        params["name"] = name
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{settings.langfuse_host}/api/public/traces",
            params=params,
            auth=auth,
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Langfuse API error")
    return resp.json()


@router.get("/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
) -> dict[str, Any]:
    """Fetch a single trace with its observations and scores."""
    auth = _langfuse_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{settings.langfuse_host}/api/public/traces/{trace_id}",
            auth=auth,
        )
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Trace not found")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Langfuse API error")
    return resp.json()


@router.get("/scores")
async def list_scores(
    org_ctx: OrganizationContext = ORG_ACTOR_DEP,
    limit: int = Query(default=50, ge=1, le=200),
    page: int = Query(default=1, ge=1),
) -> dict[str, Any]:
    """Proxy paginated score list from Langfuse."""
    auth = _langfuse_auth()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{settings.langfuse_host}/api/public/scores",
            params={"limit": limit, "page": page},
            auth=auth,
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Langfuse API error")
    return resp.json()
