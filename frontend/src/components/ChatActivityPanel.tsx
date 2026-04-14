"use client";

import { useEffect, useRef } from "react";
import {
  Activity,
  Brain,
  Cog,
  Terminal,
  MessageSquare,
  CheckCircle2,
  ChevronUp,
  ChevronDown,
  Square,
} from "lucide-react";
import { cn } from "@/lib/utils";

export interface LiveSSEEvent {
  id: string;
  event_type: string;
  agent_name: string;
  channel: string;
  message: string;
  model: string;
  metadata: Record<string, unknown>;
  timestamp: string;
}

interface ChatActivityPanelProps {
  events: LiveSSEEvent[];
  isOpen: boolean;
  onToggle: () => void;
  onAbort?: () => void;
  agentTyping: boolean;
}

function eventIcon(eventType: string) {
  if (eventType.includes("thinking"))
    return <Brain className="h-3.5 w-3.5 shrink-0 text-purple-500" />;
  if (eventType.includes("working"))
    return <Cog className="h-3.5 w-3.5 shrink-0 text-blue-500 animate-spin" />;
  if (eventType.includes("tool_call"))
    return <Terminal className="h-3.5 w-3.5 shrink-0 text-amber-500" />;
  if (eventType.includes("responded"))
    return <MessageSquare className="h-3.5 w-3.5 shrink-0 text-emerald-500" />;
  if (eventType.includes("completed"))
    return <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-500" />;
  return <Activity className="h-3.5 w-3.5 shrink-0 text-[color:var(--text-quiet)]" />;
}

function safeMessage(value: unknown): string {
  if (typeof value === "string") return value;
  if (value == null) return "";
  try { return JSON.stringify(value); } catch { return ""; }
}

function formatEventType(eventType: string): string {
  if (eventType.includes("thinking")) return "Thinking...";
  if (eventType.includes("working")) return "Working...";
  if (eventType.includes("tool_call")) return "Running tool...";
  if (eventType.includes("responded")) return "Responded";
  if (eventType.includes("completed")) return "Completed";
  return eventType.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  if (diff < 5000) return "now";
  if (diff < 60000) return `${Math.floor(diff / 1000)}s`;
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m`;
  return `${Math.floor(diff / 3600000)}h`;
}

export function ChatActivityPanel({
  events,
  isOpen,
  onToggle,
  onAbort,
  agentTyping,
}: ChatActivityPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (isOpen && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events.length, isOpen]);

  const lastEvent = events.length > 0 ? events[events.length - 1] : null;
  const lastMessage = lastEvent
    ? safeMessage(lastEvent.message) || formatEventType(lastEvent.event_type)
    : agentTyping
      ? "Agent is working..."
      : "";

  return (
    <div
      className={cn(
        "border-t border-[color:var(--border)] bg-[color:var(--surface-muted)] transition-all duration-300",
        agentTyping && "border-t-blue-500/40",
      )}
    >
      {/* Collapsed bar — always visible */}
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-4 py-1.5 text-left hover:bg-[color:var(--surface)] transition"
      >
        <Activity className={cn(
          "h-3.5 w-3.5",
          agentTyping ? "text-blue-500 animate-pulse" : "text-[color:var(--text-quiet)]",
        )} />
        <span className="flex-1 truncate text-xs text-[color:var(--text-quiet)]">
          {lastMessage}
        </span>
        {events.length > 0 && (
          <span className="rounded-full bg-[color:var(--surface)] px-1.5 py-0.5 text-[10px] tabular-nums text-[color:var(--text-quiet)]">
            {events.length}
          </span>
        )}
        {agentTyping && onAbort && (
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => { e.stopPropagation(); onAbort(); }}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); onAbort(); } }}
            className="flex items-center gap-1 rounded-md bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-medium text-rose-500 hover:bg-rose-500/20 transition"
            title="Stop response"
          >
            <Square className="h-2.5 w-2.5 fill-current" />
            Stop
          </span>
        )}
        {isOpen ? (
          <ChevronDown className="h-3.5 w-3.5 text-[color:var(--text-quiet)]" />
        ) : (
          <ChevronUp className="h-3.5 w-3.5 text-[color:var(--text-quiet)]" />
        )}
      </button>

      {/* Expanded event list */}
      {isOpen && (
        <div
          ref={scrollRef}
          className="max-h-36 overflow-y-auto border-t border-[color:var(--border)] sm:max-h-48"
        >
          {events.length === 0 ? (
            <div className="px-4 py-3 text-center text-xs text-[color:var(--text-quiet)]">
              Waiting for agent activity...
            </div>
          ) : (
            <div className="divide-y divide-[color:var(--border)]">
              {events.map((event, idx) => (
                <div
                  key={`${event.id}-${idx}`}
                  className="flex items-center gap-2 px-4 py-1.5"
                >
                  {eventIcon(event.event_type)}
                  <span className="flex-1 truncate text-xs text-[color:var(--text)]">
                    {safeMessage(event.message) || formatEventType(event.event_type)}
                  </span>
                  <span className="shrink-0 text-[10px] tabular-nums text-[color:var(--text-quiet)]">
                    {timeAgo(event.timestamp)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
