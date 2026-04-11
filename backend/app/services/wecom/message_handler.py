"""WeCom inbound message handler — routes messages to the gateway agent.

Message flow:
1. Inbound WeCom message (text) arrives
2. Sanitize for prompt injection
3. Resolve org's gateway config
4. Send to gateway via chat.send RPC
5. Poll for agent response (up to timeout)
6. Return response text for reply
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.core.sanitize import sanitize_text
from app.services.openclaw.gateway_resolver import gateway_client_config
from app.services.openclaw.gateway_rpc import (
    OpenClawGatewayError,
    get_chat_history,
    send_message,
)

if TYPE_CHECKING:
    from app.models.gateways import Gateway
    from app.models.wecom_connection import WeComConnection

logger = get_logger(__name__)

# Max time to wait for the agent to respond before switching to async reply
SYNC_TIMEOUT_SECONDS = 4.0
POLL_INTERVAL_SECONDS = 0.5


def _session_key(connection: "WeComConnection", from_user: str) -> str:
    """Build a unique gateway session key for a WeCom user."""
    agent_id = connection.target_agent_id or "the-claw"
    return f"agent:{agent_id}:wecom-{from_user}"


async def handle_message(
    *,
    connection: "WeComConnection",
    gateway: "Gateway",
    from_user: str,
    content: str,
) -> str | None:
    """Process an inbound WeCom text message and return agent response (or None if timeout).

    Returns None if the agent doesn't respond within SYNC_TIMEOUT_SECONDS,
    signaling the caller to use async reply instead.
    """
    sanitized = sanitize_text(content)
    if not sanitized.strip():
        return None

    config = gateway_client_config(gateway)
    session_key = _session_key(connection, from_user)

    # Get current history length to detect new messages
    try:
        history_before = await get_chat_history(session_key, config, limit=1)
        if isinstance(history_before, dict):
            messages_before = history_before.get("messages", [])
            last_id_before = messages_before[-1].get("id") if messages_before else None
        else:
            last_id_before = None
    except OpenClawGatewayError:
        last_id_before = None

    # Send the message
    try:
        await send_message(sanitized, session_key=session_key, config=config)
    except OpenClawGatewayError as exc:
        logger.error(
            "wecom.message.send_failed from_user=%s error=%s",
            from_user,
            str(exc)[:200],
        )
        return None

    # Poll for response
    elapsed = 0.0
    while elapsed < SYNC_TIMEOUT_SECONDS:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS

        try:
            history = await get_chat_history(session_key, config, limit=5)
        except OpenClawGatewayError:
            continue

        if not isinstance(history, dict):
            continue

        messages = history.get("messages", [])
        # Look for a new assistant message after our send
        for msg in reversed(messages):
            if msg.get("role") != "assistant":
                continue
            if last_id_before and msg.get("id") == last_id_before:
                break
            response_text = msg.get("content", "")
            if response_text:
                logger.info(
                    "wecom.message.response from_user=%s response_len=%d elapsed=%.1fs",
                    from_user,
                    len(response_text),
                    elapsed,
                )
                return response_text  # type: ignore[no-any-return]

    logger.info(
        "wecom.message.sync_timeout from_user=%s elapsed=%.1fs",
        from_user,
        elapsed,
    )
    return None
