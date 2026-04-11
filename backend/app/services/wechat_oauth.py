"""WeChat/WeCom OAuth authentication service for China deployments.

WeCom OAuth flow (企业微信网页授权):
1. Frontend redirects to WeCom authorize URL
2. User scans QR / clicks approve in WeCom
3. WeCom redirects back to our callback with `code`
4. Backend exchanges `code` for user identity (user_id, name, email, etc.)

This uses WeCom's OAuth2.0 identity API, NOT the enterprise app API
(which is already in app/services/wecom/ for messaging).

Ref: https://developer.work.weixin.qq.com/document/path/91023
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

WECOM_OAUTH_AUTHORIZE_URL = "https://open.weixin.qq.com/connect/oauth2/authorize"
WECOM_GET_TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
WECOM_GET_USER_INFO_URL = "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo"
WECOM_GET_USER_DETAIL_URL = "https://qyapi.weixin.qq.com/cgi-bin/user/get"


class WeComOAuthError(Exception):
    """Error during WeCom OAuth flow."""


@dataclass
class WeComUserInfo:
    """User identity resolved from WeCom OAuth code exchange."""

    user_id: str  # WeCom internal user ID (unique within corp)
    name: str  # Display name
    email: str  # Corporate email (may be empty)
    corp_id: str  # Which corp this user belongs to


def build_authorize_url(
    *,
    corp_id: str,
    redirect_uri: str,
    agent_id: str = "",
    state: str = "wechat_login",
) -> str:
    """Build the WeCom OAuth authorize URL for the frontend redirect.

    Args:
        corp_id: WeCom corp ID.
        redirect_uri: URL-encoded callback URL (our /auth/wechat/callback).
        agent_id: WeCom app agent ID (for scoped auth).
        state: Opaque state parameter for CSRF protection.

    Returns:
        Full authorize URL for frontend redirect.
    """
    import urllib.parse

    params = {
        "appid": corp_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "snsapi_privateinfo",
        "state": state,
    }
    if agent_id:
        params["agentid"] = agent_id

    return f"{WECOM_OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}#wechat_redirect"


async def _get_access_token(corp_id: str, corp_secret: str) -> str:
    """Fetch a WeCom access token for API calls."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            WECOM_GET_TOKEN_URL,
            params={"corpid": corp_id, "corpsecret": corp_secret},
        )
        resp.raise_for_status()
        data = resp.json()

    errcode = data.get("errcode", 0)
    if errcode != 0:
        raise WeComOAuthError(
            f"Failed to get access token: errcode={errcode} errmsg={data.get('errmsg', '')}"
        )

    return data["access_token"]  # type: ignore[no-any-return]


async def exchange_code_for_user(
    *,
    code: str,
    corp_id: str,
    corp_secret: str,
) -> WeComUserInfo:
    """Exchange a WeCom OAuth code for user identity.

    Flow:
    1. Get access token (corp_id + secret)
    2. Exchange code for user_id (getuserinfo)
    3. Fetch user details (user/get) for name and email

    Args:
        code: OAuth code from WeCom redirect.
        corp_id: WeCom corp ID.
        corp_secret: WeCom app secret.

    Returns:
        WeComUserInfo with the authenticated user's identity.

    Raises:
        WeComOAuthError: If any step fails.
    """
    access_token = await _get_access_token(corp_id, corp_secret)

    async with httpx.AsyncClient(timeout=10) as client:
        # Step 2: Exchange code for user_id
        resp = await client.get(
            WECOM_GET_USER_INFO_URL,
            params={"access_token": access_token, "code": code},
        )
        resp.raise_for_status()
        data = resp.json()

    errcode = data.get("errcode", 0)
    if errcode != 0:
        raise WeComOAuthError(
            f"Code exchange failed: errcode={errcode} errmsg={data.get('errmsg', '')}"
        )

    user_id = data.get("userid") or data.get("UserId", "")
    if not user_id:
        raise WeComOAuthError("No user_id returned from code exchange — user may be external")

    # Step 3: Get user details (name, email)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            WECOM_GET_USER_DETAIL_URL,
            params={"access_token": access_token, "userid": user_id},
        )
        resp.raise_for_status()
        detail = resp.json()

    if detail.get("errcode", 0) != 0:
        logger.warning(
            "wechat_oauth.user_detail_failed user_id=%s errcode=%s",
            user_id,
            detail.get("errcode"),
        )
        # Fall back to just user_id
        return WeComUserInfo(
            user_id=user_id,
            name=user_id,
            email="",
            corp_id=corp_id,
        )

    return WeComUserInfo(
        user_id=user_id,
        name=detail.get("name", user_id),
        email=detail.get("biz_mail", "") or detail.get("email", ""),
        corp_id=corp_id,
    )
