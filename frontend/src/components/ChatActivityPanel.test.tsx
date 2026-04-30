import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatActivityPanel, type LiveSSEEvent } from "./ChatActivityPanel";

function makeEvent(partial: Partial<LiveSSEEvent> = {}): LiveSSEEvent {
  return {
    id: "evt-1",
    event_type: "agent.thinking",
    agent_name: "the-claw",
    channel: "vantage:the-claw:chat-abc",
    message: "Thinking...",
    model: "",
    metadata: {},
    timestamp: new Date().toISOString(),
    ...partial,
  };
}

describe("ChatActivityPanel — token streaming (item 71 MVP)", () => {
  it("renders nothing-special preview when no streaming draft and no events", () => {
    render(
      <ChatActivityPanel
        events={[]}
        isOpen={false}
        onToggle={() => {}}
        agentTyping={false}
      />,
    );
    // Collapsed bar's preview span exists but contains empty string.
    // Just confirm no crash — there's no specific text to assert.
    expect(document.body).toBeInTheDocument();
  });

  it("shows streamingDraft text in collapsed bar when streaming is active", () => {
    render(
      <ChatActivityPanel
        events={[]}
        isOpen={false}
        onToggle={() => {}}
        agentTyping={true}
        streamingDraft="Hello, this is the agent typing..."
      />,
    );
    expect(
      screen.getByText("Hello, this is the agent typing..."),
    ).toBeInTheDocument();
  });

  it("prefers streamingDraft over last event in collapsed preview", () => {
    const events = [
      makeEvent({ event_type: "agent.thinking", message: "Thinking..." }),
    ];
    render(
      <ChatActivityPanel
        events={events}
        isOpen={false}
        onToggle={() => {}}
        agentTyping={true}
        streamingDraft="Mid-stream output"
      />,
    );
    expect(screen.getByText("Mid-stream output")).toBeInTheDocument();
    // The thinking event message should NOT be in the collapsed bar preview.
    // (It can still appear in the expanded list, but isOpen=false here.)
    expect(screen.queryByText("Thinking...")).not.toBeInTheDocument();
  });

  it("renders streaming block at top of expanded panel with Streaming label", () => {
    render(
      <ChatActivityPanel
        events={[]}
        isOpen={true}
        onToggle={() => {}}
        agentTyping={true}
        streamingDraft="Live tokens here"
      />,
    );
    expect(screen.getByText("Streaming")).toBeInTheDocument();
    // Streaming text appears twice when expanded: once in the collapsed-bar
    // preview (always rendered) and once inside the expanded streaming block.
    const matches = screen.getAllByText("Live tokens here");
    expect(matches.length).toBe(2);
  });

  it("hides 'Waiting for agent activity' placeholder when streaming alone", () => {
    render(
      <ChatActivityPanel
        events={[]}
        isOpen={true}
        onToggle={() => {}}
        agentTyping={true}
        streamingDraft="Something is happening"
      />,
    );
    expect(
      screen.queryByText(/Waiting for agent activity/i),
    ).not.toBeInTheDocument();
  });

  it("shows 'Waiting for agent activity' when expanded with no events and no draft", () => {
    render(
      <ChatActivityPanel
        events={[]}
        isOpen={true}
        onToggle={() => {}}
        agentTyping={false}
      />,
    );
    expect(screen.getByText(/Waiting for agent activity/i)).toBeInTheDocument();
  });

  it("renders streaming block AND existing events when both are present", () => {
    const events = [
      makeEvent({
        id: "e1",
        event_type: "agent.tool_call",
        message: "Using tool: fetch-url",
      }),
    ];
    render(
      <ChatActivityPanel
        events={events}
        isOpen={true}
        onToggle={() => {}}
        agentTyping={true}
        streamingDraft="Drafting reply..."
      />,
    );
    expect(screen.getByText("Streaming")).toBeInTheDocument();
    // Streaming text shows in collapsed-bar preview + expanded block (2 places).
    expect(screen.getAllByText("Drafting reply...").length).toBe(2);
    // Existing tool-call event still renders in the events list.
    expect(screen.getByText("Using tool: fetch-url")).toBeInTheDocument();
  });

  it("falls back to last event preview when streamingDraft is empty string", () => {
    const events = [
      makeEvent({ event_type: "agent.thinking", message: "Thinking..." }),
    ];
    render(
      <ChatActivityPanel
        events={events}
        isOpen={false}
        onToggle={() => {}}
        agentTyping={true}
        streamingDraft=""
      />,
    );
    expect(screen.getByText("Thinking...")).toBeInTheDocument();
  });

  it("passes onToggle through to the collapsed-bar button", async () => {
    const onToggle = vi.fn();
    render(
      <ChatActivityPanel
        events={[]}
        isOpen={false}
        onToggle={onToggle}
        agentTyping={false}
        streamingDraft="hi"
      />,
    );
    const button = screen.getByRole("button");
    button.click();
    expect(onToggle).toHaveBeenCalledOnce();
  });
});
