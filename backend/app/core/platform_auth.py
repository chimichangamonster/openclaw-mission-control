"""Platform-level authorization for multi-tenant administration.

Separates platform access into two roles:

- **owner**: Full access to all orgs and their data (Henz). Can read emails,
  chat history, API keys, org settings across all tenants.
- **operator**: Infrastructure management only. Can restart gateways, check
  health, view org metadata (name, slug, feature flags). CANNOT read client
  emails, chat history, decrypted API keys, or org-specific content.

Regular users (platform_role=None) have no cross-org access at all.

Every cross-org access by a platform admin is audit-logged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, status

from app.core.auth import AuthContext, get_auth_context
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.models.users import User

logger = get_logger(__name__)

PLATFORM_OWNER = "owner"
PLATFORM_OPERATOR = "operator"
PLATFORM_ROLES = {PLATFORM_OWNER, PLATFORM_OPERATOR}

# Data categories that operators CANNOT access
OPERATOR_RESTRICTED_DATA = {
    "email_content",
    "chat_history",
    "api_keys_decrypted",
    "org_settings_secrets",
    "file_contents",
    "calendar_events",
    "contact_details",
    "wecom_messages",
}


def _get_platform_role(user: User | None) -> str | None:
    """Get the platform role for a user, if any."""
    if user is None:
        return None
    return getattr(user, "platform_role", None)


async def require_platform_admin(
    auth: AuthContext = Depends(get_auth_context),
) -> User:
    """Require any platform admin role (owner or operator).

    Use this for infrastructure endpoints that both roles can access.
    """
    if auth.user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    role = _get_platform_role(auth.user)
    if role not in PLATFORM_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin access required.",
        )

    logger.info(
        "platform.access user=%s role=%s",
        auth.user.email,
        role,
    )
    return auth.user


async def require_platform_owner(
    auth: AuthContext = Depends(get_auth_context),
) -> User:
    """Require platform owner role.

    Use this for endpoints that access client-sensitive data
    (emails, chat, API keys, org settings).
    """
    if auth.user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    role = _get_platform_role(auth.user)
    if role != PLATFORM_OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform owner access required. Operators cannot access client data.",
        )

    logger.info(
        "platform.owner_access user=%s",
        auth.user.email,
    )
    return auth.user


def check_operator_data_access(user: User, data_category: str) -> None:
    """Check if a platform user can access a specific data category.

    Raises HTTPException if an operator tries to access restricted data.
    """
    role = _get_platform_role(user)
    if role == PLATFORM_OPERATOR and data_category in OPERATOR_RESTRICTED_DATA:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Platform operators cannot access {data_category}. Contact the platform owner.",
        )
