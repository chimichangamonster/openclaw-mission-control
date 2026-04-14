import { describe, expect, it } from "vitest";

import type { LiveSSEEvent } from "@/components/ChatActivityPanel";

import { shouldAcceptActivityEvent } from "./activity-filter";

function mkEvent(overrides: Partial<LiveSSEEvent> = {}): LiveSSEEvent {
  return {
    id: "evt-1",
    event_type: "agent.responded",
    agent_name: "the-claw",
    channel: "org:the-claw:chat-abc",
    message: "Agent responded",
    model: "",
    metadata: {},
    timestamp: "2026-04-14T20:00:00Z",
    ...overrides,
  };
}

describe("shouldAcceptActivityEvent", () => {
  const activeKey = "org:the-claw:chat-abc";

  it("accepts events whose channel matches the active session", () => {
    expect(shouldAcceptActivityEvent(mkEvent(), activeKey)).toBe(true);
  });

  it("rejects events from a different chat session on the same org", () => {
    const other = mkEvent({ channel: "org:the-claw:chat-different" });
    expect(shouldAcceptActivityEvent(other, activeKey)).toBe(false);
  });

  it("rejects cron events (channel is empty or job name)", () => {
    const cronEmpty = mkEvent({ event_type: "cron.started", channel: "" });
    const cronNamed = mkEvent({ event_type: "cron.completed", channel: "morning-scan" });
    expect(shouldAcceptActivityEvent(cronEmpty, activeKey)).toBe(false);
    expect(shouldAcceptActivityEvent(cronNamed, activeKey)).toBe(false);
  });

  it("rejects events from a different agent on the same gateway", () => {
    // Personal trading agent events leaking into a Vantage chat view.
    const stockAgent = mkEvent({
      agent_name: "stock-analyst",
      channel: "personal:stock-analyst:main",
    });
    expect(shouldAcceptActivityEvent(stockAgent, activeKey)).toBe(false);
  });

  it("rejects everything when no session is active", () => {
    expect(shouldAcceptActivityEvent(mkEvent(), null)).toBe(false);
    expect(shouldAcceptActivityEvent(mkEvent({ channel: "" }), null)).toBe(false);
  });

  it("treats empty string activeKey the same as null (reject)", () => {
    // Covers the case where sessionKey hasn't resolved yet
    expect(shouldAcceptActivityEvent(mkEvent(), "")).toBe(false);
  });

  it("accepts events for the main agent session (not just chat-*)", () => {
    // The Claw's main session has key like "org:the-claw:main"
    const mainKey = "vantage:the-claw:main";
    const evt = mkEvent({ channel: mainKey });
    expect(shouldAcceptActivityEvent(evt, mainKey)).toBe(true);
  });
});
