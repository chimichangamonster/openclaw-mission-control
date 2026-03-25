"""Authentication bootstrap endpoints for the Mission Control API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import AuthContext, get_auth_context
from app.core.config import settings
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.users import CURRENT_TERMS_VERSION
from app.schemas.errors import LLMErrorResponse
from app.schemas.users import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])
AUTH_CONTEXT_DEP = Depends(get_auth_context)


@router.post(
    "/bootstrap",
    response_model=UserRead,
    summary="Bootstrap Authenticated User Context",
    description=(
        "Resolve caller identity from auth headers and return the canonical user profile. "
        "This endpoint does not accept a request body."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "Authenticated user profile resolved from token claims.",
            "content": {
                "application/json": {
                    "example": {
                        "id": "11111111-1111-1111-1111-111111111111",
                        "clerk_user_id": "user_2abcXYZ",
                        "email": "alex@example.com",
                        "name": "Alex Chen",
                        "preferred_name": "Alex",
                        "pronouns": "they/them",
                        "timezone": "America/Los_Angeles",
                        "notes": "Primary operator for board triage.",
                        "context": "Handles incident coordination and escalation.",
                        "is_super_admin": False,
                    }
                }
            },
        },
        status.HTTP_401_UNAUTHORIZED: {
            "model": LLMErrorResponse,
            "description": "Caller is not authenticated as a user actor.",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {"code": "unauthorized", "message": "Not authenticated"},
                        "code": "unauthorized",
                        "retryable": False,
                    }
                }
            },
        },
    },
)
async def bootstrap_user(auth: AuthContext = AUTH_CONTEXT_DEP) -> UserRead:
    """Return the authenticated user profile from token claims."""
    if auth.actor_type != "user" or auth.user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return UserRead.model_validate(auth.user)


@router.get("/terms-status", summary="Check terms acceptance status")
async def terms_status(auth: AuthContext = AUTH_CONTEXT_DEP) -> dict[str, Any]:
    """Check if the user has accepted the current terms version."""
    if auth.actor_type != "user" or auth.user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    user = auth.user
    accepted = user.terms_accepted_version == CURRENT_TERMS_VERSION
    return {
        "terms_accepted": accepted,
        "current_version": CURRENT_TERMS_VERSION,
        "accepted_version": user.terms_accepted_version,
        "accepted_at": user.terms_accepted_at.isoformat() if user.terms_accepted_at else None,
        "privacy_accepted_at": user.privacy_accepted_at.isoformat() if user.privacy_accepted_at else None,
    }


@router.post("/accept-terms", summary="Accept terms of service and privacy policy")
async def accept_terms(auth: AuthContext = AUTH_CONTEXT_DEP) -> dict[str, Any]:
    """Record the user's acceptance of the current terms version."""
    if auth.actor_type != "user" or auth.user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    now = utcnow()
    async with async_session_maker() as session:
        from sqlmodel import select
        from app.models.users import User

        user = (await session.execute(
            select(User).where(User.id == auth.user.id)
        )).scalar_one()

        user.terms_accepted_version = CURRENT_TERMS_VERSION
        user.terms_accepted_at = now
        user.privacy_accepted_at = now
        session.add(user)
        await session.commit()

    return {
        "ok": True,
        "terms_version": CURRENT_TERMS_VERSION,
        "accepted_at": now.isoformat(),
    }


@router.get("/providers", summary="List available auth providers")
async def list_auth_providers() -> dict:
    """Return which sign-in providers are enabled (no auth required)."""
    return {
        "primary": settings.auth_mode.value,
        "wechat_login": (
            settings.wechat_login_enabled
            and bool(settings.wechat_corp_id)
            and bool(settings.wechat_app_secret)
        ),
    }
