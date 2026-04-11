"""BYOK OpenRouter API key resolution — per-org, no free credits.

Platform env key is only used as fallback for the FIRST org (platform owner).
All other orgs must provide their own key.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.core.encryption import decrypt_token
from app.models.organization_settings import OrganizationSettings
from app.models.organizations import Organization


async def _is_platform_owner(session: AsyncSession, org_id: UUID) -> bool:
    """Check if this org is the first (platform owner) org."""
    result = await session.execute(
        select(Organization.id).order_by(Organization.created_at).limit(1)  # type: ignore[arg-type]
    )
    first_org = result.scalar()
    return first_org == org_id


async def get_openrouter_key_for_org(session: AsyncSession, org_id: UUID) -> str | None:
    """Resolve the OpenRouter API key for an organization.

    Resolution order:
    1. Per-org BYOK key from OrganizationSettings (Fernet-encrypted)
    2. Platform env key — ONLY for the platform owner org (first org created)
    3. None — org must set their own key
    """
    result = await session.execute(
        select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
    )
    org_settings = result.scalars().first()

    if org_settings and org_settings.openrouter_api_key_encrypted:
        try:
            return decrypt_token(org_settings.openrouter_api_key_encrypted)
        except Exception:
            pass

    # Only fall back to platform key for the owner org
    if settings.openrouter_api_key and await _is_platform_owner(session, org_id):
        return settings.openrouter_api_key

    return None


async def get_management_key_for_org(session: AsyncSession, org_id: UUID) -> str | None:
    """Resolve the OpenRouter management key for an organization."""
    result = await session.execute(
        select(OrganizationSettings).where(OrganizationSettings.organization_id == org_id)
    )
    org_settings = result.scalars().first()

    if org_settings and org_settings.openrouter_management_key_encrypted:
        try:
            return decrypt_token(org_settings.openrouter_management_key_encrypted)
        except Exception:
            pass

    # Only fall back to platform key for the owner org
    mgmt_key = getattr(settings, "openrouter_management_key", None)
    if mgmt_key and await _is_platform_owner(session, org_id):
        return mgmt_key  # type: ignore[no-any-return]

    return None
