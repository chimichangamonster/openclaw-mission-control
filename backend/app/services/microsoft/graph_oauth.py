"""Microsoft Graph OAuth provider — extends email OAuth with broader scopes."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

GRAPH_SCOPES = (
    "openid email profile offline_access "
    "Files.ReadWrite.All "
    "Calendars.ReadWrite "
    "Sites.Read.All"
)


@dataclass(frozen=True)
class GraphTokenResult:
    """Tokens and user info from a Graph OAuth code exchange."""

    access_token: str
    refresh_token: str
    expires_in: int
    scopes: str
    provider_account_id: str
    email_address: str
    display_name: str | None = None


class MicrosoftGraphOAuthProvider:
    """OAuth2 for Microsoft Graph with OneDrive/Calendar/SharePoint scopes."""

    TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    AUTH_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
    USER_INFO_URL = "https://graph.microsoft.com/v1.0/me"

    @property
    def _tenant(self) -> str:
        return settings.microsoft_oauth_tenant_id or "common"

    @property
    def _redirect_uri(self) -> str:
        return settings.microsoft_graph_redirect_uri or settings.microsoft_oauth_redirect_uri

    def get_authorization_url(self, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": settings.microsoft_oauth_client_id,
            "redirect_uri": self._redirect_uri,
            "scope": GRAPH_SCOPES,
            "state": state,
            "response_mode": "query",
            "prompt": "select_account consent",
        }
        base = self.AUTH_URL_TEMPLATE.format(tenant=self._tenant)
        return f"{base}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> GraphTokenResult:
        token_url = self.TOKEN_URL_TEMPLATE.format(tenant=self._tenant)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.microsoft_oauth_client_id,
                    "client_secret": settings.microsoft_oauth_client_secret,
                    "redirect_uri": self._redirect_uri,
                    "code": code,
                    "scope": GRAPH_SCOPES,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token", "")
        expires_in = int(token_data.get("expires_in", 3600))

        user_info = await self.get_user_info(access_token)
        return GraphTokenResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            scopes=GRAPH_SCOPES,
            provider_account_id=user_info.get("id", ""),
            email_address=user_info.get("mail", user_info.get("userPrincipalName", "")),
            display_name=user_info.get("displayName"),
        )

    async def refresh_access_token(self, refresh_token: str) -> tuple[str, int]:
        token_url = self.TOKEN_URL_TEMPLATE.format(tenant=self._tenant)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                token_url,
                data={
                    "grant_type": "refresh_token",
                    "client_id": settings.microsoft_oauth_client_id,
                    "client_secret": settings.microsoft_oauth_client_secret,
                    "refresh_token": refresh_token,
                    "scope": GRAPH_SCOPES,
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
            "mail": data.get("mail", ""),
            "userPrincipalName": data.get("userPrincipalName", ""),
            "displayName": data.get("displayName"),
        }
