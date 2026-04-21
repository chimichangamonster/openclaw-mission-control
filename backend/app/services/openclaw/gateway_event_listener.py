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
import re
import time as _time
from typing import Any

import websockets
from websockets.exceptions import WebSocketException

from app.core.logging import get_logger
from app.services.openclaw.event_broadcast import LiveActivityEvent, broadcast
from app.services.openclaw.gateway_rpc import (
    GatewayConfig,
    _build_connect_params,
    _build_control_ui_origin,
    _build_gateway_url,
    _create_ssl_context,
    _recv_first_message_or_none,
    get_chat_history,
)

logger = get_logger(__name__)

# Events we care about.
_INTERESTING_EVENTS = frozenset(
    {
        "chat",
        "agent",
        "cron",
        "exec.approval.requested",
        "exec.approval.resolved",
        "presence",
        "shutdown",
        "health",
    }
)

# Track session state for diffing health events.
_prev_sessions: dict[str, dict[str, Any]] = {}

_MAX_BACKOFF_SECONDS = 30


def _extract_delivery_mode(payload: dict[str, Any]) -> str | None:
    """Derive a toast-routing hint from a gateway cron event payload.

    Gateway payload shape (verified live 2026-04-21 via bundle read):
      - `delivered`: bool (true = sent to channel, false = not sent)
      - `deliveryStatus`: "delivered" | "not-delivered" | "unknown"
      - NO configured `delivery.mode` in event payload

    Gateway's `resolveDeliveryStatus` returns `not-delivered` when
    `delivered === false`, which happens in TWO cases:
      (a) mode=announce/webhook and send actually failed (real failure)
      (b) mode=none (silent-disk) — nothing to send, so never "delivered"

    Case (b) is the common case (item 44a's primary target), case (a) is
    rare (delivery genuinely failed). We can't disambiguate without an
    RPC lookup, so map `not-delivered` to "none" (silent-disk toast to
    /memory?tab=reports). Real delivery failures will route there too —
    acceptable false-positive since both need user visibility and the
    report is equally accessible.

    Mapping:
      "delivered"     → "announce" (Discord/webhook confirmed sent)
      "not-delivered" → "none"     (silent-disk OR genuine send failure)
      "unknown"       → None       (legacy fallback toast)

    Legacy shapes (nested delivery.mode, snake/camel case) kept for tests
    and potential gateway evolution.
    """
    status = payload.get("deliveryStatus") or payload.get("delivery_status")
    if isinstance(status, str):
        mapping = {
            "delivered": "announce",
            "not-delivered": "none",
        }
        mapped = mapping.get(status)
        if mapped is not None:
            return mapped
    delivery = payload.get("delivery")
    if isinstance(delivery, dict):
        mode = delivery.get("mode")
        if isinstance(mode, str):
            return mode
    mode = payload.get("delivery_mode") or payload.get("deliveryMode")
    if isinstance(mode, str):
        return mode
    return None


def _coerce_preview_text(value: Any) -> str:
    """Safely coerce a gateway event payload value into a preview string.

    Gateway chat events sometimes ship ``payload.message`` as a full ChatMessage
    dict ``{role, content, timestamp}`` where ``content`` is a string or a
    content-blocks array. The activity panel is a telemetry feed, not a
    transcript — so extract the first line of readable text and cap length.
    Unknown shapes fall through to empty string; callers substitute a
    clean event-type label instead.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                p.get("text", "")
                for p in content
                if isinstance(p, dict)
                and p.get("type") == "text"
                and isinstance(p.get("text"), str)
            ]
            return " ".join(s for s in parts if s)
    return ""


def _normalise_event(event_name: str, payload: dict[str, Any]) -> LiveActivityEvent | None:
    """Map a raw gateway event into a LiveActivityEvent.

    Real gateway schema (from upstream ``server-chat.ts``):

    - ``chat`` with ``state="delta"`` — streaming token chunk, many per turn.
      Skip (returns None) — would flood the activity panel with duplicates.
    - ``chat`` with ``state="final"`` — turn completion. ``message`` is present
      unless it was a silent reply. THIS is the real "agent responded" signal.
    - ``chat`` with ``state="error"`` — turn error. ``errorMessage`` present.
    - ``agent`` with ``stream="assistant"`` — LLM token stream, too chatty. Skip.
    - ``agent`` with ``stream="lifecycle"`` + ``data.phase="start"`` — "Thinking...".
    - ``agent`` with ``stream="lifecycle"`` + ``data.phase="end"`` — skip (chat
      final covers completion; lifecycle end is a duplicate).
    - ``agent`` with ``stream="lifecycle"`` + ``data.phase="error"`` — skip (chat
      error covers it).
    - ``agent`` with ``stream="tool"`` — tool call/result.
    - ``agent`` with ``stream="error"`` — seq gap warning, ignore.
    """

    if event_name == "chat":
        session = payload.get("sessionKey") or ""
        state = payload.get("state", "")

        if state == "delta":
            return None  # Streaming chunks — skip.

        if state == "final":
            msg = payload.get("message")
            text = _coerce_preview_text(msg)
            preview = (text[:120] + "...") if len(text) > 120 else text
            return LiveActivityEvent(
                event_type="agent.responded",
                channel=str(session),
                message=preview or "Agent responded",
                metadata={"runId": payload.get("runId"), "hasMessage": msg is not None},
            )

        if state == "error":
            err = payload.get("errorMessage") or "Agent error"
            return LiveActivityEvent(
                event_type="agent.error",
                channel=str(session),
                message=str(err)[:200],
                metadata={"runId": payload.get("runId")},
            )

        # Unknown chat state — log and skip.
        return None

    if event_name == "agent":
        session = payload.get("sessionKey") or ""
        stream = payload.get("stream", "")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}

        if stream == "assistant":
            return None  # Token-by-token LLM output — too chatty.

        if stream == "lifecycle":
            phase = data.get("phase") if isinstance(data, dict) else None
            if phase == "start":
                return LiveActivityEvent(
                    event_type="agent.thinking",
                    channel=str(session),
                    message="Thinking...",
                    metadata={"runId": payload.get("runId")},
                )
            # phase="end" / "error" are duplicates of chat final/error — skip.
            return None

        if stream == "tool":
            tool_name = ""
            if isinstance(data, dict):
                raw = data.get("tool") or data.get("name") or data.get("toolName")
                if isinstance(raw, str):
                    tool_name = raw
            return LiveActivityEvent(
                event_type="agent.tool_call",
                channel=str(session),
                message=f"Using tool: {tool_name}" if tool_name else "Using tool",
                metadata={"runId": payload.get("runId")},
            )

        if stream == "error":
            return None  # seq gap noise — not a user-facing error.

        return None

    if event_name == "cron":
        # Real gateway payload: {action, deliveryStatus, durationMs, jobId, model,
        # nextRunAtMs, provider, runAtMs, sessionId, sessionKey, status, summary,
        # usage}. No name/agentId — derive from jobId+sessionKey.
        job_name = (
            payload.get("name")
            or payload.get("jobName")
            or payload.get("summary")
            or payload.get("jobId")
            or ""
        )
        status = payload.get("status") or ""
        action = payload.get("action") or ""
        agent = payload.get("agentId") or payload.get("sessionKey") or ""
        logger.info(
            "cron_event_dispatch action=%s status=%s deliveryStatus=%s",
            action,
            status,
            payload.get("deliveryStatus"),
        )
        # Promote delivery.mode to a stable top-level field for frontend consumers.
        # Gateway may emit delivery as a nested object, as separate fields, or omit
        # it entirely — fail-open to None so downstream fail-open to legacy behavior.
        delivery_mode = _extract_delivery_mode(payload)
        enriched = {**payload, "delivery_mode": delivery_mode}
        if status in ("started", "running"):
            return LiveActivityEvent(
                event_type="cron.started",
                agent_name=str(agent),
                message=f"Cron started: {job_name}",
                metadata=enriched,
            )
        # Completion is signaled by either action="finished" OR status in the
        # success/completed set. Gateway often sends both; check either.
        if action == "finished" or status in ("completed", "done", "success", "ok"):
            logger.info(
                "cron.completed action=%s status=%s delivery_mode=%s job=%s",
                action,
                status,
                delivery_mode,
                job_name,
            )
            return LiveActivityEvent(
                event_type="cron.completed",
                agent_name=str(agent),
                message=f"Cron completed: {job_name}",
                metadata=enriched,
            )
        if status in ("error", "failed") or action == "failed":
            return LiveActivityEvent(
                event_type="cron.error",
                agent_name=str(agent),
                message=f"Cron failed: {job_name} — {payload.get('error', '')}",
                metadata=enriched,
            )
        return LiveActivityEvent(
            event_type="cron.event",
            agent_name=str(agent),
            message=f"Cron: {job_name} ({status})",
            metadata=enriched,
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
    """Fetch recent messages from a session's chat history (zero token cost).

    Uses limit=20 rather than 2 because tool-calling agents interleave the
    user turn with assistant thinking/toolCall messages and toolResult
    replies. With limit=2 we would get [toolResult, assistant(text)] and
    miss the user message entirely — which silently broke the titler
    dispatch path until 2026-04-15. _extract_message_preview walks
    backward and will stop at the first user turn it finds.
    """
    try:
        result = await get_chat_history(session_key, config, limit=20)
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
            content = " ".join(
                p.get("text", "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        content = str(content).strip()
        if role in ("assistant", "model") and not assistant_msg:
            assistant_msg = (content[:200] + "...") if len(content) > 200 else content
        elif role in ("user", "human") and not user_msg:
            user_msg = (content[:200] + "...") if len(content) > 200 else content
    return user_msg, assistant_msg


async def _diff_health_sessions(
    payload: dict[str, Any],
    config: GatewayConfig,
    *,
    organization_id: str = "",
) -> list[LiveActivityEvent]:
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
            events.append(
                LiveActivityEvent(
                    event_type="agent.new_session",
                    agent_name=agent_id,
                    channel=channel,
                    model=model,
                    message=f"New session in {channel}" if channel else "New session started",
                )
            )
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
                events.append(
                    LiveActivityEvent(
                        event_type="agent.working",
                        agent_name=agent_id,
                        channel=channel,
                        model=model,
                        message=msg,
                        metadata={"tokenDelta": delta, "totalTokens": total},
                    )
                )
            else:
                msg = f"Completed in {channel}"
                if assistant_msg:
                    msg = f"💬 {assistant_msg}"
                events.append(
                    LiveActivityEvent(
                        event_type="agent.completed",
                        agent_name=agent_id,
                        channel=channel,
                        model=model,
                        message=msg,
                        metadata={"tokenDelta": delta, "totalTokens": total},
                    )
                )
                # Titler hook moved to the real chat.final event dispatch site
                # (see _listen → _autotitle_from_final). Health-diff completion
                # is a heuristic that fires ~15s late; the chat.final event is
                # the true signal.

    _prev_sessions = current
    return events


_DEFAULT_LABEL_RE = re.compile(r"^New chat \d{2}:\d{2}:\d{2}$")


def _is_default_label(label: str) -> bool:
    """True for collision-proof auto-defaults produced by the sidebar.

    Sidebar's ``defaultSessionLabel()`` emits ``New chat HH:MM:SS``. Those
    labels are NOT user intent — they only exist because gateway rejects
    duplicate ``Conversation N`` labels with 502. The titler should
    overwrite them once a real conversation starts.
    """
    return bool(_DEFAULT_LABEL_RE.match(label))


async def _autotitle_from_final(
    org_id_str: str,
    session_key: str,
    assistant_msg: str,
    config: GatewayConfig,
) -> None:
    """Title hook for real ``chat`` ``state=final`` events.

    The final event carries the assistant reply but not the user turn, so we
    fetch the last 2 history entries to pair them, then delegate to the same
    title generator used by the health-diff heuristic.
    """
    logger.info(
        "session_titler.final_enter org=%s key=%s",
        org_id_str[:8],
        session_key[-12:],
    )
    user_msg = ""
    try:
        messages = await _fetch_latest_chat(session_key, config)
        u, _a = _extract_message_preview(messages)
        user_msg = u
    except Exception:  # noqa: BLE001
        pass
    if not user_msg:
        logger.info(
            "session_titler.no_user_msg org=%s key=%s",
            org_id_str[:8],
            session_key[-12:],
        )
        return
    await _maybe_autotitle_session(org_id_str, session_key, user_msg, assistant_msg)


async def _maybe_autotitle_session(
    org_id_str: str, session_key: str, user_msg: str, assistant_msg: str
) -> None:
    """Generate + persist a title for an ad-hoc chat session that has no label.

    Fire-and-forget helper called from the health-diff completed branch. All
    errors are swallowed — worst case is the session keeps its default label.
    """
    from uuid import UUID

    from app.db.session import async_session_maker
    from app.services.openclaw.session_service import GatewaySessionService
    from app.services.openclaw.session_titler import generate_title

    try:
        org_id = UUID(org_id_str)
    except (ValueError, TypeError):
        return

    try:
        async with async_session_maker() as session:
            service = GatewaySessionService(session)
            existing = await service._get_session_labels(org_id)
        current_label = existing.get(session_key)
        if current_label and not _is_default_label(current_label):
            logger.info(
                "session_titler.manual_label_wins org=%s key=%s label=%s",
                org_id_str[:8],
                session_key[-12:],
                current_label,
            )
            return  # User-renamed — respect it.

        title = await generate_title(org_id, user_msg, assistant_msg)
        if not title:
            logger.info(
                "session_titler.no_title_returned org=%s key=%s",
                org_id_str[:8],
                session_key[-12:],
            )
            return

        async with async_session_maker() as session:
            service = GatewaySessionService(session)
            await service._save_session_label(org_id, session_key, title)

        logger.info(
            "session_titler.persisted org=%s key=%s title=%s",
            org_id_str[:8],
            session_key[-12:],
            title,
        )
    except Exception:  # noqa: BLE001
        logger.info("session_titler.autotitle_failed key=%s", session_key, exc_info=True)


async def _listen(
    config: GatewayConfig,
    *,
    organization_id: str = "",
    gateway_id: str = "",
) -> None:
    """Open a persistent connection and process events until disconnected."""
    url = _build_gateway_url(config)
    ssl_ctx = _create_ssl_context(config)
    connect_kwargs: dict[str, Any] = {"additional_headers": {}}
    if ssl_ctx:
        connect_kwargs["ssl"] = ssl_ctx
    if config.disable_device_pairing:
        origin = _build_control_ui_origin(url)
        if origin:
            connect_kwargs["origin"] = origin

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
            raw_msg = await ws.recv()
            raw = raw_msg.decode("utf-8") if isinstance(raw_msg, bytes) else raw_msg
            resp = json.loads(raw)
            if resp.get("id") == connect_id:
                if resp.get("ok") is False or resp.get("error"):
                    err = (resp.get("error") or {}).get("message", "connect failed")
                    raise WebSocketException(f"Gateway connect failed: {err}")
                break

        label = f"org={organization_id[:8] or 'default'}"
        logger.info("gateway_event_listener.connected %s", label)

        try:
            from app.core.prometheus import gateway_listener_connected

            gateway_listener_connected.set(1)
        except Exception:  # noqa: BLE001
            pass

        def _tag(event: LiveActivityEvent) -> LiveActivityEvent:
            """Stamp org/gateway identity onto an event."""
            event.organization_id = organization_id
            event.gateway_id = gateway_id
            return event

        # Publish a synthetic "connected" event
        broadcast.publish(
            _tag(
                LiveActivityEvent(
                    event_type="gateway.connected",
                    message="Connected to gateway event stream",
                )
            )
        )

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
                    "gateway_event_listener.event %s event=%s payload_keys=%s",
                    label,
                    event_name,
                    (
                        sorted((data.get("payload") or {}).keys())
                        if isinstance(data.get("payload"), dict)
                        else "n/a"
                    ),
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
                for activity in await _diff_health_sessions(
                    payload, config, organization_id=organization_id
                ):
                    broadcast.publish(_tag(activity))
                continue

            normalized = _normalise_event(event_name, payload)
            if normalized:
                broadcast.publish(_tag(normalized))

            # Fire-and-forget auto-title on real chat completion signal.
            # Runs for unlabeled :chat- sessions only; manual labels win
            # because _maybe_autotitle_session re-checks the label store
            # before writing.
            if (
                event_name == "chat"
                and payload.get("state") == "final"
                and organization_id
                and isinstance(payload.get("sessionKey"), str)
                and ":chat-" in payload["sessionKey"]
            ):
                asst = _coerce_preview_text(payload.get("message"))
                if asst:
                    session_key = payload["sessionKey"]
                    # Fetch the latest user message from history to pair with
                    # the assistant response — the gateway final event only
                    # carries the assistant side.
                    asyncio.create_task(
                        _autotitle_from_final(organization_id, session_key, asst, config),
                        name=f"autotitle-{session_key[-8:]}",
                    )


async def run_event_listener(
    config: GatewayConfig,
    *,
    organization_id: str = "",
    gateway_id: str = "",
) -> None:
    """Run the event listener forever with auto-reconnect.

    When *organization_id* and *gateway_id* are provided, all emitted
    ``LiveActivityEvent`` objects are tagged so SSE consumers can filter
    by org.
    """
    backoff = 1
    label = f"org={organization_id or 'default'} gw={gateway_id or 'default'}"
    while True:
        try:
            await _listen(
                config,
                organization_id=organization_id,
                gateway_id=gateway_id,
            )
        except asyncio.CancelledError:
            logger.info("gateway_event_listener.cancelled %s", label)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "gateway_event_listener.disconnected %s error=%s backoff=%ss",
                label,
                exc,
                backoff,
            )
            try:
                from app.core.prometheus import gateway_listener_connected

                gateway_listener_connected.set(0)
            except Exception:  # noqa: BLE001
                pass
            broadcast.publish(
                LiveActivityEvent(
                    event_type="gateway.disconnected",
                    organization_id=organization_id,
                    gateway_id=gateway_id,
                    message=f"Disconnected: {exc}",
                )
            )

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)


async def run_all_event_listeners() -> list[asyncio.Task[None]]:
    """Query all configured gateways and spawn a listener task per gateway.

    Returns the list of running tasks so the lifespan can cancel them on
    shutdown.
    """
    from sqlmodel import col, select

    from app.db.session import async_session_maker
    from app.models.gateways import Gateway

    tasks: list[asyncio.Task[None]] = []
    try:
        async with async_session_maker() as session:
            gateways = (
                await session.exec(select(Gateway).where(col(Gateway.url).is_not(None)))
            ).all()

        for gw in gateways:
            if not gw.url:
                continue
            config = GatewayConfig(
                url=gw.url.strip(),
                token=(gw.token or "").strip() or None,
                allow_insecure_tls=gw.allow_insecure_tls,
                disable_device_pairing=gw.disable_device_pairing,
            )
            org_id = str(gw.organization_id) if gw.organization_id else ""
            gw_id = str(gw.id)
            task = asyncio.create_task(
                run_event_listener(
                    config,
                    organization_id=org_id,
                    gateway_id=gw_id,
                ),
                name=f"gw-listener-{gw_id[:8]}",
            )
            tasks.append(task)
            logger.info(
                "gateway_event_listener.spawned org=%s gw=%s url=%s",
                org_id[:8] if org_id else "n/a",
                gw_id[:8],
                gw.url,
            )

        if not tasks:
            logger.info("gateway_event_listener.no_gateways_configured")
    except Exception as exc:  # noqa: BLE001
        logger.warning("gateway_event_listener.init_failed error=%s", exc)

    return tasks
