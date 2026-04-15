"""Tests for _normalise_event against the real gateway schema.

Covers chat state transitions (delta/final/error) and agent stream types
(lifecycle/tool/assistant/error) observed in production gateway logs.
Locks in the 2026-04-14 schema fix that replaced the fantasy
``direction="inbound/outbound"`` / ``state="thinking/done"`` guesses.
"""

from app.services.openclaw.gateway_event_listener import _is_default_label, _normalise_event

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


def test_chat_delta_skipped():
    """Delta tokens flood the panel — must return None."""
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
