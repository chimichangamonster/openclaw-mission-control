# ruff: noqa: INP001
"""Tests for gateway chat command RPC helpers and session service methods.

Verifies that abort, compact, and reset commands:
- Call the correct gateway RPC methods
- Pass the right parameters
- Propagate errors as expected
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.openclaw.gateway_rpc import (
    GatewayConfig,
    OpenClawGatewayError,
    abort_chat,
    compact_session,
    delete_session,
    reset_session,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_CONFIG = GatewayConfig(
    url="ws://gateway.test/ws",
    token="test-token",
    disable_device_pairing=True,
)

SESSION_KEY = "agent:the-claw:general"


# ---------------------------------------------------------------------------
# RPC helper tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_abort_chat_calls_correct_method() -> None:
    with patch(
        "app.services.openclaw.gateway_rpc.openclaw_call",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ) as mock_call:
        result = await abort_chat(SESSION_KEY, config=FAKE_CONFIG)

    mock_call.assert_called_once_with(
        "chat.abort",
        {"sessionKey": SESSION_KEY},
        config=FAKE_CONFIG,
    )
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_compact_session_calls_correct_method() -> None:
    with patch(
        "app.services.openclaw.gateway_rpc.openclaw_call",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ) as mock_call:
        result = await compact_session(SESSION_KEY, config=FAKE_CONFIG)

    mock_call.assert_called_once_with(
        "sessions.compact",
        {"key": SESSION_KEY},
        config=FAKE_CONFIG,
    )
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_reset_session_calls_correct_method() -> None:
    with patch(
        "app.services.openclaw.gateway_rpc.openclaw_call",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ) as mock_call:
        result = await reset_session(SESSION_KEY, config=FAKE_CONFIG)

    mock_call.assert_called_once_with(
        "sessions.reset",
        {"key": SESSION_KEY},
        config=FAKE_CONFIG,
    )
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_delete_session_calls_correct_method() -> None:
    with patch(
        "app.services.openclaw.gateway_rpc.openclaw_call",
        new_callable=AsyncMock,
        return_value={"ok": True},
    ) as mock_call:
        result = await delete_session(SESSION_KEY, config=FAKE_CONFIG)

    mock_call.assert_called_once_with(
        "sessions.delete",
        {"key": SESSION_KEY},
        config=FAKE_CONFIG,
    )
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_abort_chat_propagates_gateway_error() -> None:
    with patch(
        "app.services.openclaw.gateway_rpc.openclaw_call",
        new_callable=AsyncMock,
        side_effect=OpenClawGatewayError("connection refused"),
    ):
        with pytest.raises(OpenClawGatewayError, match="connection refused"):
            await abort_chat(SESSION_KEY, config=FAKE_CONFIG)


@pytest.mark.asyncio
async def test_compact_session_propagates_gateway_error() -> None:
    with patch(
        "app.services.openclaw.gateway_rpc.openclaw_call",
        new_callable=AsyncMock,
        side_effect=OpenClawGatewayError("session not found"),
    ):
        with pytest.raises(OpenClawGatewayError, match="session not found"):
            await compact_session(SESSION_KEY, config=FAKE_CONFIG)


@pytest.mark.asyncio
async def test_reset_session_propagates_gateway_error() -> None:
    with patch(
        "app.services.openclaw.gateway_rpc.openclaw_call",
        new_callable=AsyncMock,
        side_effect=OpenClawGatewayError("timeout"),
    ):
        with pytest.raises(OpenClawGatewayError, match="timeout"):
            await reset_session(SESSION_KEY, config=FAKE_CONFIG)


# ---------------------------------------------------------------------------
# Method registration tests
# ---------------------------------------------------------------------------


def test_chat_abort_in_gateway_methods() -> None:
    from app.services.openclaw.gateway_rpc import GATEWAY_METHODS

    assert "chat.abort" in GATEWAY_METHODS


def test_sessions_compact_in_gateway_methods() -> None:
    from app.services.openclaw.gateway_rpc import GATEWAY_METHODS

    assert "sessions.compact" in GATEWAY_METHODS


def test_sessions_reset_in_gateway_methods() -> None:
    from app.services.openclaw.gateway_rpc import GATEWAY_METHODS

    assert "sessions.reset" in GATEWAY_METHODS


def test_chat_send_in_gateway_methods() -> None:
    from app.services.openclaw.gateway_rpc import GATEWAY_METHODS

    assert "chat.send" in GATEWAY_METHODS


def test_chat_history_in_gateway_methods() -> None:
    from app.services.openclaw.gateway_rpc import GATEWAY_METHODS

    assert "chat.history" in GATEWAY_METHODS
