"""Google Calendar OAuth provider — authorization, token exchange, refresh."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

GOOGLE_CALENDAR_SCOPES = "openid email profile " "https://www.googleapis.com/auth/calendar"


@dataclass(frozen=True)
class GoogleTokenResult:
    """Tokens and user info from a Google OAuth code exchange."""

    access_token: str
    refresh_token: str
    expires_in: int
    scopes: str
    provider_account_id: str
    email_address: str
    display_name: str | None = None


class GoogleCalendarOAuthProvider:
    """OAuth2 for Google Calendar API."""

    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USER_INFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

    def get_authorization_url(self, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "scope": GOOGLE_CALENDAR_SCOPES,
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> GoogleTokenResult:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.google_oauth_client_id,
                    "client_secret": settings.google_oauth_client_secret,
                    "redirect_uri": settings.google_oauth_redirect_uri,
                    "code": code,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token", "")
        expires_in = int(token_data.get("expires_in", 3600))

        user_info = await self.get_user_info(access_token)
        return GoogleTokenResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            scopes=GOOGLE_CALENDAR_SCOPES,
            provider_account_id=user_info.get("id", ""),
            email_address=user_info.get("email", ""),
            display_name=user_info.get("name"),
        )

    async def refresh_access_token(self, refresh_token: str) -> tuple[str, int]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": settings.google_oauth_client_id,
                    "client_secret": settings.google_oauth_client_secret,
                    "refresh_token": refresh_token,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return data["access_token"], int(data.get("expires_in", 3600))

    async def get_user_info(self, access_token: str) -> dict[str, str]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self.USER_INFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
        return {
            "id": data.get("id", ""),
            "email": data.get("email", ""),
            "name": data.get("name"),
        }
