"""OAuth2 provider implementations for Zoho Mail and Microsoft Outlook."""

from __future__ import annotations

from abc import ABC, abstractmethod
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.email.types import OAuthTokenResult

logger = get_logger(__name__)


class EmailOAuthProvider(ABC):
    """Base class for email OAuth2 provider implementations."""

    @abstractmethod
    def get_authorization_url(self, state: str) -> str:
        """Return the provider's OAuth2 authorization URL with required params."""

    @abstractmethod
    async def exchange_code(self, code: str) -> OAuthTokenResult:
        """Exchange an authorization code for tokens and account info."""

    @abstractmethod
    async def refresh_access_token(self, refresh_token: str) -> tuple[str, int]:
        """Refresh an expired access token. Returns (new_access_token, expires_in)."""

    @abstractmethod
    async def get_user_info(self, access_token: str) -> dict[str, str]:
        """Fetch basic user profile from the provider."""


class ZohoOAuthProvider(EmailOAuthProvider):
    """OAuth2 implementation for Zoho Mail."""

    AUTH_URL = "https://accounts.zohocloud.ca/oauth/v2/auth"
    TOKEN_URL = "https://accounts.zohocloud.ca/oauth/v2/token"
    USER_INFO_URL = "https://mail.zohocloud.ca/api/accounts"
    SCOPES = "ZohoMail.messages.READ ZohoMail.messages.CREATE ZohoMail.accounts.READ"

    def get_authorization_url(self, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": settings.zoho_oauth_client_id,
            "redirect_uri": settings.zoho_oauth_redirect_uri,
            "scope": self.SCOPES,
            "state": state,
            "access_type": "offline",
            # Zoho OAuth2 may not support "select_account" prompt value (less
            # standards-compliant than Microsoft/Google). Keep at "consent" only
            # until Zoho docs are verified or a multi-Zoho-account use case
            # actually triggers the need.
            "prompt": "consent",
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> OAuthTokenResult:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.zoho_oauth_client_id,
                    "client_secret": settings.zoho_oauth_client_secret,
                    "redirect_uri": settings.zoho_oauth_redirect_uri,
                    "code": code,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token", "")
        expires_in = int(token_data.get("expires_in", 3600))

        user_info = await self.get_user_info(access_token)
        return OAuthTokenResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            scopes=self.SCOPES,
            provider_account_id=user_info.get("account_id", ""),
            email_address=user_info.get("email", ""),
            display_name=user_info.get("display_name"),
        )

    async def refresh_access_token(self, refresh_token: str) -> tuple[str, int]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": settings.zoho_oauth_client_id,
                    "client_secret": settings.zoho_oauth_client_secret,
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
                headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()

        accounts = data.get("data", [])
        if not accounts:
            raise ValueError("No Zoho Mail accounts found for this user.")
        account = accounts[0]
        return {
            "account_id": str(account.get("accountId", "")),
            "email": account.get("primaryEmailAddress", ""),
            "display_name": account.get("displayName"),
        }


class MicrosoftOAuthProvider(EmailOAuthProvider):
    """OAuth2 implementation for Microsoft Outlook via Graph API."""

    TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    AUTH_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
    USER_INFO_URL = "https://graph.microsoft.com/v1.0/me"
    SCOPES = "openid email profile offline_access Mail.Read Mail.ReadWrite Mail.Send"

    @property
    def _tenant(self) -> str:
        return settings.microsoft_oauth_tenant_id or "common"

    def get_authorization_url(self, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": settings.microsoft_oauth_client_id,
            "redirect_uri": settings.microsoft_oauth_redirect_uri,
            "scope": self.SCOPES,
            "state": state,
            "response_mode": "query",
            "prompt": "select_account consent",
        }
        base = self.AUTH_URL_TEMPLATE.format(tenant=self._tenant)
        return f"{base}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> OAuthTokenResult:
        token_url = self.TOKEN_URL_TEMPLATE.format(tenant=self._tenant)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.microsoft_oauth_client_id,
                    "client_secret": settings.microsoft_oauth_client_secret,
                    "redirect_uri": settings.microsoft_oauth_redirect_uri,
                    "code": code,
                    "scope": self.SCOPES,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token", "")
        expires_in = int(token_data.get("expires_in", 3600))

        user_info = await self.get_user_info(access_token)
        return OAuthTokenResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            scopes=self.SCOPES,
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
                    "scope": self.SCOPES,
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


class GoogleEmailOAuthProvider(EmailOAuthProvider):
    """OAuth2 implementation for Gmail / Google Workspace via the Gmail API."""

    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USER_INFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
    SCOPES = (
        "openid email profile "
        "https://www.googleapis.com/auth/gmail.readonly "
        "https://www.googleapis.com/auth/gmail.send "
        "https://www.googleapis.com/auth/gmail.modify"
    )

    @property
    def _redirect_uri(self) -> str:
        """Dedicated Gmail callback URI; falls back to the shared Google one."""
        return settings.google_email_redirect_uri or settings.google_oauth_redirect_uri

    def get_authorization_url(self, state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": self._redirect_uri,
            "scope": self.SCOPES,
            "state": state,
            "access_type": "offline",
            "prompt": "select_account consent",
            "include_granted_scopes": "true",
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> OAuthTokenResult:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.google_oauth_client_id,
                    "client_secret": settings.google_oauth_client_secret,
                    "redirect_uri": self._redirect_uri,
                    "code": code,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token", "")
        expires_in = int(token_data.get("expires_in", 3600))

        user_info = await self.get_user_info(access_token)
        return OAuthTokenResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            scopes=self.SCOPES,
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


def get_oauth_provider(provider: str) -> EmailOAuthProvider:
    """Factory for email OAuth providers."""
    if provider == "zoho":
        return ZohoOAuthProvider()
    if provider == "microsoft":
        return MicrosoftOAuthProvider()
    if provider == "google":
        return GoogleEmailOAuthProvider()
    raise ValueError(
        f"Unknown email provider: {provider!r}. Must be 'zoho', 'microsoft', or 'google'."
    )
