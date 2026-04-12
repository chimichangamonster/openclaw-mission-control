"""Observability endpoints — quality scoring, trace metadata.

Gated by the ``observability`` feature flag. Admin role required for mutations.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import ORG_ACTOR_DEP, require_feature, require_org_role
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
