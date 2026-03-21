"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, Radio, Cpu, MessageSquare, Zap, Clock, Wifi, WifiOff } from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { customFetch } from "@/api/mutator";
import { cn } from "@/lib/utils";

interface AgentSession {
  key: string;
  channel: string;
  agent: string;
  model: string;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  updatedAt: number;
  abortedLastRun: boolean;
  systemSent: boolean;
}

interface ActivityEvent {
  id: string;
  timestamp: number;
  agent: string;
  channel: string;
  model: string;
  type: "active" | "idle" | "heartbeat" | "new_session" | "thinking" | "tool_call" | "responded" | "cron" | "approval" | "gateway";
  message: string;
  fullMessage?: string;
  tokenDelta: number;
}

interface LiveSSEEvent {
  id: string;
  event_type: string;
  agent_name: string;
  channel: string;
  message: string;
  model: string;
  metadata: Record<string, unknown>;
  timestamp: string;
}

function timeAgo(ts: number): string {
  const diff = Date.now() - ts;
  if (diff < 5000) return "just now";
  if (diff < 60000) return `${Math.floor(diff / 1000)}s ago`;
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  return `${Math.floor(diff / 3600000)}h ago`;
}

function agentColor(agent: string): string {
  if (agent.includes("the-claw") || agent === "main") return "bg-blue-500";
  if (agent.includes("market-scout")) return "bg-purple-500";
  if (agent.includes("sports-analyst")) return "bg-emerald-500";
  if (agent.includes("stock-analyst")) return "bg-amber-500";
  if (agent.includes("notification")) return "bg-rose-500";
  if (agent.includes("lead") || agent.includes("gateway")) return "bg-slate-400";
  return "bg-slate-500";
}

function agentDotColor(agent: string): string {
  if (agent.includes("the-claw") || agent === "main") return "bg-blue-400";
  if (agent.includes("market-scout")) return "bg-purple-400";
  if (agent.includes("sports-analyst")) return "bg-emerald-400";
  if (agent.includes("stock-analyst")) return "bg-amber-400";
  return "bg-slate-400";
}

function agentName(agent: string): string {
  if (agent.includes("the-claw") || agent === "main") return "The Claw";
  if (agent.includes("market-scout")) return "Market Scout";
  if (agent.includes("sports-analyst")) return "Sports Analyst";
  if (agent.includes("stock-analyst")) return "Stock Analyst";
  if (agent.includes("notification")) return "Notifications";
  if (agent.includes("lead")) return "Lead Agent";
  if (agent.includes("mc-gateway")) return "Gateway Agent";
  return agent;
}

export default function LivePage() {
  const { isSignedIn } = useAuth();
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [lastPoll, setLastPoll] = useState(0);
  const [expandedEvents, setExpandedEvents] = useState<Set<string>>(new Set());
  const prevSessionsRef = useRef<Map<string, AgentSession>>(new Map());
  const eventIdRef = useRef(0);

  // SSE stream for real-time gateway events
  const sseRef = useRef<EventSource | null>(null);
  useEffect(() => {
    if (!isSignedIn) return;
    const token = typeof window !== "undefined" ? localStorage.getItem("auth_token") || "" : "";
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || "";
    const url = `${baseUrl}/api/v1/activity/live/stream?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);
    sseRef.current = es;

    es.addEventListener("activity", (e) => {
      try {
        const data: LiveSSEEvent = JSON.parse(e.data);
        const eventType = data.event_type || "";
        let type: ActivityEvent["type"] = "active";
        if (eventType.includes("thinking")) type = "thinking";
        else if (eventType.includes("tool_call")) type = "tool_call";
        else if (eventType.includes("responded") || eventType.includes("completed")) type = "responded";
        else if (eventType.includes("cron")) type = "cron";
        else if (eventType.includes("approval")) type = "approval";
        else if (eventType.includes("gateway") || eventType.includes("disconnect") || eventType.includes("connect")) type = "gateway";
        else if (eventType.includes("message_received")) type = "active";
        else if (eventType.includes("presence")) type = "idle";

        const newEvent: ActivityEvent = {
          id: data.id || String(eventIdRef.current++),
          timestamp: data.timestamp ? new Date(data.timestamp).getTime() : Date.now(),
          agent: data.agent_name || "unknown",
          channel: data.channel || "",
          model: data.model || "",
          type,
          message: data.message || eventType,
          tokenDelta: 0,
        };
        setEvents((prev) => [newEvent, ...prev].slice(0, 100));
      } catch { /* ignore parse errors */ }
    });

    es.onerror = () => {
      // EventSource auto-reconnects
    };

    return () => {
      es.close();
      sseRef.current = null;
    };
  }, [isSignedIn]);

  const poll = useCallback(async () => {
    try {
      const boardId = "fc95c061-3c32-4c82-a87d-9e21225e59fd";
      const raw: any = await customFetch(`/api/v1/gateways/status?board_id=${boardId}`, { method: "GET" });
      const data = raw?.data ?? raw;

      setConnected(data?.connected ?? false);
      setLastPoll(Date.now());

      const newSessions: AgentSession[] = (data?.sessions || []).map((s: any) => {
        const key = s.key || "";
        const agentId = key.split(":")[1] || "unknown";
        return {
          key,
          channel: s.groupChannel || s.displayName || "direct",
          agent: agentId,
          model: (s.model || "").split("/").pop() || "unknown",
          inputTokens: s.inputTokens || 0,
          outputTokens: s.outputTokens || 0,
          totalTokens: s.totalTokens || 0,
          updatedAt: s.updatedAt || 0,
          abortedLastRun: s.abortedLastRun || false,
          systemSent: s.systemSent || false,
        };
      });

      setSessions(newSessions);

      // Detect changes and generate events
      const prevMap = prevSessionsRef.current;
      const newEvents: ActivityEvent[] = [];

      for (const session of newSessions) {
        const prev = prevMap.get(session.key);
        if (!prev) {
          if (prevMap.size > 0) {
            newEvents.push({
              id: String(eventIdRef.current++),
              timestamp: Date.now(),
              agent: session.agent,
              channel: session.channel,
              model: session.model,
              type: "new_session",
              message: `New session started in ${session.channel}`,
              tokenDelta: 0,
            });
          }
        } else if (session.totalTokens !== prev.totalTokens) {
          const delta = session.totalTokens - prev.totalTokens;
          const isActive = Date.now() - session.updatedAt < 30000;

          // Fetch latest chat content (zero LLM cost — just reads session log)
          let chatMsg = "";
          let chatFull = "";
          try {
            const historyRaw: any = await customFetch(
              `/api/v1/gateways/sessions/${encodeURIComponent(session.key)}/history?board_id=${boardId}&limit=2`,
              { method: "GET" }
            );
            const history = historyRaw?.data ?? historyRaw;
            const messages = Array.isArray(history) ? history : (history?.messages || history?.history || []);
            for (let i = messages.length - 1; i >= 0; i--) {
              const m = messages[i];
              const role = m?.role || "";
              let content = m?.content || m?.text || "";
              if (Array.isArray(content)) {
                content = content.filter((p: any) => p?.type === "text").map((p: any) => p?.text || "").join(" ");
              }
              if (typeof content === "string" && content.trim()) {
                const full = content.trim();
                const prefix = (role === "assistant" || role === "model") ? "💬" : "📩";
                chatFull = `${prefix} ${full}`;
                chatMsg = full.length > 500 ? `${prefix} ${full.slice(0, 500)}...` : chatFull;
                break;
              }
            }
          } catch { /* ignore — chat history is best-effort */ }

          newEvents.push({
            id: String(eventIdRef.current++),
            timestamp: session.updatedAt,
            agent: session.agent,
            channel: session.channel,
            model: session.model,
            type: isActive ? "active" : "idle",
            message: chatMsg || (isActive
              ? `Processing in ${session.channel} (+${delta.toLocaleString()} tokens)`
              : `Completed task in ${session.channel}`),
            fullMessage: chatFull && chatFull !== chatMsg ? chatFull : undefined,
            tokenDelta: delta,
          });
        }
      }

      if (newEvents.length > 0) {
        setEvents((prev) => [...newEvents, ...prev].slice(0, 50));
      }

      const newMap = new Map<string, AgentSession>();
      for (const s of newSessions) {
        newMap.set(s.key, s);
      }
      prevSessionsRef.current = newMap;
    } catch {
      setConnected(false);
    }
  }, []);

  useEffect(() => {
    if (!isSignedIn) return;
    poll();
    const interval = setInterval(poll, 3000);
    return () => clearInterval(interval);
  }, [isSignedIn, poll]);

  const discordSessions = sessions.filter((s) => s.key.includes("discord") || s.key.includes("the-claw") || s.key.includes("market-scout") || s.key.includes("sports-analyst") || s.key.includes("stock-analyst"));

  return (
    <DashboardPageLayout
      signedOut={{ message: "Sign in to view live activity.", forceRedirectUrl: "/live", signUpForceRedirectUrl: "/live" }}
      title="Live Activity"
      description="Real-time agent activity and gateway status."
    >
      <div className="space-y-6">
        {/* Connection Status Bar */}
        <div className={cn(
          "flex items-center justify-between rounded-lg px-4 py-2 text-sm",
          connected ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
        )}>
          <div className="flex items-center gap-2">
            {connected ? <Wifi className="h-4 w-4" /> : <WifiOff className="h-4 w-4" />}
            {connected ? "Gateway connected" : "Gateway disconnected"}
            <span className="text-xs opacity-60">
              {lastPoll > 0 ? `Polling every 3s  •  Last: ${timeAgo(lastPoll)}` : ""}
            </span>
          </div>
          <div className="flex items-center gap-3 text-xs">
            <span>{sessions.length} sessions</span>
            <span className="flex items-center gap-1">
              <span className="relative flex h-2 w-2">
                <span className={cn(
                  "absolute inline-flex h-full w-full rounded-full opacity-75",
                  connected ? "animate-ping bg-emerald-400" : "bg-red-400"
                )} />
                <span className={cn(
                  "relative inline-flex h-2 w-2 rounded-full",
                  connected ? "bg-emerald-500" : "bg-red-500"
                )} />
              </span>
              Live
            </span>
          </div>
        </div>

        {/* Agent Cards */}
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
          {discordSessions.map((session) => {
            const isActive = Date.now() - session.updatedAt < 60000;
            const isWorking = Date.now() - session.updatedAt < 15000;
            return (
              <div
                key={session.key}
                className={cn(
                  "relative overflow-hidden rounded-xl border bg-white p-4 shadow-sm transition-all duration-500",
                  isWorking ? "border-blue-300 shadow-blue-100 shadow-md" : "border-slate-200",
                )}
              >
                {isWorking && (
                  <div className="absolute inset-0 animate-pulse bg-gradient-to-r from-blue-50/50 to-transparent pointer-events-none" />
                )}

                <div className="relative flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    <div className={cn("h-3 w-3 rounded-full", agentColor(session.agent))} />
                    <span className="text-sm font-semibold text-slate-900">
                      {agentName(session.agent)}
                    </span>
                  </div>
                  <div className={cn(
                    "flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium transition-all",
                    isWorking ? "bg-blue-100 text-blue-700 animate-pulse" :
                    isActive ? "bg-emerald-100 text-emerald-700" :
                    "bg-slate-100 text-slate-500"
                  )}>
                    {isWorking ? (
                      <><Zap className="h-3 w-3" /> Working</>
                    ) : isActive ? (
                      <><Activity className="h-3 w-3" /> Active</>
                    ) : (
                      <><Clock className="h-3 w-3" /> Idle</>
                    )}
                  </div>
                </div>

                <div className="relative mt-3 space-y-1 text-xs text-slate-500">
                  <div className="flex items-center gap-1">
                    <MessageSquare className="h-3 w-3" />
                    {session.channel}
                  </div>
                  <div className="flex items-center gap-1">
                    <Cpu className="h-3 w-3" />
                    <span className="font-mono">{session.model}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Radio className="h-3 w-3" />
                    {session.totalTokens.toLocaleString()} tokens
                  </div>
                  <div className="text-slate-400">
                    {timeAgo(session.updatedAt)}
                  </div>
                </div>
              </div>
            );
          })}
          {discordSessions.length === 0 && (
            <div className="col-span-4 rounded-xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-400">
              No active agent sessions. Send a message in Discord to see agents appear.
            </div>
          )}
        </div>

        {/* Activity Timeline */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 px-4 py-3">
            <h3 className="text-sm font-semibold text-slate-900">Activity Timeline</h3>
            <p className="text-xs text-slate-500">Real-time gateway events via SSE + session polling</p>
          </div>
          <div className="max-h-[500px] overflow-y-auto">
            {events.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-slate-400">
                <div className="relative mb-4">
                  <Activity className="h-10 w-10 opacity-30" />
                  <span className="absolute -right-1 -top-1 flex h-3 w-3">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
                    <span className="relative inline-flex h-3 w-3 rounded-full bg-blue-500" />
                  </span>
                </div>
                <p className="text-sm font-medium">Listening for agent activity...</p>
                <p className="mt-1 text-xs">Send a message in Discord to see events appear here in real-time</p>
              </div>
            ) : (
              <div className="divide-y divide-slate-50">
                {events.map((event, idx) => (
                  <div
                    key={event.id}
                    className={cn(
                      "flex items-start gap-3 px-4 py-3 transition-all duration-300",
                      event.type === "active" ? "bg-blue-50/30" : "",
                      idx === 0 ? "animate-[slideDown_0.3s_ease-out]" : "",
                    )}
                  >
                    <div className="mt-1 flex flex-col items-center gap-1">
                      <div className={cn("h-2.5 w-2.5 rounded-full ring-2 ring-white", agentColor(event.agent))} />
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-medium text-slate-900">
                          {agentName(event.agent)}
                        </span>
                        <span className={cn(
                          "rounded-full px-1.5 py-0.5 text-[10px] font-semibold tracking-wide",
                          event.type === "active" ? "bg-blue-100 text-blue-700" :
                          event.type === "thinking" ? "bg-yellow-100 text-yellow-700" :
                          event.type === "tool_call" ? "bg-orange-100 text-orange-700" :
                          event.type === "responded" ? "bg-emerald-100 text-emerald-700" :
                          event.type === "cron" ? "bg-indigo-100 text-indigo-700" :
                          event.type === "approval" ? "bg-pink-100 text-pink-700" :
                          event.type === "gateway" ? "bg-slate-200 text-slate-600" :
                          event.type === "new_session" ? "bg-purple-100 text-purple-700" :
                          event.type === "idle" ? "bg-emerald-100 text-emerald-700" :
                          "bg-slate-100 text-slate-500"
                        )}>
                          {event.type === "active" ? "WORKING" :
                           event.type === "thinking" ? "THINKING" :
                           event.type === "tool_call" ? "TOOL CALL" :
                           event.type === "responded" ? "RESPONDED" :
                           event.type === "cron" ? "CRON" :
                           event.type === "approval" ? "APPROVAL" :
                           event.type === "gateway" ? "GATEWAY" :
                           event.type === "new_session" ? "NEW SESSION" :
                           event.type === "idle" ? "COMPLETED" : "EVENT"}
                        </span>
                        <span className="text-[10px] text-slate-400">
                          {new Date(event.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <div
                        className={cn(
                          "mt-0.5 text-xs text-slate-600",
                          event.fullMessage ? "cursor-pointer hover:text-slate-900" : "",
                        )}
                        onClick={() => {
                          if (!event.fullMessage) return;
                          setExpandedEvents((prev) => {
                            const next = new Set(prev);
                            if (next.has(event.id)) next.delete(event.id);
                            else next.add(event.id);
                            return next;
                          });
                        }}
                      >
                        <p className="whitespace-pre-wrap">
                          {expandedEvents.has(event.id) && event.fullMessage
                            ? event.fullMessage
                            : event.message}
                        </p>
                        {event.fullMessage && (
                          <span className="text-[10px] text-blue-500 hover:underline">
                            {expandedEvents.has(event.id) ? "collapse" : "expand full message"}
                          </span>
                        )}
                      </div>
                      <div className="mt-1 flex items-center gap-3 text-[10px] text-slate-400">
                        <span className="font-mono">{event.model}</span>
                        {event.tokenDelta > 0 && (
                          <span className="font-semibold text-blue-500">+{event.tokenDelta.toLocaleString()} tokens</span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </DashboardPageLayout>
  );
}
