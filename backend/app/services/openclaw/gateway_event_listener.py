"""Persistent WebSocket listener for OpenClaw gateway events.

Connects to the gateway, subscribes to the event stream, normalises
incoming events into ``LiveActivityEvent`` objects, and publishes them
to the in-memory broadcast hub so SSE clients receive them instantly.

Designed to run as a single background ``asyncio.Task`` started from
the FastAPI lifespan.  Auto-reconnects with exponential back-off.
"""

from __future__ import annotations

import asyncio
import json
import time as _time
from typing import Any

import websockets
from websockets.exceptions import WebSocketException

from app.core.logging import get_logger
from app.services.openclaw.event_broadcast import LiveActivityEvent, broadcast
from app.services.openclaw.gateway_rpc import (
    GatewayConfig,
    _build_connect_params,
    _build_gateway_url,
    _create_ssl_context,
    _recv_first_message_or_none,
    get_chat_history,
)

logger = get_logger(__name__)

# Events we care about.
_INTERESTING_EVENTS = frozenset({
    "chat",
    "agent",
    "cron",
    "exec.approval.requested",
    "exec.approval.resolved",
    "presence",
    "shutdown",
    "health",
})

# Track session state for diffing health events.
_prev_sessions: dict[str, dict[str, Any]] = {}

_MAX_BACKOFF_SECONDS = 30


def _normalise_event(event_name: str, payload: dict[str, Any]) -> LiveActivityEvent | None:
    """Map a raw gateway event into a LiveActivityEvent."""

    if event_name == "chat":
        direction = payload.get("direction", "")
        agent = payload.get("agentId") or payload.get("agent") or ""
        session = payload.get("sessionKey") or ""
        text = payload.get("text") or payload.get("message") or ""
        preview = (text[:120] + "...") if len(text) > 120 else text

        if direction == "inbound":
            return LiveActivityEvent(
                event_type="agent.message_received",
                agent_name=str(agent),
                channel=str(session),
                message=preview or "Message received",
            )
        if direction == "outbound":
            return LiveActivityEvent(
                event_type="agent.responded",
                agent_name=str(agent),
                channel=str(session),
                message=preview or "Agent responded",
            )
        # Generic chat event
        return LiveActivityEvent(
            event_type="agent.chat",
            agent_name=str(agent),
            channel=str(session),
            message=preview or "Chat activity",
            metadata=payload,
        )

    if event_name == "agent":
        agent = payload.get("agentId") or payload.get("id") or ""
        state = payload.get("state") or payload.get("status") or ""
        tool = payload.get("tool") or ""
        model = payload.get("model") or ""

        if tool:
            return LiveActivityEvent(
                event_type="agent.tool_call",
                agent_name=str(agent),
                message=f"Calling tool: {tool}",
                model=str(model),
                metadata=payload,
            )
        if state in ("thinking", "busy", "processing"):
            return LiveActivityEvent(
                event_type="agent.thinking",
                agent_name=str(agent),
                message="Thinking...",
                model=str(model),
            )
        if state in ("idle", "done", "completed"):
            return LiveActivityEvent(
                event_type="agent.completed",
                agent_name=str(agent),
                message="Completed",
                model=str(model),
            )
        return LiveActivityEvent(
            event_type="agent.state_change",
            agent_name=str(agent),
            message=f"State: {state}" if state else "Agent event",
            model=str(model),
            metadata=payload,
        )

    if event_name == "cron":
        job_name = payload.get("name") or payload.get("jobName") or ""
        status = payload.get("status") or ""
        agent = payload.get("agentId") or ""
        if status in ("started", "running"):
            return LiveActivityEvent(
                event_type="cron.started",
                agent_name=str(agent),
                message=f"Cron started: {job_name}",
                metadata=payload,
            )
        if status in ("completed", "done", "success"):
            return LiveActivityEvent(
                event_type="cron.completed",
                agent_name=str(agent),
                message=f"Cron completed: {job_name}",
                metadata=payload,
            )
        if status in ("error", "failed"):
            return LiveActivityEvent(
                event_type="cron.error",
                agent_name=str(agent),
                message=f"Cron failed: {job_name} — {payload.get('error', '')}",
                metadata=payload,
            )
        return LiveActivityEvent(
            event_type="cron.event",
            agent_name=str(agent),
            message=f"Cron: {job_name} ({status})",
            metadata=payload,
        )

    if event_name == "exec.approval.requested":
        return LiveActivityEvent(
            event_type="approval.requested",
            agent_name=payload.get("agentId", ""),
            message=f"Approval requested: {payload.get('actionType', '')}",
            metadata=payload,
        )

    if event_name == "exec.approval.resolved":
        decision = payload.get("decision") or payload.get("status") or ""
        return LiveActivityEvent(
            event_type="approval.resolved",
            agent_name=payload.get("agentId", ""),
            message=f"Approval {decision}",
            metadata=payload,
        )

    if event_name == "presence":
        return None  # Handled separately; too noisy for the feed.

    if event_name == "shutdown":
        return LiveActivityEvent(
            event_type="gateway.shutdown",
            message="Gateway shutting down",
        )

    return None


async def _fetch_latest_chat(session_key: str, config: GatewayConfig) -> list[dict[str, Any]]:
    """Fetch the last 2 messages from a session's chat history (zero token cost)."""
    try:
        result = await get_chat_history(session_key, config, limit=2)
        if isinstance(result, dict):
            return result.get("messages", []) or result.get("history", []) or []
        if isinstance(result, list):
            return result
    except Exception as exc:  # noqa: BLE001
        logger.debug("gateway_event_listener.chat_history_failed key=%s error=%s", session_key, exc)
    return []


def _extract_message_preview(messages: list[dict[str, Any]]) -> tuple[str, str]:
    """Extract the latest user message and assistant response from chat history."""
    user_msg = ""
    assistant_msg = ""
    for msg in reversed(messages):
        role = msg.get("role", "")
        content = msg.get("content") or msg.get("text") or ""
        if isinstance(content, list):
            # Multi-part content — extract text parts
            content = " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
        content = str(content).strip()
        if role in ("assistant", "model") and not assistant_msg:
            assistant_msg = (content[:200] + "...") if len(content) > 200 else content
        elif role in ("user", "human") and not user_msg:
            user_msg = (content[:200] + "...") if len(content) > 200 else content
    return user_msg, assistant_msg


async def _diff_health_sessions(payload: dict[str, Any], config: GatewayConfig) -> list[LiveActivityEvent]:
    """Compare health event sessions with previous state and emit deltas."""
    global _prev_sessions  # noqa: PLW0603
    sessions = payload.get("sessions")
    if not isinstance(sessions, (list, dict)):
        return []

    if isinstance(sessions, dict):
        session_list = list(sessions.values())
    else:
        session_list = sessions

    events: list[LiveActivityEvent] = []
    current: dict[str, dict[str, Any]] = {}

    for s in session_list:
        if not isinstance(s, dict):
            continue
        key = s.get("key", "")
        if not key:
            continue
        current[key] = s

        prev = _prev_sessions.get(key)
        total = s.get("totalTokens", 0) or 0
        prev_total = (prev.get("totalTokens", 0) or 0) if prev else 0
        agent_id = key.split(":")[1] if ":" in key else "unknown"
        model = (s.get("model") or "").split("/")[-1] if s.get("model") else ""
        channel = s.get("groupChannel") or s.get("displayName") or ""
        updated_at = s.get("updatedAt", 0) or 0

        if prev is None and _prev_sessions:
            events.append(LiveActivityEvent(
                event_type="agent.new_session",
                agent_name=agent_id,
                channel=channel,
                model=model,
                message=f"New session in {channel}" if channel else "New session started",
            ))
        elif prev and total > prev_total:
            delta = total - prev_total
            is_active = updated_at and (updated_at / 1000) > (_time.time() - 15)

            # Fetch latest chat to show what was said
            user_msg = ""
            assistant_msg = ""
            try:
                messages = await _fetch_latest_chat(key, config)
                user_msg, assistant_msg = _extract_message_preview(messages)
            except Exception:  # noqa: BLE001
                pass

            if is_active:
                msg = f"Processing in {channel} (+{delta:,} tokens)"
                if user_msg:
                    msg = f"📩 {user_msg}"
                events.append(LiveActivityEvent(
                    event_type="agent.working",
                    agent_name=agent_id,
                    channel=channel,
                    model=model,
                    message=msg,
                    metadata={"tokenDelta": delta, "totalTokens": total},
                ))
            else:
                msg = f"Completed in {channel}"
                if assistant_msg:
                    msg = f"💬 {assistant_msg}"
                events.append(LiveActivityEvent(
                    event_type="agent.completed",
                    agent_name=agent_id,
                    channel=channel,
                    model=model,
                    message=msg,
                    metadata={"tokenDelta": delta, "totalTokens": total},
                ))

    _prev_sessions = current
    return events


async def _listen(config: GatewayConfig) -> None:
    """Open a persistent connection and process events until disconnected."""
    url = _build_gateway_url(config)
    ssl_ctx = _create_ssl_context(config)
    connect_kwargs: dict[str, Any] = {"additional_headers": {}}
    if ssl_ctx:
        connect_kwargs["ssl"] = ssl_ctx

    async with websockets.connect(url, **connect_kwargs) as ws:
        # --- Handshake (same as _ensure_connected) ---
        first = await _recv_first_message_or_none(ws)
        connect_nonce: str | None = None
        if first:
            raw = first.decode("utf-8") if isinstance(first, bytes) else first
            data = json.loads(raw)
            if data.get("type") == "event" and data.get("event") == "connect.challenge":
                nonce = (data.get("payload") or {}).get("nonce")
                if isinstance(nonce, str) and nonce.strip():
                    connect_nonce = nonce.strip()

        connect_id = str(__import__("uuid").uuid4())
        connect_msg = {
            "type": "req",
            "id": connect_id,
            "method": "connect",
            "params": _build_connect_params(config, connect_nonce=connect_nonce),
        }
        await ws.send(json.dumps(connect_msg))

        # Wait for connect response
        while True:
            raw = await ws.recv()
            resp = json.loads(raw)
            if resp.get("id") == connect_id:
                if resp.get("ok") is False or resp.get("error"):
                    err = (resp.get("error") or {}).get("message", "connect failed")
                    raise WebSocketException(f"Gateway connect failed: {err}")
                break

        logger.info("gateway_event_listener.connected")

        try:
            from app.core.prometheus import gateway_listener_connected
            gateway_listener_connected.set(1)
        except Exception:  # noqa: BLE001
            pass

        # Publish a synthetic "connected" event
        broadcast.publish(LiveActivityEvent(
            event_type="gateway.connected",
            message="Connected to gateway event stream",
        ))

        # --- Event loop ---
        async for raw_msg in ws:
            try:
                data = json.loads(raw_msg)
            except (json.JSONDecodeError, TypeError):
                continue

            msg_type = data.get("type", "")
            event_name = data.get("event", "")

            # Log all incoming messages for debugging (temporary)
            if msg_type == "event":
                logger.info(
                    "gateway_event_listener.event event=%s payload_keys=%s",
                    event_name,
                    sorted((data.get("payload") or {}).keys()) if isinstance(data.get("payload"), dict) else "n/a",
                )

            if msg_type != "event":
                continue

            if event_name not in _INTERESTING_EVENTS:
                continue

            payload = data.get("payload") or {}
            if not isinstance(payload, dict):
                payload = {}

            # Health events use diff-based detection.
            if event_name == "health":
                for activity in await _diff_health_sessions(payload, config):
                    broadcast.publish(activity)
                continue

            activity = _normalise_event(event_name, payload)
            if activity:
                broadcast.publish(activity)


async def run_event_listener(config: GatewayConfig) -> None:
    """Run the event listener forever with auto-reconnect."""
    backoff = 1
    while True:
        try:
            await _listen(config)
        except asyncio.CancelledError:
            logger.info("gateway_event_listener.cancelled")
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "gateway_event_listener.disconnected error=%s backoff=%ss",
                exc,
                backoff,
            )
            try:
                from app.core.prometheus import gateway_listener_connected
                gateway_listener_connected.set(0)
            except Exception:  # noqa: BLE001
                pass
            broadcast.publish(LiveActivityEvent(
                event_type="gateway.disconnected",
                message=f"Disconnected: {exc}",
            ))

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)
