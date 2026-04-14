"""Tests for _coerce_preview_text in gateway_event_listener.

Locks in the fix for the ChatActivityPanel bug where raw ChatMessage objects
(shape ``{role, content, timestamp}`` with content as string or content-blocks
array) were being passed into ``LiveActivityEvent.message`` and leaked to the
SSE stream as JSON strings the panel rendered verbatim.
"""

from app.services.openclaw.gateway_event_listener import _coerce_preview_text


def test_string_passes_through():
    assert _coerce_preview_text("hello") == "hello"


def test_empty_string():
    assert _coerce_preview_text("") == ""


def test_none_returns_empty():
    assert _coerce_preview_text(None) == ""


def test_dict_with_string_content():
    msg = {"role": "assistant", "content": "Hello there", "timestamp": "2026-04-14T20:00:00Z"}
    assert _coerce_preview_text(msg) == "Hello there"


def test_dict_with_content_blocks_array():
    msg = {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "First part."},
            {"type": "tool_use", "name": "fetch-url"},
            {"type": "text", "text": "Second part."},
        ],
        "timestamp": "2026-04-14T20:00:00Z",
    }
    # Only text blocks join, tool_use dropped
    assert _coerce_preview_text(msg) == "First part. Second part."


def test_dict_with_only_non_text_blocks():
    msg = {
        "role": "assistant",
        "content": [
            {"type": "tool_use", "name": "fetch-url", "input": {"url": "..."}},
            {"type": "thinking", "text": "pondering..."},
        ],
    }
    # No text blocks, no preview string — caller substitutes clean label
    assert _coerce_preview_text(msg) == ""


def test_dict_without_content_key():
    assert _coerce_preview_text({"role": "assistant", "timestamp": "..."}) == ""


def test_unknown_shape_returns_empty():
    assert _coerce_preview_text(42) == ""
    assert _coerce_preview_text([1, 2, 3]) == ""
    assert _coerce_preview_text({"foo": "bar"}) == ""
