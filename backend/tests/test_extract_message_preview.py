"""Unit tests for _extract_message_preview.

Documents the real gateway chat history shape:
- Agent turns with tool use produce: [user, assistant(thinking+toolCall),
  toolResult, assistant(text)] — so the last 2 messages are toolResult +
  assistant(text), NOT user + assistant.
- The titler needs enough lookback to find the paired user message across
  tool calls. Tests here lock the required behavior.

Root cause of titler silent-failure (2026-04-15):
  `_fetch_latest_chat` used limit=2. With tool calls, limit=2 returned
  [toolResult, assistant(text)] — no user message, `_extract_message_preview`
  returned ("", assistant_text), titler skipped via `if not user_msg: return`.
"""

from app.services.openclaw.gateway_event_listener import _extract_message_preview


def test_extract_pairs_user_and_assistant_simple():
    """Smoke: direct user→assistant turn (no tool use)."""
    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": "hello test"}],
            "timestamp": 1,
        },
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "Hi! How can I help?"}],
            "timestamp": 2,
        },
    ]
    user, assistant = _extract_message_preview(messages)
    assert user == "hello test"
    assert assistant == "Hi! How can I help?"


def test_extract_skips_tool_result_role_when_looking_for_user():
    """Real-world case that bit us: tool-calling agent produces
    [user, assistant(thinking+toolCall), toolResult, assistant(text)].
    Preview must still pair the text-only user turn with the final
    assistant text, skipping thinking/toolCall/toolResult in between.
    """
    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": "what's the weather"}],
            "timestamp": 1,
        },
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "Need to call a tool", "thinkingSignature": "x"},
                {"type": "toolCall", "id": "t1", "name": "read", "arguments": {"file_path": "BOOTSTRAP.md"}},
            ],
            "timestamp": 2,
        },
        {
            "role": "toolResult",
            "toolCallId": "t1",
            "toolName": "read",
            "content": [{"type": "text", "text": "# BOOTSTRAP.md\n..."}],
            "isError": False,
            "timestamp": 3,
        },
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "The weather is sunny."}],
            "timestamp": 4,
        },
    ]
    user, assistant = _extract_message_preview(messages)
    assert user == "what's the weather", (
        "User message must be found even when tool-call messages are interleaved"
    )
    assert assistant == "The weather is sunny.", (
        "Assistant must resolve to the final text block, not thinking/toolCall content"
    )


def test_extract_returns_empty_user_when_only_tool_messages_present():
    """If the sliced window has no user role, user_msg is empty. This is the
    failure mode that triggered the titler-not-firing bug — when
    `_fetch_latest_chat(limit=2)` returned [toolResult, assistant(text)], the
    user message was out of window and preview returned user=''.
    """
    messages = [
        {
            "role": "toolResult",
            "toolCallId": "t1",
            "toolName": "read",
            "content": [{"type": "text", "text": "..."}],
            "timestamp": 3,
        },
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "Hello!"}],
            "timestamp": 4,
        },
    ]
    user, assistant = _extract_message_preview(messages)
    assert user == "", "No user role in window → empty user_msg (this was the bug)"
    assert assistant == "Hello!"


def test_extract_ignores_assistant_thinking_only_messages():
    """An assistant message whose content is entirely `thinking` blocks yields
    empty text after filtering. The walker must keep looking for a real text
    block, not lock onto the first assistant message it sees.
    """
    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": "hi"}],
            "timestamp": 1,
        },
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "planning", "thinkingSignature": "x"},
                {"type": "text", "text": "Done."},
            ],
            "timestamp": 2,
        },
    ]
    user, assistant = _extract_message_preview(messages)
    assert user == "hi"
    assert assistant == "Done.", "Text block must be extracted even when thinking block precedes it"
