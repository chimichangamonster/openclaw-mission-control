# ruff: noqa: INP001
"""Tests for WeChat/WeCom OAuth authentication."""

from __future__ import annotations

import time

import pytest

from app.services.wechat_oauth import (
    WeComOAuthError,
    WeComUserInfo,
    build_authorize_url,
)

# ---------------------------------------------------------------------------
# build_authorize_url
# ---------------------------------------------------------------------------


class TestBuildAuthorizeUrl:
    def test_basic_url(self) -> None:
        url = build_authorize_url(
            corp_id="wx123456",
            redirect_uri="https://example.com/callback",
        )
        assert "open.weixin.qq.com" in url
        assert "wx123456" in url
        assert "https%3A%2F%2Fexample.com%2Fcallback" in url
        assert "snsapi_privateinfo" in url
        assert "#wechat_redirect" in url

    def test_with_agent_id(self) -> None:
        url = build_authorize_url(
            corp_id="wx123456",
            redirect_uri="https://example.com/callback",
            agent_id="1000001",
        )
        assert "agentid=1000001" in url

    def test_custom_state(self) -> None:
        url = build_authorize_url(
            corp_id="wx123456",
            redirect_uri="https://example.com/callback",
            state="custom_state_123",
        )
        assert "state=custom_state_123" in url


# ---------------------------------------------------------------------------
# WeComUserInfo
# ---------------------------------------------------------------------------


class TestWeComUserInfo:
    def test_dataclass_fields(self) -> None:
        info = WeComUserInfo(
            user_id="john_doe",
            name="John Doe",
            email="john@corp.com",
            corp_id="wx123",
        )
        assert info.user_id == "john_doe"
        assert info.name == "John Doe"
        assert info.email == "john@corp.com"
        assert info.corp_id == "wx123"


# ---------------------------------------------------------------------------
# Token signing/verification (backend session tokens)
# ---------------------------------------------------------------------------


class TestWeChatTokens:
    """Test HMAC-signed session tokens used by WeChat auth."""

    def test_sign_and_verify(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Token roundtrip: sign → verify → get claims back."""

        # Mock the settings to provide a secret
        class MockSettings:
            wechat_app_secret = "test-secret-for-hmac-signing-tokens"

        monkeypatch.setattr("app.api.wechat_auth.settings", MockSettings())
        from app.api.wechat_auth import _sign_token, _verify_token

        claims = {"sub": "wechat-wx123-johndoe", "name": "John"}
        token = _sign_token(claims)

        assert isinstance(token, str)
        assert "." in token

        payload = _verify_token(token)
        assert payload is not None
        assert payload["sub"] == "wechat-wx123-johndoe"
        assert payload["name"] == "John"
        assert "exp" in payload
        assert "iat" in payload

    def test_expired_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Expired tokens should return None."""

        class MockSettings:
            wechat_app_secret = "test-secret-for-hmac-signing-tokens"

        monkeypatch.setattr("app.api.wechat_auth.settings", MockSettings())
        monkeypatch.setattr("app.api.wechat_auth._TOKEN_TTL_SECONDS", -1)
        from app.api.wechat_auth import _sign_token, _verify_token

        token = _sign_token({"sub": "test"})
        payload = _verify_token(token)
        assert payload is None

    def test_tampered_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tampered tokens should return None."""

        class MockSettings:
            wechat_app_secret = "test-secret-for-hmac-signing-tokens"

        monkeypatch.setattr("app.api.wechat_auth.settings", MockSettings())
        from app.api.wechat_auth import _sign_token, _verify_token

        token = _sign_token({"sub": "test"})
        # Tamper with the signature
        parts = token.split(".")
        payload = _verify_token(f"{parts[0]}.{'0' * 64}")
        assert payload is None

    def test_garbage_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Garbage input should return None."""

        class MockSettings:
            wechat_app_secret = "test-secret"

        monkeypatch.setattr("app.api.wechat_auth.settings", MockSettings())
        from app.api.wechat_auth import _verify_token

        assert _verify_token("") is None
        assert _verify_token("not-a-token") is None
        assert _verify_token("a.b.c") is None

    def test_wrong_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Token signed with different secret should fail verification."""

        class MockSettings1:
            wechat_app_secret = "secret-one"

        class MockSettings2:
            wechat_app_secret = "secret-two"

        monkeypatch.setattr("app.api.wechat_auth.settings", MockSettings1())
        from app.api.wechat_auth import _sign_token, _verify_token

        token = _sign_token({"sub": "test"})

        monkeypatch.setattr("app.api.wechat_auth.settings", MockSettings2())
        payload = _verify_token(token)
        assert payload is None
