"""OAuth2 connection flow endpoints for email providers."""

from __future__ import annotations

import json
import secrets
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

import redis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.api.deps import ORG_MEMBER_DEP, SESSION_DEP
from app.core.config import settings
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.email_accounts import EmailAccount
from app.services.email.oauth import get_oauth_provider
from app.services.email.token_manager import store_tokens
from app.services.organizations import OrganizationContext

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = get_logger(__name__)
router = APIRouter(prefix="/email/oauth", tags=["email"])

VALID_PROVIDERS = ("zoho", "microsoft")
_STATE_TTL_SECONDS = 300  # 5 minutes


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.rq_redis_url)


@router.get(
    "/{provider}/authorize",
    summary="Initiate email OAuth flow",
    description="Returns a redirect URL to the provider's OAuth2 consent screen.",
)
async def initiate_oauth(
    provider: Literal["zoho", "microsoft"],
    ctx: OrganizationContext = ORG_MEMBER_DEP,
) -> dict[str, str]:
    """Generate and return the OAuth2 authorization URL."""
    oauth = get_oauth_provider(provider)

    state = secrets.token_urlsafe(32)
    state_payload = json.dumps(
        {
            "user_id": str(ctx.member.user_id),
            "organization_id": str(ctx.organization.id),
            "provider": provider,
        }
    )
    client = _redis_client()
    client.setex(f"email_oauth_state:{state}", _STATE_TTL_SECONDS, state_payload)

    url = oauth.get_authorization_url(state)
    return {"authorization_url": url, "state": state}


@router.get(
    "/{provider}/callback",
    summary="OAuth callback",
    description="Handles the OAuth2 callback from the email provider.",
    include_in_schema=False,
)
async def oauth_callback(
    provider: Literal["zoho", "microsoft"],
    code: str = Query(...),
    state: str = Query(...),
    error: str | None = Query(default=None),
    session: AsyncSession = SESSION_DEP,
) -> RedirectResponse:
    """Handle OAuth2 callback, exchange code for tokens, create EmailAccount."""
    if error:
        logger.warning("email.oauth.callback_error", extra={"provider": provider, "error": error})
        return RedirectResponse(url=f"/settings?email_error={error}")

    # Validate state
    client = _redis_client()
    raw_state = client.get(f"email_oauth_state:{state}")
    if raw_state is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state.",
        )
    client.delete(f"email_oauth_state:{state}")

    state_data = json.loads(raw_state if isinstance(raw_state, str) else raw_state.decode())  # type: ignore[union-attr]
    if state_data.get("provider") != provider:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider mismatch in OAuth state.",
        )

    user_id = state_data["user_id"]
    organization_id = state_data["organization_id"]

    # Exchange code for tokens
    oauth = get_oauth_provider(provider)
    try:
        result = await oauth.exchange_code(code)
    except Exception as exc:
        logger.exception(
            "email.oauth.exchange_failed",
            extra={"provider": provider, "error": str(exc)},
        )
        return RedirectResponse(url="/settings?email_error=exchange_failed")

    # Upsert EmailAccount
    from sqlalchemy import select

    stmt = select(EmailAccount).where(
        EmailAccount.organization_id == organization_id,
        EmailAccount.provider == provider,  # type: ignore[arg-type]
        EmailAccount.email_address == result.email_address,  # type: ignore[arg-type]
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()

    if existing:
        account = existing
    else:
        account = EmailAccount(
            id=uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            provider=provider,
            email_address=result.email_address,
            created_at=utcnow(),
        )

    account.display_name = result.display_name
    account.provider_account_id = result.provider_account_id
    account.scopes = result.scopes
    account.sync_enabled = True
    account.last_sync_error = None
    account.updated_at = utcnow()

    store_tokens(
        account,
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        expires_in=result.expires_in,
    )

    session.add(account)
    await session.commit()

    logger.info(
        "email.oauth.connected",
        extra={
            "provider": provider,
            "email": result.email_address,
            "account_id": str(account.id),
            "organization_id": organization_id,
        },
    )
    return RedirectResponse(url="/settings?email_connected=true")
