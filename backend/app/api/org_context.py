"""Org-Context Files API — admin-gated CRUD over org-scoped reference docs.

Phase 1 covers metadata CRUD. Phase 2 will replace the ``POST /org-context``
stub with a multipart upload that runs document_intake → redact_sensitive →
embedding before persisting, and add ``POST /agent/org-context/search``.

Audit logging covers create / delete / visibility-change so platform admins
can trace org-context provenance independent of the request log.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import (
    ORG_MEMBER_DEP,
    ORG_RATE_LIMIT_DEP,
    require_feature,
    require_org_role,
)
from app.core.logging import get_logger
from app.core.redact import RedactionLevel, redact_sensitive
from app.core.time import utcnow
from app.db.session import get_session
from app.models.org_context import OrgContextFile
from app.schemas.org_context import (
    VISIBILITY_VALUES,
    OrgContextFileDetail,
    OrgContextFileRead,
    OrgContextFileUpdate,
)
from app.services.document_intake import process_document
from app.services.embedding import get_embedding
from app.services.organizations import OrganizationContext

logger = get_logger(__name__)

router = APIRouter(
    prefix="/org-context",
    tags=["org-context"],
    dependencies=[
        Depends(require_feature("org_context")),
        ORG_RATE_LIMIT_DEP,
    ],
)

SESSION_DEP = Depends(get_session)
ADMIN_DEP = Depends(require_org_role("admin"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_visibility(value: str) -> str:
    if value not in VISIBILITY_VALUES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"visibility must be one of {sorted(VISIBILITY_VALUES)}",
        )
    return value


def _age_days(uploaded_at: datetime) -> int:
    """Days since upload. Both ``utcnow()`` and SQLAlchemy-returned
    DateTime columns are naive UTC in this codebase (per app/core/time.py),
    so subtracting them directly is correct. Defensive fallback strips any
    tzinfo on the input in case a caller stuffs an aware datetime."""
    if uploaded_at.tzinfo is not None:
        uploaded_at = uploaded_at.replace(tzinfo=None)
    delta = utcnow() - uploaded_at
    return max(0, delta.days)


def _to_read(row: OrgContextFile) -> dict[str, Any]:
    """Project an OrgContextFile row into the API's Read shape."""
    return {
        "id": row.id,
        "filename": row.filename,
        "category": row.category,
        "content_type": row.content_type,
        "source": row.source,
        "visibility": row.visibility,
        "is_living_data": row.is_living_data,
        "uploaded_at": row.uploaded_at,
        "last_updated": row.last_updated,
        "has_embedding": row.embedding is not None,
        "age_days": _age_days(row.uploaded_at),
    }


def _can_view(row: OrgContextFile, ctx: OrganizationContext) -> bool:
    """Visibility check. Owner + admin see everything; members see only
    shared rows OR rows they uploaded. Mirrors the email-account model."""
    if row.visibility == "shared":
        return True
    if ctx.member.role in {"owner", "admin"}:
        return True
    return row.uploaded_by_user_id == ctx.member.user_id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[OrgContextFileRead])
async def list_files(
    org_ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
    category: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    """List org-context files. Members see shared files; owner/admin see all."""
    org_id = org_ctx.organization.id

    q = (
        select(OrgContextFile)
        .where(OrgContextFile.organization_id == org_id)
        .order_by(col(OrgContextFile.last_updated).desc())
        .offset(offset)
        .limit(limit)
    )
    if category:
        q = q.where(OrgContextFile.category == category)

    result = await session.execute(q)
    rows = result.scalars().all()

    return [_to_read(r) for r in rows if _can_view(r, org_ctx)]


@router.get("/stats")
async def stats(
    org_ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """Summary counts and bytes grouped by category. Used by the admin
    landing page's stats strip.

    ``total_bytes`` and ``bytes_by_category`` sum over rows with non-NULL
    ``size_bytes``. Pre-Session-4 rows had no size column, so they show up
    in counts but contribute 0 to the bytes total. ``files_with_unknown_size``
    surfaces this so the UI can flag "(some sizes unknown)" when relevant.
    """
    org_id = org_ctx.organization.id

    total_q = (
        select(func.count())
        .select_from(OrgContextFile)
        .where(OrgContextFile.organization_id == org_id)
    )
    total = (await session.execute(total_q)).scalar() or 0

    by_cat_q = (
        select(
            OrgContextFile.category,
            func.count().label("count"),
            func.coalesce(func.sum(OrgContextFile.size_bytes), 0).label("bytes"),
        )
        .where(OrgContextFile.organization_id == org_id)
        .group_by(OrgContextFile.category)
        .order_by(func.count().desc())
    )
    by_cat = [
        {"category": r[0], "count": r[1], "bytes": int(r[2])}
        for r in (await session.execute(by_cat_q)).all()
    ]

    total_bytes_q = (
        select(func.coalesce(func.sum(OrgContextFile.size_bytes), 0))
        .select_from(OrgContextFile)
        .where(OrgContextFile.organization_id == org_id)
    )
    total_bytes = (await session.execute(total_bytes_q)).scalar() or 0

    unknown_size_q = (
        select(func.count())
        .select_from(OrgContextFile)
        .where(
            OrgContextFile.organization_id == org_id,
            OrgContextFile.size_bytes.is_(None),  # type: ignore[union-attr]
        )
    )
    files_with_unknown_size = (await session.execute(unknown_size_q)).scalar() or 0

    return {
        "total": total,
        "by_category": by_cat,
        "total_bytes": int(total_bytes),
        "files_with_unknown_size": files_with_unknown_size,
    }


@router.get("/{file_id}", response_model=OrgContextFileDetail)
async def get_file(
    file_id: UUID,
    org_ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """Fetch one file with its redacted extracted text."""
    row = await session.get(OrgContextFile, file_id)
    if not row or row.organization_id != org_ctx.organization.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Org-context file not found.",
        )
    if not _can_view(row, org_ctx):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Org-context file not found.",
        )

    payload = _to_read(row)
    payload["extracted_text"] = row.extracted_text
    return payload


MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB — mirrors document_intake limit
ALLOWED_UPLOAD_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "text/plain",
    "text/csv",
    "text/markdown",
    "application/json",
}


# ---------------------------------------------------------------------------
# Per-category redaction policy (Option C)
# ---------------------------------------------------------------------------
#
# STRICT also strips PII patterns (phones, emails-in-body, DOB, addresses).
# MODERATE keeps those — appropriate for files where contact info IS the
# signal the agent needs to ground recommendations on (e.g. a prospects
# roster: "next move is calling Joe at 780-..." can't fire if the phone
# was redacted at intake).
#
# Default for unmapped/new categories is STRICT — fail-safe.
#
# Future extension hook (Option D, deferred): add a per-org
# ``org_context_redaction_overrides_json`` field on OrganizationSettings
# that maps category -> level for verticals that need to override these
# defaults. Industry templates can seed it. See
# ``project_org_context_redaction_strategy.md`` memory for the full
# extension plan.
_CATEGORY_REDACTION_LEVEL: dict[str, RedactionLevel] = {
    # Prospects, customers, deployments, pricing — contact info / vendor
    # names / quoted amounts are signal the agent needs.
    "prospects": RedactionLevel.MODERATE,
    "customers": RedactionLevel.MODERATE,
    "deployments": RedactionLevel.MODERATE,
    "pricing": RedactionLevel.MODERATE,
    # Static reference docs — should not contain operational PII; if any
    # is present treat it as accidental and strip.
    "regulations": RedactionLevel.STRICT,
    "brand": RedactionLevel.STRICT,
    "contracts": RedactionLevel.STRICT,
    "rules-of-engagement": RedactionLevel.STRICT,
    # Catchall — fail-safe to STRICT.
    "other": RedactionLevel.STRICT,
}


def _redaction_level_for(category: str) -> RedactionLevel:
    """Resolve the redaction level for a given category. Unknown
    categories fall through to STRICT (fail-safe default)."""
    return _CATEGORY_REDACTION_LEVEL.get(category, RedactionLevel.STRICT)


@router.post(
    "",
    response_model=OrgContextFileRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[ADMIN_DEP],
)
async def upload_file(
    file: UploadFile = File(...),
    category: str = Form(default="other"),
    source: str | None = Form(default=None),
    visibility: str = Form(default="shared"),
    is_living_data: bool = Form(default=True),
    org_ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """Multipart upload + intake pipeline.

    Pipeline (in order, all must succeed):
    1. Validate file type (PDF / image / text family) and size (<= 20 MB)
    2. Run document_intake.process_document → text extraction + sanitize
    3. Apply redact_sensitive(STRICT) — strips credentials/keys/financial/PII
       *before* the text is embedded or persisted. The redaction stage is
       load-bearing, not optional: agents and embeddings see only the
       redacted form, period.
    4. Generate embedding via OpenRouter (BYOK > platform key)
    5. Persist OrgContextFile with redacted text + embedding

    Failures at steps 2-4 surface as 422 with a diagnostic message —
    we do NOT silently store a row without text/embedding because the
    file would then be invisible to semantic search and confuse admins.
    """
    visibility = _ensure_visibility(visibility)

    # 1. Validate
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {content_type}",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File too large ({len(file_bytes) / 1024 / 1024:.1f} MB, "
                f"max {MAX_UPLOAD_SIZE // 1024 // 1024} MB)"
            ),
        )

    org_id = org_ctx.organization.id
    filename = file.filename or "unknown"

    # 2. Extract + sanitize
    intake = await process_document(
        file_bytes=file_bytes,
        filename=filename,
        content_type=content_type,
        org_id=org_id,
        db_session=session,
    )
    extracted = intake.get("extracted_text") or ""
    if not extracted.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Could not extract any text from this file. Scanned PDFs "
                "without OCR text and binary blobs aren't searchable."
            ),
        )

    # 3. Redact (load-bearing — strips credentials before LLM embedding).
    # Level is per-category (Option C) — see _CATEGORY_REDACTION_LEVEL
    # comment block above for the policy and rationale.
    redaction_level = _redaction_level_for(category or "other")
    redaction = redact_sensitive(extracted, redaction_level)
    redacted_text = redaction.text

    # 4. Embed
    try:
        embedding = await get_embedding(redacted_text, org_id)
    except Exception as exc:
        logger.warning(
            "org_context.embed_failed",
            extra={
                "organization_id": str(org_id),
                "file_name": filename,
                "error": str(exc),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Embedding failed: {exc}",
        ) from exc

    # 5. Persist
    row = OrgContextFile(
        organization_id=org_id,
        filename=filename,
        category=category or "other",
        content_type=content_type,
        source=source,
        visibility=visibility,
        is_living_data=is_living_data,
        extracted_text=redacted_text,
        embedding=embedding,
        size_bytes=len(file_bytes),
        uploaded_by_user_id=org_ctx.member.user_id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    logger.info(
        "org_context.uploaded",
        extra={
            "organization_id": str(org_id),
            "file_id": str(row.id),
            "file_name": filename,
            "category": row.category,
            "visibility": row.visibility,
            "redaction_level": redaction_level.value,
            "redaction_count": redaction.redaction_count,
            "redaction_categories": sorted(redaction.categories),
            "extracted_chars": len(redacted_text),
        },
    )
    return _to_read(row)


@router.patch(
    "/{file_id}",
    response_model=OrgContextFileRead,
    dependencies=[ADMIN_DEP],
)
async def update_file(
    file_id: UUID,
    body: OrgContextFileUpdate,
    org_ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> dict[str, Any]:
    """Mutate metadata fields (category / source / visibility / is_living_data)."""
    row = await session.get(OrgContextFile, file_id)
    if not row or row.organization_id != org_ctx.organization.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Org-context file not found.",
        )

    visibility_changed = False
    if body.category is not None:
        row.category = body.category
    if body.source is not None:
        row.source = body.source
    if body.visibility is not None:
        new_visibility = _ensure_visibility(body.visibility)
        visibility_changed = new_visibility != row.visibility
        row.visibility = new_visibility
    if body.is_living_data is not None:
        row.is_living_data = body.is_living_data

    row.last_updated = utcnow()
    session.add(row)
    await session.commit()
    await session.refresh(row)

    if visibility_changed:
        logger.info(
            "org_context.visibility_changed",
            extra={
                "organization_id": str(org_ctx.organization.id),
                "file_id": str(row.id),
                "visibility": row.visibility,
            },
        )

    return _to_read(row)


@router.delete(
    "/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[ADMIN_DEP],
)
async def delete_file(
    file_id: UUID,
    org_ctx: OrganizationContext = ORG_MEMBER_DEP,
    session: AsyncSession = SESSION_DEP,
) -> None:
    """Hard-delete a file and its embedding."""
    row = await session.get(OrgContextFile, file_id)
    if not row or row.organization_id != org_ctx.organization.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Org-context file not found.",
        )

    await session.delete(row)
    await session.commit()

    logger.info(
        "org_context.deleted",
        extra={
            "organization_id": str(org_ctx.organization.id),
            "file_id": str(file_id),
        },
    )
