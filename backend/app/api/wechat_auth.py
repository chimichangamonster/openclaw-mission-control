"""WeChat/WeCom OAuth authentication endpoints for China deployments.

Flow:
1. GET  /auth/wechat/authorize   → returns WeCom authorize URL for frontend redirect
2. POST /auth/wechat/callback    → exchanges code for user identity, returns JWT-like session token
3. GET  /auth/wechat/userinfo    → returns current user from session token

Frontend flow:
1. User clicks "Login with WeChat" → redirect to authorize URL
2. WeCom redirects back with ?code=xxx → frontend POSTs to /callback
3. Backend returns a session token → frontend stores in sessionStorage
4. All subsequent requests use Bearer token (same as local auth mode)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, TYPE_CHECKING

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.core.logging import get_logger
from app.db import crud
from app.db.session import async_session_maker
from app.models.users import User
from app.services.wechat_oauth import WeComOAuthError, build_authorize_url, exchange_code_for_user

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)
router = APIRouter(prefix="/auth/wechat", tags=["auth"])

# Session tokens are HMAC-SHA256 signed payloads: base64(json(claims)) + "." + hex(signature)
# This is NOT a JWT — it's simpler and doesn't require a JWT library.
# Tokens expire after 24 hours.
_TOKEN_TTL_SECONDS = 86400


def _sign_token(payload: dict[str, Any]) -> str:
    """Create a signed session token from claims."""
    import base64

    payload["exp"] = int(time.time()) + _TOKEN_TTL_SECONDS
    payload["iat"] = int(time.time())
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(
        settings.wechat_app_secret.encode(),
        encoded.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{encoded}.{sig}"


def _verify_token(token: str) -> dict[str, Any] | None:
    """Verify and decode a signed session token. Returns None if invalid."""
    import base64

    parts = token.split(".", 1)
    if len(parts) != 2:
        return None

    encoded, sig = parts
    expected_sig = hmac.new(
        settings.wechat_app_secret.encode(),
        encoded.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(sig, expected_sig):
        return None

    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded))
    except Exception:
        return None

    # Check expiry
    if payload.get("exp", 0) < time.time():
        return None

    return payload  # type: ignore[no-any-return]


@router.get("/authorize")
async def wechat_authorize(redirect_uri: str) -> dict[str, Any]:
    """Return the WeCom OAuth authorize URL for frontend redirect."""
    url = build_authorize_url(
        corp_id=settings.wechat_corp_id,
        redirect_uri=redirect_uri,
        agent_id=settings.wechat_agent_id,
    )
    return {"authorize_url": url}


@router.post("/callback")
async def wechat_callback(code: str) -> dict[str, Any]:
    """Exchange a WeCom OAuth code for a session token.

    The frontend redirects here after WeCom authorization.
    Returns a session token that works as a Bearer token for all API calls.
    """
    try:
        user_info = await exchange_code_for_user(
            code=code,
            corp_id=settings.wechat_corp_id,
            corp_secret=settings.wechat_app_secret,
        )
    except WeComOAuthError as exc:
        logger.warning("wechat_auth.callback.failed error=%s", str(exc)[:200])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"WeChat authentication failed: {exc}",
        ) from exc

    # Upsert user in DB
    wechat_user_id = f"wechat-{user_info.corp_id}-{user_info.user_id}"
    async with async_session_maker() as session:
        defaults: dict[str, object] = {
            "email": user_info.email or f"{user_info.user_id}@{user_info.corp_id}.wecom",
            "name": user_info.name,
        }
        user, created = await crud.get_or_create(
            session,
            User,
            clerk_user_id=wechat_user_id,
            defaults=defaults,
        )

        # Update name/email if changed
        changed = False
        if user_info.name and user.name != user_info.name:
            user.name = user_info.name
            changed = True
        if user_info.email and user.email != user_info.email:
            user.email = user_info.email
            changed = True
        if changed:
            session.add(user)
            await session.commit()

        from app.services.organizations import ensure_member_for_user

        await ensure_member_for_user(session, user)

    # Create session token
    token = _sign_token(
        {
            "sub": wechat_user_id,
            "name": user_info.name,
            "email": user_info.email,
            "corp_id": user_info.corp_id,
            "wechat_user_id": user_info.user_id,
        }
    )

    logger.info(
        "wechat_auth.login user_id=%s name=%s created=%s",
        user_info.user_id,
        user_info.name,
        created,
    )

    return {
        "token": token,
        "user": {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
        },
    }
