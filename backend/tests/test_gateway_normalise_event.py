"""Tests for _normalise_event against the real gateway schema.

Covers chat state transitions (delta/final/error) and agent stream types
(lifecycle/tool/assistant/error) observed in production gateway logs.
Locks in the 2026-04-14 schema fix that replaced the fantasy
``direction="inbound/outbound"`` / ``state="thinking/done"`` guesses.
"""

from app.services.openclaw.gateway_event_listener import (
    DeltaBuffer,
    _extract_delivery_mode,
    _is_default_label,
    _normalise_event,
)

# ── _is_default_label ──────────────────────────────────────────────────────


def test_default_label_matches_sidebar_pattern():
    assert _is_default_label("New chat 14:32:07") is True
    assert _is_default_label("New chat 00:00:00") is True
    assert _is_default_label("New chat 23:59:59") is True


def test_default_label_rejects_user_renames():
    assert _is_default_label("Budget review") is False
    assert _is_default_label("New chat") is False  # no timestamp
    assert _is_default_label("New chat 14:32") is False  # wrong format
    assert _is_default_label("new chat 14:32:07") is False  # wrong case
    assert _is_default_label("Conversation 3") is False  # legacy default
    assert _is_default_label("New chat 14:32:07 extra") is False  # trailing
    assert _is_default_label("") is False


# ── chat events ────────────────────────────────────────────────────────────


def test_chat_delta_skipped_when_streaming_disabled():
    """Delta tokens flood the panel — default behavior returns None."""
    payload = {
        "runId": "r1",
        "sessionKey": "vantage:the-claw:chat-abc",
        "seq": 5,
        "state": "delta",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "partial..."}],
            "timestamp": 1234567890,
        },
    }
    assert _normalise_event("chat", payload) is None
    assert _normalise_event("chat", payload, streaming_enabled=False) is None


def test_chat_delta_passes_through_when_streaming_enabled():
    """When chat_token_streaming flag is on, deltas emit token_delta events."""
    payload = {
        "runId": "r1",
        "sessionKey": "vantage:the-claw:chat-abc",
        "seq": 5,
        "state": "delta",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello"}],
            "timestamp": 1234567890,
        },
    }
    evt = _normalise_event("chat", payload, streaming_enabled=True)
    assert evt is not None
    assert evt.event_type == "agent.token_delta"
    assert evt.channel == "vantage:the-claw:chat-abc"
    assert evt.metadata["delta"] == "Hello"
    assert evt.metadata["runId"] == "r1"


def test_chat_delta_with_empty_text_skipped_even_when_enabled():
    """Empty/unparseable delta payloads skip — no point flushing nothing."""
    payload = {
        "runId": "r1",
        "sessionKey": "s1",
        "seq": 5,
        "state": "delta",
        "message": {"role": "assistant", "content": []},
    }
    assert _normalise_event("chat", payload, streaming_enabled=True) is None


def test_chat_final_with_message_emits_responded():
    payload = {
        "runId": "r1",
        "sessionKey": "vantage:the-claw:chat-abc",
        "seq": 42,
        "state": "final",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello there!"}],
            "timestamp": 1234567890,
        },
    }
    evt = _normalise_event("chat", payload)
    assert evt is not None
    assert evt.event_type == "agent.responded"
    assert evt.channel == "vantage:the-claw:chat-abc"
    assert evt.message == "Hello there!"
    assert evt.metadata["runId"] == "r1"
    assert evt.metadata["hasMessage"] is True


def test_chat_final_without_message_uses_default_label():
    """Silent replies omit .message — panel shows clean label."""
    payload = {"runId": "r1", "sessionKey": "s1", "seq": 1, "state": "final"}
    evt = _normalise_event("chat", payload)
    assert evt is not None
    assert evt.event_type == "agent.responded"
    assert evt.message == "Agent responded"
    assert evt.metadata["hasMessage"] is False


def test_chat_final_long_message_truncated():
    long_text = "x" * 500
    payload = {
        "runId": "r1",
        "sessionKey": "s1",
        "seq": 1,
        "state": "final",
        "message": {"role": "assistant", "content": long_text},
    }
    evt = _normalise_event("chat", payload)
    assert evt is not None
    assert len(evt.message) == 123  # 120 + "..."
    assert evt.message.endswith("...")


def test_chat_error_emits_error_event():
    payload = {
        "runId": "r1",
        "sessionKey": "s1",
        "seq": 1,
        "state": "error",
        "errorMessage": "LLM provider timeout",
    }
    evt = _normalise_event("chat", payload)
    assert evt is not None
    assert evt.event_type == "agent.error"
    assert evt.message == "LLM provider timeout"


def test_chat_unknown_state_skipped():
    """Forward-compat: unknown chat states must not raise."""
    payload = {"runId": "r1", "sessionKey": "s1", "seq": 1, "state": "future_state"}
    assert _normalise_event("chat", payload) is None


# ── agent events ───────────────────────────────────────────────────────────


def test_agent_lifecycle_start_emits_thinking():
    payload = {
        "runId": "r1",
        "stream": "lifecycle",
        "ts": 1234567890,
        "sessionKey": "s1",
        "data": {"phase": "start"},
    }
    evt = _normalise_event("agent", payload)
    assert evt is not None
    assert evt.event_type == "agent.thinking"
    assert evt.message == "Thinking..."


def test_agent_lifecycle_end_skipped():
    """chat.final covers completion — lifecycle end is a duplicate."""
    payload = {
        "runId": "r1",
        "stream": "lifecycle",
        "ts": 1234567890,
        "sessionKey": "s1",
        "data": {"phase": "end"},
    }
    assert _normalise_event("agent", payload) is None


def test_agent_lifecycle_error_skipped():
    """chat.error covers turn errors — lifecycle error is a duplicate."""
    payload = {
        "runId": "r1",
        "stream": "lifecycle",
        "ts": 1234567890,
        "sessionKey": "s1",
        "data": {"phase": "error"},
    }
    assert _normalise_event("agent", payload) is None


def test_agent_tool_emits_tool_call_with_name():
    payload = {
        "runId": "r1",
        "stream": "tool",
        "ts": 1234567890,
        "sessionKey": "s1",
        "data": {"tool": "fetch-url", "result": "<huge data>"},
    }
    evt = _normalise_event("agent", payload)
    assert evt is not None
    assert evt.event_type == "agent.tool_call"
    assert evt.message == "Using tool: fetch-url"


def test_agent_tool_without_name_falls_back():
    payload = {
        "runId": "r1",
        "stream": "tool",
        "ts": 1234567890,
        "sessionKey": "s1",
        "data": {},
    }
    evt = _normalise_event("agent", payload)
    assert evt is not None
    assert evt.event_type == "agent.tool_call"
    assert evt.message == "Using tool"


def test_agent_assistant_stream_skipped():
    """Token stream — too chatty for telemetry panel."""
    payload = {
        "runId": "r1",
        "stream": "assistant",
        "ts": 1234567890,
        "sessionKey": "s1",
        "data": {"text": "Partial LLM output..."},
    }
    assert _normalise_event("agent", payload) is None


def test_agent_error_stream_skipped():
    """Seq-gap noise — not a user-facing error."""
    payload = {
        "runId": "r1",
        "stream": "error",
        "ts": 1234567890,
        "sessionKey": "s1",
        "data": {"reason": "seq gap", "expected": 5, "received": 7},
    }
    assert _normalise_event("agent", payload) is None


def test_agent_unknown_stream_skipped():
    payload = {"runId": "r1", "stream": "future_stream", "sessionKey": "s1", "data": {}}
    assert _normalise_event("agent", payload) is None


# ── cron delivery mode extraction (item 44a) ───────────────────────────────


def test_extract_delivery_mode_from_gateway_deliveryStatus_delivered():
    """deliveryStatus='delivered' = Discord/webhook confirmed → 'announce'."""
    payload = {"deliveryStatus": "delivered"}
    assert _extract_delivery_mode(payload) == "announce"


def test_extract_delivery_mode_from_gateway_deliveryStatus_not_delivered():
    """deliveryStatus='not-delivered' = silent-disk OR send failure → 'none'.

    Gateway emits this for both mode=none (silent-disk expected) and genuine
    send failures. Both need a visibility toast; mapping to 'none' routes
    to /memory?tab=reports which works for either case.
    """
    payload = {"deliveryStatus": "not-delivered"}
    assert _extract_delivery_mode(payload) == "none"


def test_extract_delivery_mode_from_gateway_deliveryStatus_unknown_falls_through():
    """deliveryStatus='unknown' falls through to legacy checks, ultimately None."""
    assert _extract_delivery_mode({"deliveryStatus": "unknown"}) is None


def test_extract_delivery_mode_from_nested_delivery_object():
    """Legacy shape: delivery as nested object — kept as fallback."""
    payload = {"delivery": {"mode": "none", "bestEffort": True}}
    assert _extract_delivery_mode(payload) == "none"


def test_extract_delivery_mode_from_flattened_snake_case():
    payload = {"delivery_mode": "announce"}
    assert _extract_delivery_mode(payload) == "announce"


def test_extract_delivery_mode_from_flattened_camel_case():
    payload = {"deliveryMode": "webhook"}
    assert _extract_delivery_mode(payload) == "webhook"


def test_extract_delivery_mode_missing_returns_none():
    """Fail-open: frontend falls back to legacy toast behavior on None."""
    assert _extract_delivery_mode({}) is None
    assert _extract_delivery_mode({"name": "job", "status": "completed"}) is None


def test_extract_delivery_mode_nested_delivery_missing_mode():
    """Delivery dict without mode key — still None, no KeyError."""
    assert _extract_delivery_mode({"delivery": {"bestEffort": True}}) is None


def test_cron_completed_metadata_includes_delivery_mode():
    """cron.completed events must surface delivery_mode for NotificationProvider."""
    payload = {
        "name": "competitor-scan",
        "status": "completed",
        "agentId": "waste-gurus-agent",
        "delivery": {"mode": "none", "bestEffort": True},
    }
    event = _normalise_event("cron", payload)
    assert event is not None
    assert event.event_type == "cron.completed"
    assert event.metadata["delivery_mode"] == "none"


def test_cron_completed_real_gateway_payload():
    """Real gateway payload verified via live VPS trace 2026-04-21 session #23.

    Gateway payload keys: action, delivered, deliveryStatus, durationMs, jobId,
    model, nextRunAtMs, provider, runAtMs, sessionId, sessionKey, status,
    summary, usage. Completion signaled by action='finished' AND status='ok'.
    Silent-disk crons (mode=none) land with deliveryStatus='not-delivered'
    because gateway's resolveDeliveryStatus returns that whenever delivered=false.
    """
    payload = {
        "action": "finished",
        "delivered": False,
        "deliveryStatus": "not-delivered",
        "durationMs": 94758,
        "jobId": "da0997df-8e75-43d1-8b19-4189674e57db",
        "status": "ok",
        "summary": "**Email Triage Complete**",
        "sessionKey": "waste-gurus:waste-gurus-agent:cron:abc123",
    }
    event = _normalise_event("cron", payload)
    assert event is not None
    assert event.event_type == "cron.completed"
    assert event.metadata["delivery_mode"] == "none"  # silent-disk → none toast


def test_cron_completed_without_delivery_falls_open():
    """Legacy cron events without delivery metadata still emit an event."""
    payload = {"name": "legacy-job", "status": "completed", "agentId": "a1"}
    event = _normalise_event("cron", payload)
    assert event is not None
    assert event.event_type == "cron.completed"
    assert event.metadata["delivery_mode"] is None


def test_cron_error_includes_delivery_mode():
    """Errors also surface delivery_mode so warning toasts can branch."""
    payload = {
        "name": "failing-job",
        "status": "error",
        "agentId": "a1",
        "error": "timeout",
        "delivery": {"mode": "announce"},
    }
    event = _normalise_event("cron", payload)
    assert event is not None
    assert event.event_type == "cron.error"
    assert event.metadata["delivery_mode"] == "announce"


# ── DeltaBuffer (token-streaming MVP item 71) ─────────────────────────────


def test_delta_buffer_holds_under_threshold():
    """Fewer than 5 tokens, sub-50ms — buffered, no flush."""
    buf = DeltaBuffer()
    assert buf.push("s1", "He", now=0.000) is None
    assert buf.push("s1", "llo", now=0.005) is None
    assert buf.push("s1", " ", now=0.010) is None
    assert buf.pending("s1") == "Hello "


def test_delta_buffer_flushes_at_5_tokens():
    """5th token flushes the accumulated string."""
    buf = DeltaBuffer()
    buf.push("s1", "a", now=0.000)
    buf.push("s1", "b", now=0.001)
    buf.push("s1", "c", now=0.002)
    buf.push("s1", "d", now=0.003)
    flushed = buf.push("s1", "e", now=0.004)
    assert flushed == "abcde"
    assert buf.pending("s1") == ""


def test_delta_buffer_lazy_flushes_on_age_exceeded():
    """If first-token age exceeds 50ms when next event arrives, flush stale buffer first.

    The next push starts a new buffer with its own delta.
    """
    buf = DeltaBuffer()
    buf.push("s1", "stale", now=0.000)
    buf.push("s1", "_data", now=0.020)
    # 70ms after first token — next push should flush the old buffer
    flushed = buf.push("s1", "_NEW", now=0.070)
    assert flushed == "stale_data"
    # New buffer holds only the latest delta
    assert buf.pending("s1") == "_NEW"


def test_delta_buffer_force_flush_on_final():
    """chat:final force-flushes whatever is buffered."""
    buf = DeltaBuffer()
    buf.push("s1", "partial", now=0.000)
    buf.push("s1", " thought", now=0.010)
    flushed = buf.flush("s1")
    assert flushed == "partial thought"
    assert buf.pending("s1") == ""


def test_delta_buffer_force_flush_on_empty_returns_none():
    """flush() on a session with no buffered tokens returns None — nothing to emit."""
    buf = DeltaBuffer()
    assert buf.flush("s1") is None


def test_delta_buffer_isolates_sessions():
    """Each session_key has its own buffer."""
    buf = DeltaBuffer()
    buf.push("s1", "a", now=0.000)
    buf.push("s2", "x", now=0.000)
    buf.push("s1", "b", now=0.001)
    assert buf.pending("s1") == "ab"
    assert buf.pending("s2") == "x"
    flushed = buf.flush("s1")
    assert flushed == "ab"
    # s2 untouched
    assert buf.pending("s2") == "x"


def test_delta_buffer_drop_removes_session_state():
    """drop() clears state for a session_key — used on disconnect or final."""
    buf = DeltaBuffer()
    buf.push("s1", "a", now=0.000)
    buf.drop("s1")
    assert buf.pending("s1") == ""
    # Subsequent push starts fresh (would not flush stale data)
    buf.push("s1", "b", now=10.0)  # huge gap, but no prior state to flush
    assert buf.pending("s1") == "b"
