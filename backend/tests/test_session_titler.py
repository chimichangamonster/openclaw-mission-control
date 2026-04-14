# ruff: noqa: INP001
"""Tests for auto-generated session titles via Gemini Flash Lite.

Verifies LLM-based title generation including happy path, sanitization,
empty input handling, HTTP errors, missing endpoint, and title length
limits. Part of chat reorganization Tier 1 (item 34a).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from app.services.llm_routing import LLMEndpoint
from app.services.openclaw.session_titler import generate_title


def _fake_endpoint() -> LLMEndpoint:
    return LLMEndpoint(
        api_url="https://openrouter.ai/api/v1",
        api_key="sk-test-key",
        source="platform_openrouter",
        name="Test",
        models=[],
        is_openrouter=True,
    )


def _llm_response(content: str) -> dict:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"total_tokens": 12},
    }


class _FakeHTTPClient:
    """Async context manager returning a fake HTTP client with a canned response."""

    def __init__(self, response_json: dict | None = None, raise_exc: Exception | None = None):
        self._response_json = response_json
        self._raise_exc = raise_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, *args, **kwargs):
        if self._raise_exc:
            raise self._raise_exc
        return _FakeResponse(self._response_json or {})


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)  # type: ignore[arg-type]

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_generate_title_happy_path() -> None:
    org_id = uuid4()
    with (
        patch(
            "app.services.openclaw.session_titler.resolve_llm_endpoint",
            new=AsyncMock(return_value=_fake_endpoint()),
        ),
        patch(
            "app.services.openclaw.session_titler.httpx.AsyncClient",
            return_value=_FakeHTTPClient(response_json=_llm_response("Property Smart Proposal")),
        ),
    ):
        result = await generate_title(
            org_id,
            user_msg="Can you draft a marketing proposal for Property Smart?",
            assistant_msg="Sure, here's a proposal covering their dumpster rental business...",
        )
    assert result == "Property Smart Proposal"


@pytest.mark.asyncio
async def test_generate_title_strips_quotes_and_punctuation() -> None:
    org_id = uuid4()
    with (
        patch(
            "app.services.openclaw.session_titler.resolve_llm_endpoint",
            new=AsyncMock(return_value=_fake_endpoint()),
        ),
        patch(
            "app.services.openclaw.session_titler.httpx.AsyncClient",
            return_value=_FakeHTTPClient(response_json=_llm_response('"Market Update."')),
        ),
    ):
        result = await generate_title(org_id, user_msg="hi", assistant_msg="ok")
    assert result == "Market Update"


@pytest.mark.asyncio
async def test_generate_title_strips_smart_quotes() -> None:
    org_id = uuid4()
    with (
        patch(
            "app.services.openclaw.session_titler.resolve_llm_endpoint",
            new=AsyncMock(return_value=_fake_endpoint()),
        ),
        patch(
            "app.services.openclaw.session_titler.httpx.AsyncClient",
            return_value=_FakeHTTPClient(
                response_json=_llm_response("\u201cMagnetik Q2 Review\u201d")
            ),
        ),
    ):
        result = await generate_title(org_id, user_msg="hi", assistant_msg="ok")
    assert result == "Magnetik Q2 Review"


@pytest.mark.asyncio
async def test_generate_title_returns_none_on_empty_user_message() -> None:
    org_id = uuid4()
    with patch(
        "app.services.openclaw.session_titler.resolve_llm_endpoint",
        new=AsyncMock(return_value=_fake_endpoint()),
    ) as mock_resolve:
        result = await generate_title(org_id, user_msg="   ", assistant_msg="response")
    assert result is None
    mock_resolve.assert_not_called()  # Should short-circuit before hitting LLM


@pytest.mark.asyncio
async def test_generate_title_returns_none_when_endpoint_missing() -> None:
    org_id = uuid4()
    with patch(
        "app.services.openclaw.session_titler.resolve_llm_endpoint",
        new=AsyncMock(return_value=None),
    ):
        result = await generate_title(org_id, user_msg="hi", assistant_msg="ok")
    assert result is None


@pytest.mark.asyncio
async def test_generate_title_returns_none_on_http_error() -> None:
    org_id = uuid4()
    with (
        patch(
            "app.services.openclaw.session_titler.resolve_llm_endpoint",
            new=AsyncMock(return_value=_fake_endpoint()),
        ),
        patch(
            "app.services.openclaw.session_titler.httpx.AsyncClient",
            return_value=_FakeHTTPClient(raise_exc=httpx.ConnectError("refused")),
        ),
    ):
        result = await generate_title(org_id, user_msg="hi", assistant_msg="ok")
    assert result is None


@pytest.mark.asyncio
async def test_generate_title_returns_none_on_malformed_response() -> None:
    org_id = uuid4()
    with (
        patch(
            "app.services.openclaw.session_titler.resolve_llm_endpoint",
            new=AsyncMock(return_value=_fake_endpoint()),
        ),
        patch(
            "app.services.openclaw.session_titler.httpx.AsyncClient",
            return_value=_FakeHTTPClient(response_json={"unexpected": "shape"}),
        ),
    ):
        result = await generate_title(org_id, user_msg="hi", assistant_msg="ok")
    assert result is None


@pytest.mark.asyncio
async def test_generate_title_rejects_overly_long_title() -> None:
    org_id = uuid4()
    runaway = "word " * 30  # 150 chars — exceeds 80-char cap
    with (
        patch(
            "app.services.openclaw.session_titler.resolve_llm_endpoint",
            new=AsyncMock(return_value=_fake_endpoint()),
        ),
        patch(
            "app.services.openclaw.session_titler.httpx.AsyncClient",
            return_value=_FakeHTTPClient(response_json=_llm_response(runaway)),
        ),
    ):
        result = await generate_title(org_id, user_msg="hi", assistant_msg="ok")
    assert result is None


@pytest.mark.asyncio
async def test_generate_title_rejects_empty_string_response() -> None:
    org_id = uuid4()
    with (
        patch(
            "app.services.openclaw.session_titler.resolve_llm_endpoint",
            new=AsyncMock(return_value=_fake_endpoint()),
        ),
        patch(
            "app.services.openclaw.session_titler.httpx.AsyncClient",
            return_value=_FakeHTTPClient(response_json=_llm_response("   ")),
        ),
    ):
        result = await generate_title(org_id, user_msg="hi", assistant_msg="ok")
    assert result is None


@pytest.mark.asyncio
async def test_generate_title_handles_non_ascii() -> None:
    org_id = uuid4()
    with (
        patch(
            "app.services.openclaw.session_titler.resolve_llm_endpoint",
            new=AsyncMock(return_value=_fake_endpoint()),
        ),
        patch(
            "app.services.openclaw.session_titler.httpx.AsyncClient",
            return_value=_FakeHTTPClient(response_json=_llm_response("北京办公室设置")),
        ),
    ):
        result = await generate_title(
            org_id,
            user_msg="Set up the Beijing office WeCom integration",
            assistant_msg="Sure, here are the steps...",
        )
    assert result == "北京办公室设置"
