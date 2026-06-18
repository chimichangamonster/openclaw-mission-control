import { describe, expect, it } from "vitest";
import { unreadSessionKeyFromEvent } from "./NotificationProvider";

// Regression lock for the chat unread-tracking firing path. The original bug
// (caught 2026-06): the gateway listener emits `agent.responded` with the
// session key in `channel`, but the SSE handler read `metadata.sessionKey`
// (always undefined) — so the unread badge + chat-sidebar dot never lit up.
// These cases lock the field source + the event-type filter so the silent
// failure cannot return. Per feedback_test_before_deploy.md.
describe("unreadSessionKeyFromEvent", () => {
  it("marks the session unread from `channel` on agent.responded", () => {
    const key = unreadSessionKeyFromEvent(
      {
        event_type: "agent.responded",
        channel: "org:board:chat-abcd",
        metadata: { runId: "r1", hasMessage: true },
      },
      null,
    );
    expect(key).toBe("org:board:chat-abcd");
  });

  it("excludes the session the user is actively viewing", () => {
    const key = unreadSessionKeyFromEvent(
      { event_type: "agent.responded", channel: "org:board:chat-abcd" },
      "org:board:chat-abcd",
    );
    expect(key).toBeNull();
  });

  it("ignores cron.completed (substring 'completed' must not match)", () => {
    const key = unreadSessionKeyFromEvent(
      { event_type: "cron.completed", channel: "org:cron:isolated-xyz" },
      null,
    );
    expect(key).toBeNull();
  });

  it("ignores token deltas, thinking, and tool calls", () => {
    for (const event_type of ["agent.token_delta", "agent.thinking", "agent.tool_call"]) {
      expect(
        unreadSessionKeyFromEvent({ event_type, channel: "org:board:chat-abcd" }, null),
      ).toBeNull();
    }
  });

  it("falls back to metadata.sessionKey when channel is absent", () => {
    const key = unreadSessionKeyFromEvent(
      { event_type: "agent.responded", metadata: { sessionKey: "org:board:chat-zzzz" } },
      null,
    );
    expect(key).toBe("org:board:chat-zzzz");
  });

  it("returns null when no session key is present anywhere", () => {
    expect(
      unreadSessionKeyFromEvent({ event_type: "agent.responded", metadata: {} }, null),
    ).toBeNull();
  });
});
