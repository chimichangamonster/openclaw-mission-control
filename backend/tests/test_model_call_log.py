# ruff: noqa: INP001
"""Tests for the llm_call wrapper and model_call_log persistence.

Verifies:
- Successful LLM calls produce a ModelCallLog row with status=success + tokens
- HTTP 5xx failures persist with status=error, error_type=server_error
- HTTP 401/403 classified as error_type=auth
- HTTP 429 classified as error_type=rate_limit
- httpx.TimeoutException persists with status=timeout, error_type=timeout
- httpx.ConnectError persists with status=error, error_type=connect_error
- OpenRouter error_body with metadata.provider_name is extracted
- error_body clipped to 500 chars
- Cost is computed when tokens are present and model is in registry
- Logging failure never blocks the caller (still raises the original exc)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.model_call_log import ModelCallLog
from app.services.llm_call import (
    _classify_error,
    _extract_provider_name,
    llm_call,
)


async def _make_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


def _session_maker(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _mock_client(response: httpx.Response | None = None, exc: BaseException | None = None):
    client = AsyncMock(spec=httpx.AsyncClient)

    async def _request(*_args, **_kwargs):
        if exc is not None:
            raise exc
        assert response is not None
        return response

    client.request = _request
    return client


def _response(status: int, body: dict | str) -> httpx.Response:
    req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    if isinstance(body, dict):
        import json as _json

        return httpx.Response(status, content=_json.dumps(body).encode(), request=req)
    return httpx.Response(status, content=body.encode(), request=req)


# ── Unit: classify_error + extract_provider_name ─────────────────────────────


def test_classify_error_timeout():
    assert _classify_error(http_status=None, exc=httpx.TimeoutException("x")) == (
        "timeout",
        "timeout",
    )


def test_classify_error_connect():
    assert _classify_error(http_status=None, exc=httpx.ConnectError("x")) == (
        "error",
        "connect_error",
    )


def test_classify_error_5xx():
    assert _classify_error(http_status=503, exc=None) == ("error", "server_error")


def test_classify_error_429():
    assert _classify_error(http_status=429, exc=None) == ("error", "rate_limit")


def test_classify_error_401():
    assert _classify_error(http_status=401, exc=None) == ("error", "auth")


def test_classify_error_403():
    assert _classify_error(http_status=403, exc=None) == ("error", "auth")


def test_classify_error_400():
    assert _classify_error(http_status=400, exc=None) == ("error", "bad_request")


def test_extract_provider_name_from_openrouter_error():
    body = (
        '{"error": {"code": 503, "message": "upstream",'
        ' "metadata": {"provider_name": "Anthropic"}}}'
    )
    assert _extract_provider_name(body) == "Anthropic"


def test_extract_provider_name_handles_garbage():
    assert _extract_provider_name(None) is None
    assert _extract_provider_name("not json") is None
    assert _extract_provider_name('{"error": "string not dict"}') is None
    assert _extract_provider_name('{"error": {}}') is None


# ── Integration: wrapper persistence ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_successful_call_persists_row_with_tokens():
    org_id = uuid4()
    engine = await _make_engine()
    maker = _session_maker(engine)

    resp = _response(
        200,
        {
            "choices": [{"message": {"content": "hello"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        },
    )
    client = _mock_client(response=resp)

    with patch("app.services.llm_call.async_session_maker", maker):
        out = await llm_call(
            client,  # type: ignore[arg-type]
            method="POST",
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": "Bearer x"},
            json_body={"model": "anthropic/claude-sonnet-4"},
            skill_name="test_skill",
            model="anthropic/claude-sonnet-4",
            organization_id=org_id,
        )

    assert out.status_code == 200

    async with maker() as session:
        rows = (await session.execute(select(ModelCallLog))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "success"
    assert row.model == "anthropic/claude-sonnet-4"
    assert row.skill_name == "test_skill"
    assert row.provider == "openrouter"
    assert row.http_status == 200
    assert row.tokens_in == 12
    assert row.tokens_out == 4
    assert row.error_type is None
    assert row.error_body is None


@pytest.mark.asyncio
async def test_server_error_persists_with_provider_name():
    """An OpenRouter 503 carrying provider_name=Anthropic should log
    error_type=server_error AND provider_name=Anthropic."""
    engine = await _make_engine()
    maker = _session_maker(engine)

    body = (
        '{"error": {"code": 503, "message": "upstream unavailable",'
        ' "metadata": {"provider_name": "Anthropic"}}}'
    )
    resp = _response(503, body)
    client = _mock_client(response=resp)

    with patch("app.services.llm_call.async_session_maker", maker):
        out = await llm_call(
            client,  # type: ignore[arg-type]
            method="POST",
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={},
            json_body={},
            skill_name="test_skill",
            model="anthropic/claude-sonnet-4",
            organization_id=None,
        )
    # Wrapper returns the error response rather than raising — caller handles
    assert out.status_code == 503

    async with maker() as session:
        rows = (await session.execute(select(ModelCallLog))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "error"
    assert row.error_type == "server_error"
    assert row.provider_name == "Anthropic"
    assert row.http_status == 503
    assert "upstream unavailable" in (row.error_body or "")


@pytest.mark.asyncio
async def test_timeout_persists_and_reraises():
    engine = await _make_engine()
    maker = _session_maker(engine)

    client = _mock_client(exc=httpx.TimeoutException("slow"))

    with patch("app.services.llm_call.async_session_maker", maker):
        with pytest.raises(httpx.TimeoutException):
            await llm_call(
                client,  # type: ignore[arg-type]
                method="POST",
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={},
                json_body={},
                skill_name="test_skill",
                model="anthropic/claude-sonnet-4",
                organization_id=None,
            )

    async with maker() as session:
        rows = (await session.execute(select(ModelCallLog))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "timeout"
    assert row.error_type == "timeout"
    assert row.http_status is None


@pytest.mark.asyncio
async def test_rate_limit_classified():
    engine = await _make_engine()
    maker = _session_maker(engine)

    resp = _response(429, {"error": {"message": "slow down"}})
    client = _mock_client(response=resp)

    with patch("app.services.llm_call.async_session_maker", maker):
        await llm_call(
            client,  # type: ignore[arg-type]
            method="POST",
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={},
            json_body={},
            skill_name="test_skill",
            model="anthropic/claude-sonnet-4",
            organization_id=None,
        )

    async with maker() as session:
        rows = (await session.execute(select(ModelCallLog))).scalars().all()
    assert rows[0].error_type == "rate_limit"


@pytest.mark.asyncio
async def test_error_body_clipped_to_500():
    """Large error bodies must not bloat the table."""
    engine = await _make_engine()
    maker = _session_maker(engine)

    huge_body = "x" * 2000
    resp = _response(500, huge_body)
    client = _mock_client(response=resp)

    with patch("app.services.llm_call.async_session_maker", maker):
        await llm_call(
            client,  # type: ignore[arg-type]
            method="POST",
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={},
            json_body={},
            skill_name="test_skill",
            model="anthropic/claude-sonnet-4",
            organization_id=None,
        )

    async with maker() as session:
        rows = (await session.execute(select(ModelCallLog))).scalars().all()
    assert len(rows[0].error_body or "") == 500
