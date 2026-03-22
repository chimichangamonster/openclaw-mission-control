"""Industry templates API — list, apply, and track onboarding progress."""

from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from app.api.deps import ORG_MEMBER_DEP, require_org_role
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.org_config import OrgConfigData, OrgOnboardingStep
from app.models.organization_settings import OrganizationSettings
from app.services.audit import log_audit
from app.services.industry_templates import TEMPLATES, get_template, list_templates
from app.services.organizations import OrganizationContext

router = APIRouter(prefix="/industry-templates", tags=["industry-templates"])

_ADMIN_DEP = Depends(require_org_role("admin"))


@router.get("")
async def list_available_templates(org_ctx: OrganizationContext = ORG_MEMBER_DEP):
    """List all available industry templates."""
    return list_templates()


@router.get("/{template_id}")
async def get_template_detail(template_id: str, org_ctx: OrganizationContext = ORG_MEMBER_DEP):
    """Get full template details including default config and onboarding steps."""
    template = get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "icon": template.icon,
        "skills": template.skills,
        "feature_flags": template.feature_flags,
        "config_categories": {
            cat: [{"key": item.key, "label": item.label, "value": item.value} for item in items]
            for cat, items in template.default_config.items()
        },
        "onboarding_steps": [
            {"key": s.key, "label": s.label, "description": s.description, "sort_order": s.sort_order}
            for s in template.onboarding_steps
        ],
    }


@router.post("/{template_id}/apply")
async def apply_template(template_id: str, org_ctx: OrganizationContext = _ADMIN_DEP):
    """Apply an industry template to the current organization.

    Seeds default config data, merges feature flags, creates onboarding checklist.
    Skips config items that already exist (safe to re-apply).
    """
    template = get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        # 1. Update org settings: merge feature flags + set template ID
        result = await session.execute(
            select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
        )
        settings = result.scalars().first()
        if not settings:
            settings = OrganizationSettings(id=uuid4(), organization_id=org_id, created_at=utcnow(), updated_at=utcnow())
            session.add(settings)

        # Merge flags (template flags override, but don't disable existing enabled flags)
        current_flags = settings.feature_flags
        for flag, enabled in template.feature_flags.items():
            if enabled:
                current_flags[flag] = True
        settings.feature_flags_json = json.dumps(current_flags)
        settings.industry_template_id = template_id
        settings.updated_at = utcnow()

        # 2. Seed config data (skip existing)
        config_created = 0
        for category, items in template.default_config.items():
            for item in items:
                existing = await session.execute(
                    select(OrgConfigData).where(
                        OrgConfigData.organization_id == org_id,
                        OrgConfigData.category == category,
                        OrgConfigData.key == item.key,
                    )
                )
                if existing.scalars().first():
                    continue
                session.add(OrgConfigData(
                    id=uuid4(),
                    organization_id=org_id,
                    category=category,
                    key=item.key,
                    label=item.label,
                    value_json=json.dumps(item.value),
                    sort_order=items.index(item),
                    created_at=utcnow(),
                    updated_at=utcnow(),
                ))
                config_created += 1

        # 3. Create onboarding steps (replace existing for this template)
        await session.execute(
            select(OrgOnboardingStep).where(
                OrgOnboardingStep.organization_id == org_id,
                OrgOnboardingStep.template_id == template_id,
            )
        )
        # Delete old steps for this template if re-applying
        old_steps = (await session.execute(
            select(OrgOnboardingStep).where(
                OrgOnboardingStep.organization_id == org_id,
                OrgOnboardingStep.template_id == template_id,
            )
        )).scalars().all()
        for old in old_steps:
            await session.delete(old)

        for step in template.onboarding_steps:
            session.add(OrgOnboardingStep(
                id=uuid4(),
                organization_id=org_id,
                template_id=template_id,
                step_key=step.key,
                label=step.label,
                description=step.description,
                sort_order=step.sort_order,
                created_at=utcnow(),
            ))

        await session.commit()

    await log_audit(
        org_id, "template.applied",
        user_id=org_ctx.member.user_id,
        resource_type="industry_template",
        details={"template_id": template_id, "config_items_created": config_created},
    )

    return {
        "ok": True,
        "template_id": template_id,
        "template_name": template.name,
        "config_items_created": config_created,
        "onboarding_steps": len(template.onboarding_steps),
    }


@router.get("/onboarding/status")
async def get_onboarding_status(org_ctx: OrganizationContext = ORG_MEMBER_DEP):
    """Get onboarding checklist status for the current org."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrgOnboardingStep)
            .where(OrgOnboardingStep.organization_id == org_id)
            .order_by(OrgOnboardingStep.sort_order)
        )
        steps = result.scalars().all()

        if not steps:
            return {"template_id": None, "steps": [], "progress": 0}

        total = len(steps)
        completed = sum(1 for s in steps if s.completed)

        return {
            "template_id": steps[0].template_id,
            "steps": [
                {
                    "key": s.step_key,
                    "label": s.label,
                    "description": s.description,
                    "completed": s.completed,
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                }
                for s in steps
            ],
            "progress": round(completed / total * 100) if total else 0,
        }


@router.patch("/onboarding/{step_key}")
async def complete_onboarding_step(step_key: str, org_ctx: OrganizationContext = _ADMIN_DEP):
    """Mark an onboarding step as complete."""
    org_id = org_ctx.organization.id

    async with async_session_maker() as session:
        result = await session.execute(
            select(OrgOnboardingStep).where(
                OrgOnboardingStep.organization_id == org_id,
                OrgOnboardingStep.step_key == step_key,
            )
        )
        step = result.scalars().first()
        if not step:
            raise HTTPException(status_code=404, detail=f"Onboarding step '{step_key}' not found")

        step.completed = True
        step.completed_at = utcnow()
        await session.commit()

        return {"ok": True, "step_key": step_key, "completed": True}
