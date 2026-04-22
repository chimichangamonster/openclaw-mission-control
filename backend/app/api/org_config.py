"""Per-org configuration data API — cost codes, rates, equipment, service catalogs.

Agents call GET /{category} at runtime to fetch org-specific config.
Admins manage config via POST/PUT/DELETE.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import ORG_ACTOR_DEP, require_org_role
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.org_config import OrgConfigData
from app.models.organization_settings import OrganizationSettings
from app.services.industry_templates import get_template
from app.services.organizations import OrganizationContext

router = APIRouter(prefix="/org-config", tags=["org-config"])

_ADMIN_DEP = Depends(require_org_role("admin"))

# Generic fallback suggestions used when an org has no custom config AND no
# industry template. Kept intentionally vertical-agnostic.
_FALLBACK_CHAT_SUGGESTIONS: list[dict[str, str]] = [
    {"key": "check_email", "label": "Check my email", "prompt": "Check my email"},
    {"key": "weekly_summary", "label": "What's new this week?", "prompt": "What's new this week?"},
    {"key": "generate_report", "label": "Generate a report", "prompt": "Generate a report"},
    {"key": "draft_doc", "label": "Draft a document", "prompt": "Help me draft a document"},
]


@router.get("/chat-suggestions/resolved")
async def resolve_chat_suggestions(org_ctx: OrganizationContext = ORG_ACTOR_DEP) -> Any:
    """Resolve chat suggestions via cascade: org config > industry template > fallback.

    Returns ``{source: "org"|"template"|"fallback", suggestions: [{key, label, prompt}]}``.
    Empty-but-present org config counts as "org" source — an admin can explicitly
    blank the suggestions to opt out of template defaults.
    """
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        org_items_result = await session.execute(
            select(OrgConfigData)
            .where(
                OrgConfigData.organization_id == org_id,
                OrgConfigData.category == "chat_suggestions",
                OrgConfigData.is_active == True,  # noqa: E712
            )
            .order_by(OrgConfigData.sort_order)  # type: ignore[arg-type]
        )
        org_items = org_items_result.scalars().all()

        # Layer 1: any org-configured suggestions win
        if org_items:
            return {
                "source": "org",
                "suggestions": [_suggestion_from_config(item) for item in org_items],
            }

        # Layer 2: industry template defaults
        settings_result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = settings_result.scalars().first()
        template_id = settings.industry_template_id if settings else None

        if template_id:
            template = get_template(template_id)
            if template:
                tmpl_items = template.default_config.get("chat_suggestions", [])
                if tmpl_items:
                    return {
                        "source": "template",
                        "template_id": template_id,
                        "suggestions": [
                            {
                                "key": item.key,
                                "label": item.label,
                                "prompt": item.value.get("prompt", item.label),
                            }
                            for item in tmpl_items
                        ],
                    }

        # Layer 3: generic fallback
        return {"source": "fallback", "suggestions": list(_FALLBACK_CHAT_SUGGESTIONS)}


def _suggestion_from_config(item: OrgConfigData) -> dict[str, str]:
    """Flatten an OrgConfigData chat_suggestions row into {key, label, prompt}.

    Falls back to ``label`` as the prompt if ``value.prompt`` is missing — lets
    an admin add quick-and-dirty suggestions without the value JSON shape.
    """
    value = item.value or {}
    prompt = value.get("prompt") if isinstance(value, dict) else None
    return {
        "key": item.key,
        "label": item.label,
        "prompt": prompt or item.label,
    }


class ConfigItemCreate(BaseModel):
    key: str
    label: str
    value: dict[str, Any] = {}
    sort_order: int = 0


class ConfigItemUpdate(BaseModel):
    label: str | None = None
    value: dict[str, Any] | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class BulkUpsert(BaseModel):
    category: str
    items: list[ConfigItemCreate]


@router.get("/{category}")
async def list_config(category: str, org_ctx: OrganizationContext = ORG_ACTOR_DEP) -> Any:
    """List all active config items for a category. This is what skills call at runtime."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(OrgConfigData)
            .where(
                OrgConfigData.organization_id == org_ctx.organization.id,
                OrgConfigData.category == category,
                OrgConfigData.is_active == True,  # noqa: E712
            )
            .order_by(OrgConfigData.sort_order)  # type: ignore[arg-type]
        )
        return [_serialize(item) for item in result.scalars().all()]


@router.get("/{category}/{key}")
async def get_config_item(
    category: str, key: str, org_ctx: OrganizationContext = ORG_ACTOR_DEP
) -> Any:
    """Get a single config item."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(OrgConfigData).where(
                OrgConfigData.organization_id == org_ctx.organization.id,
                OrgConfigData.category == category,
                OrgConfigData.key == key,
            )
        )
        item = result.scalars().first()
        if not item:
            raise HTTPException(status_code=404, detail=f"Config item '{category}/{key}' not found")
        return _serialize(item)


@router.post("/{category}", status_code=201)
async def create_config_item(
    category: str,
    payload: ConfigItemCreate,
    org_ctx: OrganizationContext = _ADMIN_DEP,
) -> Any:
    """Create a config item. Requires admin role."""
    async with async_session_maker() as session:
        # Check for duplicate
        existing = await session.execute(
            select(OrgConfigData).where(
                OrgConfigData.organization_id == org_ctx.organization.id,
                OrgConfigData.category == category,
                OrgConfigData.key == payload.key,
            )
        )
        if existing.scalars().first():
            raise HTTPException(
                status_code=409, detail=f"Config item '{category}/{payload.key}' already exists"
            )

        item = OrgConfigData(
            id=uuid4(),
            organization_id=org_ctx.organization.id,
            category=category,
            key=payload.key,
            label=payload.label,
            value_json=json.dumps(payload.value),
            sort_order=payload.sort_order,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return _serialize(item)


@router.put("/{category}/{key}")
async def update_config_item(
    category: str,
    key: str,
    payload: ConfigItemUpdate,
    org_ctx: OrganizationContext = _ADMIN_DEP,
) -> Any:
    """Update a config item. Requires admin role."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(OrgConfigData).where(
                OrgConfigData.organization_id == org_ctx.organization.id,
                OrgConfigData.category == category,
                OrgConfigData.key == key,
            )
        )
        item = result.scalars().first()
        if not item:
            raise HTTPException(status_code=404, detail=f"Config item '{category}/{key}' not found")

        if payload.label is not None:
            item.label = payload.label
        if payload.value is not None:
            item.value_json = json.dumps(payload.value)
        if payload.sort_order is not None:
            item.sort_order = payload.sort_order
        if payload.is_active is not None:
            item.is_active = payload.is_active
        item.updated_at = utcnow()
        await session.commit()
        await session.refresh(item)
        return _serialize(item)


@router.delete("/{category}/{key}")
async def deactivate_config_item(
    category: str,
    key: str,
    org_ctx: OrganizationContext = _ADMIN_DEP,
) -> Any:
    """Deactivate a config item (soft delete). Requires admin role."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(OrgConfigData).where(
                OrgConfigData.organization_id == org_ctx.organization.id,
                OrgConfigData.category == category,
                OrgConfigData.key == key,
            )
        )
        item = result.scalars().first()
        if not item:
            raise HTTPException(status_code=404, detail=f"Config item '{category}/{key}' not found")

        item.is_active = False
        item.updated_at = utcnow()
        await session.commit()
        return {"ok": True}


@router.post("/bulk", status_code=201)
async def bulk_upsert(
    payload: BulkUpsert,
    org_ctx: OrganizationContext = _ADMIN_DEP,
) -> Any:
    """Bulk upsert config items for a category. Skips existing keys. Used during template application."""
    org_id = org_ctx.organization.id
    created = 0

    async with async_session_maker() as session:
        for item in payload.items:
            existing = await session.execute(
                select(OrgConfigData).where(
                    OrgConfigData.organization_id == org_id,
                    OrgConfigData.category == payload.category,
                    OrgConfigData.key == item.key,
                )
            )
            if existing.scalars().first():
                continue  # skip existing

            session.add(
                OrgConfigData(
                    id=uuid4(),
                    organization_id=org_id,
                    category=payload.category,
                    key=item.key,
                    label=item.label,
                    value_json=json.dumps(item.value),
                    sort_order=item.sort_order,
                    created_at=utcnow(),
                    updated_at=utcnow(),
                )
            )
            created += 1

        await session.commit()

    return {"ok": True, "created": created, "skipped": len(payload.items) - created}


def _serialize(item: OrgConfigData) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "category": item.category,
        "key": item.key,
        "label": item.label,
        "value": item.value,
        "sort_order": item.sort_order,
        "is_active": item.is_active,
    }
