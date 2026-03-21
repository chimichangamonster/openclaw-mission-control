"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  Radio,
  Cpu,
  MessageSquare,
  Zap,
  Clock,
  Wifi,
  WifiOff,
  ChevronDown,
  ChevronUp,
  DollarSign,
  Timer,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Bot,
  RefreshCw,
} from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { customFetch } from "@/api/mutator";
import { cn } from "@/lib/utils";

// ─── Types ───────────────────────────────────────────────────────────────────

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

interface ModelUsage {
  model: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost: number;
  session_count: number;
  agents: string[];
  tier: string;
}

interface CronJob {
  id: string;
  name: string;
  description: string;
  agent_id: string;
  enabled: boolean;
  schedule_type: string;
  schedule_expr: string;
  timezone: string;
  next_run: string | null;
  last_run: string | null;
  last_status: string | null;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const BOARD_ID = "fc95c061-3c32-4c82-a87d-9e21225e59fd";

const AGENTS: Record<string, { name: string; color: string; dotColor: string; tierDefault: string; channelDefault: string }> = {
  "the-claw":       { name: "The Claw",       color: "bg-blue-500",    dotColor: "bg-blue-400",    tierDefault: "Tier 3", channelDefault: "#general" },
  "main":           { name: "The Claw",       color: "bg-blue-500",    dotColor: "bg-blue-400",    tierDefault: "Tier 3", channelDefault: "#general" },
  "market-scout":   { name: "Market Scout",   color: "bg-purple-500",  dotColor: "bg-purple-400",  tierDefault: "Tier 2", channelDefault: "#prediction-markets" },
  "sports-analyst": { name: "Sports Analyst", color: "bg-emerald-500", dotColor: "bg-emerald-400", tierDefault: "Tier 3", channelDefault: "#sports-betting" },
  "stock-analyst":  { name: "Stock Analyst",  color: "bg-amber-500",   dotColor: "bg-amber-400",   tierDefault: "Tier 2", channelDefault: "#stonks" },
  "notification":   { name: "Notifications",  color: "bg-rose-500",    dotColor: "bg-rose-400",    tierDefault: "Tier 1", channelDefault: "#notifications" },
};

function getAgent(id: string) {
  for (const [key, val] of Object.entries(AGENTS)) {
    if (id.includes(key)) return val;
  }
  return { name: id, color: "bg-slate-500", dotColor: "bg-slate-400", tierDefault: "", channelDefault: "" };
}

function timeAgo(ts: number): string {
  const diff = Date.now() - ts;
  if (diff < 5000) return "just now";
  if (diff < 60000) return `${Math.floor(diff / 1000)}s ago`;
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  return `${Math.floor(diff / 3600000)}h ago`;
}

function timeUntil(iso: string | null): string {
  if (!iso) return "";
  const diff = new Date(iso).getTime() - Date.now();
  if (diff < 0) return "overdue";
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `in ${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `in ${hours}h ${mins % 60}m`;
  return `in ${Math.floor(hours / 24)}d`;
}

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

const FALLBACK_PRICING: Record<string, { prompt: number; completion: number }> = {
  "claude-sonnet-4": { prompt: 3.0, completion: 15.0 },
  "deepseek-v3.2": { prompt: 0.26, completion: 0.38 },
  "grok-4": { prompt: 3.0, completion: 15.0 },
  "gemini-2.5-flash": { prompt: 0.3, completion: 2.5 },
  "gpt-5-nano": { prompt: 0.05, completion: 0.4 },
};

function estimateCost(model: string, inputTokens: number, outputTokens: number): string {
  const short = model.split("/").pop() || model;
  const fb = FALLBACK_PRICING[short];
  if (!fb) return "$0.0000";
  const cost = (inputTokens / 1_000_000) * fb.prompt + (outputTokens / 1_000_000) * fb.completion;
  return `$${cost.toFixed(4)}`;
}

function tierFromModel(model: string): { label: string; color: string } {
  const short = model.split("/").pop() || model;
  if (short.includes("opus")) return { label: "Tier 4", color: "bg-red-100 text-red-700" };
  if (short.includes("sonnet") || short.includes("grok-4")) return { label: "Tier 3", color: "bg-purple-100 text-purple-700" };
  if (short.includes("deepseek")) return { label: "Tier 2", color: "bg-blue-100 text-blue-700" };
  if (short.includes("nano") || short.includes("grok-4-fast") || short.includes("flash")) return { label: "Tier 1", color: "bg-emerald-100 text-emerald-700" };
  return { label: "—", color: "bg-slate-100 text-slate-500" };
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function LivePage() {
  const { isSignedIn } = useAuth();

  // Core state
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [lastPoll, setLastPoll] = useState(0);
  const [expandedEvents, setExpandedEvents] = useState<Set<string>>(new Set());
  const prevSessionsRef = useRef<Map<string, AgentSession>>(new Map());
  const eventIdRef = useRef(0);

  // Agent detail panel
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);
  const [modelUsage, setModelUsage] = useState<ModelUsage[]>([]);

  // Cron jobs
  const [cronJobs, setCronJobs] = useState<CronJob[]>([]);
  const [cronLoading, setCronLoading] = useState(true);

  // Error log
  const [errorEvents, setErrorEvents] = useState<any[]>([]);
  const [showErrors, setShowErrors] = useState(false);

  // ─── SSE stream ──────────────────────────────────────────────────────────

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

    es.onerror = () => { /* EventSource auto-reconnects */ };

    return () => {
      es.close();
      sseRef.current = null;
    };
  }, [isSignedIn]);

  // ─── Poll gateway sessions ───────────────────────────────────────────────

  const poll = useCallback(async () => {
    try {
      const raw: any = await customFetch(`/api/v1/gateways/status?board_id=${BOARD_ID}`, { method: "GET" });
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

          let chatMsg = "";
          let chatFull = "";
          try {
            const historyRaw: any = await customFetch(
              `/api/v1/gateways/sessions/${encodeURIComponent(session.key)}/history?board_id=${BOARD_ID}&limit=2`,
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
                const prefix = (role === "assistant" || role === "model") ? "\u{1F4AC}" : "\u{1F4E9}";
                chatFull = `${prefix} ${full}`;
                chatMsg = full.length > 500 ? `${prefix} ${full.slice(0, 500)}...` : chatFull;
                break;
              }
            }
          } catch { /* chat history is best-effort */ }

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
      for (const s of newSessions) newMap.set(s.key, s);
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

  // ─── Load model usage (for agent detail panel) ───────────────────────────

  const loadModelUsage = useCallback(async () => {
    try {
      const raw: any = await customFetch("/api/v1/cost-tracker/usage-by-model", { method: "GET" });
      const data = raw?.data ?? raw;
      if (data?.models) setModelUsage(data.models as ModelUsage[]);
    } catch { /* ignore */ }
  }, []);

  // ─── Load cron jobs ──────────────────────────────────────────────────────

  const loadCronJobs = useCallback(async () => {
    try {
      const res: any = await customFetch("/api/v1/cron-jobs", { method: "GET" });
      const data = Array.isArray(res?.data) ? res.data : Array.isArray(res) ? res : [];
      setCronJobs(data);
    } catch {
      setCronJobs([]);
    } finally {
      setCronLoading(false);
    }
  }, []);

  // ─── Load error events ─────────────────────────────────────────────────

  const loadErrors = useCallback(async () => {
    try {
      const res: any = await customFetch("/api/v1/cost-tracker/errors?limit=20", { method: "GET" });
      const data = res?.data ?? res;
      const items = Array.isArray(data) ? data : [];
      setErrorEvents(items);
    } catch {
      setErrorEvents([]);
    }
  }, []);

  useEffect(() => {
    if (!isSignedIn) return;
    loadModelUsage();
    loadCronJobs();
    loadErrors();
    // Refresh model usage every 30s, cron jobs every 60s, errors every 60s
    const modelInterval = setInterval(loadModelUsage, 30_000);
    const cronInterval = setInterval(loadCronJobs, 60_000);
    const errorInterval = setInterval(loadErrors, 60_000);
    return () => { clearInterval(modelInterval); clearInterval(cronInterval); clearInterval(errorInterval); };
  }, [isSignedIn, loadModelUsage, loadCronJobs, loadErrors]);

  // ─── Derived data ────────────────────────────────────────────────────────

  const discordSessions = sessions.filter((s) =>
    s.key.includes("discord") || s.key.includes("the-claw") || s.key.includes("market-scout") ||
    s.key.includes("sports-analyst") || s.key.includes("stock-analyst")
  );

  // Group sessions by agent for detail panel
  const agentSessions = (agentId: string) =>
    discordSessions.filter((s) => s.agent === agentId || s.key.includes(agentId));

  // Get model usage for a specific agent
  const agentModelUsage = (agentName: string) =>
    modelUsage.filter((m) => m.agents.some((a) => a.toLowerCase().includes(agentName.toLowerCase())));

  // Get agent events for detail panel
  const agentEvents = (agentId: string) =>
    events.filter((e) => e.agent.includes(agentId)).slice(0, 15);

  // Cron jobs for a specific agent
  const agentCronJobs = (agentId: string) =>
    cronJobs.filter((j) => j.agent_id === agentId);

  // ─── Render ──────────────────────────────────────────────────────────────

  return (
    <DashboardPageLayout
      signedOut={{ message: "Sign in to view agent activity.", forceRedirectUrl: "/live", signUpForceRedirectUrl: "/live" }}
      title="Agent Activity"
      description="Real-time agent status, cost tracking, and cron execution."
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
              {lastPoll > 0 ? `Polling every 3s  \u2022  Last: ${timeAgo(lastPoll)}` : ""}
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

        {/* ═══ Agent Cards ═══ */}
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
          {discordSessions.map((session) => {
            const isActive = Date.now() - session.updatedAt < 60000;
            const isWorking = Date.now() - session.updatedAt < 15000;
            const agent = getAgent(session.agent);
            const tier = tierFromModel(session.model);
            const cost = estimateCost(session.model, session.inputTokens, session.outputTokens);
            const isExpanded = expandedAgent === session.agent;

            return (
              <div key={session.key}>
                <button
                  onClick={() => setExpandedAgent(isExpanded ? null : session.agent)}
                  className={cn(
                    "relative w-full overflow-hidden rounded-xl border bg-white p-4 shadow-sm transition-all duration-300 text-left",
                    isWorking ? "border-blue-300 shadow-blue-100 shadow-md" :
                    isExpanded ? "border-slate-300 shadow-md" : "border-slate-200 hover:border-slate-300",
                  )}
                >
                  {isWorking && (
                    <div className="absolute inset-0 animate-pulse bg-gradient-to-r from-blue-50/50 to-transparent pointer-events-none" />
                  )}

                  <div className="relative flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      <div className={cn("h-3 w-3 rounded-full", agent.color)} />
                      <span className="text-sm font-semibold text-slate-900">{agent.name}</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-medium", tier.color)}>
                        {tier.label}
                      </span>
                      <div className={cn(
                        "flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium transition-all",
                        isWorking ? "bg-blue-100 text-blue-700 animate-pulse" :
                        isActive ? "bg-emerald-100 text-emerald-700" :
                        "bg-slate-100 text-slate-500"
                      )}>
                        {isWorking ? <><Zap className="h-2.5 w-2.5" /> Working</> :
                         isActive ? <><Activity className="h-2.5 w-2.5" /> Active</> :
                         <><Clock className="h-2.5 w-2.5" /> Idle</>}
                      </div>
                    </div>
                  </div>

                  <div className="relative mt-3 grid grid-cols-2 gap-y-1.5 text-xs text-slate-500">
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
                    <div className="flex items-center gap-1">
                      <DollarSign className="h-3 w-3" />
                      <span className="font-mono">{cost}</span>
                    </div>
                  </div>

                  <div className="relative mt-2 flex items-center justify-between text-[10px] text-slate-400">
                    <span>{timeAgo(session.updatedAt)}</span>
                    {isExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                  </div>
                </button>

                {/* ─── Agent Detail Panel ─── */}
                {isExpanded && (
                  <div className="mt-1 rounded-xl border border-slate-200 bg-slate-50/80 p-4 space-y-4 animate-[slideDown_0.2s_ease-out]">
                    {/* Model Usage for this agent */}
                    {(() => {
                      const usage = agentModelUsage(agent.name);
                      if (usage.length === 0) return null;
                      return (
                        <div>
                          <h4 className="text-xs font-semibold text-slate-700 mb-2 flex items-center gap-1.5">
                            <DollarSign className="h-3 w-3" /> Model Usage (All Sessions)
                          </h4>
                          <div className="space-y-1.5">
                            {usage.map((m) => (
                              <div key={m.model} className="flex items-center justify-between rounded-lg bg-white px-3 py-2 text-xs border border-slate-100">
                                <div className="flex items-center gap-2">
                                  <span className="font-mono font-medium text-slate-700">{m.model}</span>
                                  <span className={cn("rounded px-1.5 py-0.5 text-[9px] font-medium",
                                    m.tier.includes("4") ? "bg-red-100 text-red-700" :
                                    m.tier.includes("3") ? "bg-purple-100 text-purple-700" :
                                    m.tier.includes("2") ? "bg-blue-100 text-blue-700" :
                                    "bg-emerald-100 text-emerald-700"
                                  )}>{m.tier.replace("Tier ", "T").replace(" — ", " ")}</span>
                                </div>
                                <div className="flex items-center gap-4 text-slate-500">
                                  <span>{m.total_tokens.toLocaleString()} tokens</span>
                                  <span>{m.session_count} sessions</span>
                                  <span className="font-semibold text-slate-800">${m.estimated_cost.toFixed(4)}</span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })()}

                    {/* Cron jobs for this agent */}
                    {(() => {
                      const jobs = agentCronJobs(session.agent);
                      if (jobs.length === 0) return null;
                      return (
                        <div>
                          <h4 className="text-xs font-semibold text-slate-700 mb-2 flex items-center gap-1.5">
                            <Timer className="h-3 w-3" /> Scheduled Tasks
                          </h4>
                          <div className="space-y-1.5">
                            {jobs.map((job) => (
                              <div key={job.id} className="flex items-center justify-between rounded-lg bg-white px-3 py-2 text-xs border border-slate-100">
                                <div className="flex items-center gap-2">
                                  <span className={cn("h-2 w-2 rounded-full", job.enabled ? "bg-emerald-500" : "bg-slate-300")} />
                                  <span className="font-medium text-slate-700">{job.name}</span>
                                  <span className="font-mono text-slate-400">{job.schedule_expr}</span>
                                </div>
                                <div className="flex items-center gap-3 text-slate-500">
                                  {job.last_status && (
                                    <span className={cn("flex items-center gap-1",
                                      job.last_status === "success" ? "text-emerald-600" : "text-red-500"
                                    )}>
                                      {job.last_status === "success" ?
                                        <CheckCircle2 className="h-3 w-3" /> :
                                        <XCircle className="h-3 w-3" />}
                                      {job.last_status}
                                    </span>
                                  )}
                                  {job.next_run && (
                                    <span className="text-slate-400">Next: {timeUntil(job.next_run)}</span>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })()}

                    {/* Recent activity for this agent */}
                    {(() => {
                      const recentEvents = agentEvents(session.agent);
                      if (recentEvents.length === 0) return null;
                      return (
                        <div>
                          <h4 className="text-xs font-semibold text-slate-700 mb-2 flex items-center gap-1.5">
                            <Activity className="h-3 w-3" /> Recent Activity
                          </h4>
                          <div className="space-y-1 max-h-[200px] overflow-y-auto">
                            {recentEvents.map((evt) => (
                              <div key={evt.id} className="flex items-start gap-2 rounded-lg bg-white px-3 py-2 text-xs border border-slate-100">
                                <span className={cn(
                                  "mt-0.5 shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-semibold",
                                  evt.type === "active" ? "bg-blue-100 text-blue-700" :
                                  evt.type === "thinking" ? "bg-yellow-100 text-yellow-700" :
                                  evt.type === "tool_call" ? "bg-orange-100 text-orange-700" :
                                  evt.type === "responded" ? "bg-emerald-100 text-emerald-700" :
                                  evt.type === "cron" ? "bg-indigo-100 text-indigo-700" :
                                  "bg-slate-100 text-slate-500"
                                )}>
                                  {evt.type === "active" ? "WORKING" :
                                   evt.type === "thinking" ? "THINKING" :
                                   evt.type === "tool_call" ? "TOOL" :
                                   evt.type === "responded" ? "DONE" :
                                   evt.type === "cron" ? "CRON" :
                                   evt.type.toUpperCase()}
                                </span>
                                <p className="min-w-0 flex-1 text-slate-600 truncate">{evt.message}</p>
                                <span className="shrink-0 text-[10px] text-slate-400">
                                  {new Date(evt.timestamp).toLocaleTimeString()}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })()}

                    {/* All sessions for this agent */}
                    {(() => {
                      const allSessions = agentSessions(session.agent);
                      if (allSessions.length <= 1) return null;
                      return (
                        <div>
                          <h4 className="text-xs font-semibold text-slate-700 mb-2 flex items-center gap-1.5">
                            <Bot className="h-3 w-3" /> All Sessions ({allSessions.length})
                          </h4>
                          <div className="space-y-1.5">
                            {allSessions.map((s) => (
                              <div key={s.key} className="flex items-center justify-between rounded-lg bg-white px-3 py-2 text-xs border border-slate-100">
                                <div className="flex items-center gap-2">
                                  <span className="font-mono text-slate-500 truncate max-w-[200px]">{s.key}</span>
                                </div>
                                <div className="flex items-center gap-3 text-slate-500">
                                  <span>{s.totalTokens.toLocaleString()} tokens</span>
                                  <span className="text-slate-400">{timeAgo(s.updatedAt)}</span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                )}
              </div>
            );
          })}
          {discordSessions.length === 0 && (
            <div className="col-span-4 rounded-xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-400">
              No active agent sessions. Send a message in Discord to see agents appear.
            </div>
          )}
        </div>

        {/* ═══ Cron Job Execution Log ═══ */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <div>
              <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-1.5">
                <Timer className="h-4 w-4" /> Cron Execution Log
              </h3>
              <p className="text-xs text-slate-500">
                {cronJobs.filter((j) => j.enabled).length} active jobs \u2022 {cronJobs.length} total
              </p>
            </div>
            <button
              onClick={() => { setCronLoading(true); loadCronJobs(); }}
              className="flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-50 transition"
            >
              <RefreshCw className={cn("h-3 w-3", cronLoading && "animate-spin")} />
              Refresh
            </button>
          </div>
          {cronLoading && cronJobs.length === 0 ? (
            <div className="flex justify-center py-8">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-200 border-t-blue-500" />
            </div>
          ) : cronJobs.length === 0 ? (
            <p className="py-6 text-center text-sm text-slate-400">No cron jobs configured</p>
          ) : (
            <div className="divide-y divide-slate-50">
              {cronJobs
                .sort((a, b) => {
                  // Sort: most recently run first, then by next run
                  const aLast = a.last_run ? new Date(a.last_run).getTime() : 0;
                  const bLast = b.last_run ? new Date(b.last_run).getTime() : 0;
                  return bLast - aLast;
                })
                .map((job) => {
                  const agent = AGENTS[job.agent_id] || { name: job.agent_id, color: "bg-slate-500" };
                  return (
                    <div key={job.id} className="flex items-center gap-4 px-4 py-3 hover:bg-slate-50/50 transition">
                      {/* Status dot */}
                      <div className={cn(
                        "h-2.5 w-2.5 shrink-0 rounded-full",
                        !job.enabled ? "bg-slate-300" :
                        job.last_status === "success" ? "bg-emerald-500" :
                        job.last_status === "error" || job.last_status === "failed" ? "bg-red-500" :
                        "bg-amber-400"
                      )} />

                      {/* Job info */}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-slate-800">{job.name}</span>
                          <span className={cn(
                            "rounded-full px-2 py-0.5 text-[10px] font-medium",
                            AGENTS[job.agent_id]
                              ? (job.agent_id === "the-claw" ? "bg-blue-100 text-blue-700" :
                                 job.agent_id === "sports-analyst" ? "bg-emerald-100 text-emerald-700" :
                                 job.agent_id === "market-scout" ? "bg-purple-100 text-purple-700" :
                                 job.agent_id === "stock-analyst" ? "bg-amber-100 text-amber-700" :
                                 "bg-slate-100 text-slate-600")
                              : "bg-slate-100 text-slate-600"
                          )}>
                            {agent.name}
                          </span>
                          {!job.enabled && (
                            <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-400">PAUSED</span>
                          )}
                        </div>
                        {job.description && (
                          <p className="mt-0.5 text-xs text-slate-500 truncate">{job.description}</p>
                        )}
                      </div>

                      {/* Schedule */}
                      <div className="shrink-0 text-right">
                        <div className="text-xs font-mono text-slate-600">{job.schedule_expr}</div>
                        <div className="text-[10px] text-slate-400">{job.timezone}</div>
                      </div>

                      {/* Last run */}
                      <div className="shrink-0 text-right min-w-[90px]">
                        <div className="flex items-center justify-end gap-1 text-xs">
                          {job.last_status === "success" ? (
                            <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                          ) : job.last_status === "error" || job.last_status === "failed" ? (
                            <XCircle className="h-3 w-3 text-red-500" />
                          ) : job.last_status ? (
                            <AlertTriangle className="h-3 w-3 text-amber-500" />
                          ) : null}
                          <span className={cn(
                            "text-xs",
                            job.last_status === "success" ? "text-emerald-600" :
                            job.last_status === "error" || job.last_status === "failed" ? "text-red-500" :
                            "text-slate-400"
                          )}>
                            {job.last_status || "never"}
                          </span>
                        </div>
                        <div className="text-[10px] text-slate-400">{formatTime(job.last_run)}</div>
                      </div>

                      {/* Next run */}
                      <div className="shrink-0 text-right min-w-[70px]">
                        <div className="text-xs text-slate-600">{timeUntil(job.next_run)}</div>
                        <div className="text-[10px] text-slate-400">next run</div>
                      </div>
                    </div>
                  );
                })}
            </div>
          )}
        </div>

        {/* ═══ Error Log ═══ */}
        {errorEvents.length > 0 && (
          <div className="rounded-xl border border-red-200 bg-white shadow-sm">
            <button
              onClick={() => setShowErrors(!showErrors)}
              className="flex w-full items-center justify-between border-b border-red-100 px-4 py-3 hover:bg-red-50/50 transition"
            >
              <div>
                <h3 className="text-sm font-semibold text-red-900 flex items-center gap-1.5">
                  <AlertTriangle className="h-4 w-4 text-red-500" />
                  Error Log
                  <span className="ml-1.5 rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-medium text-red-700">
                    {errorEvents.length}
                  </span>
                </h3>
                <p className="text-xs text-red-400">Recent system errors and warnings</p>
              </div>
              {showErrors ? <ChevronUp className="h-4 w-4 text-red-400" /> : <ChevronDown className="h-4 w-4 text-red-400" />}
            </button>
            {showErrors && (
              <div className="divide-y divide-red-50 max-h-[300px] overflow-y-auto">
                {errorEvents.map((evt: any, idx: number) => {
                  const eventType = evt.event_type || "";
                  const source = eventType.replace("system.error.", "");
                  const message = evt.message || "";
                  const isWarning = message.startsWith("[WARNING]");
                  const cleanMessage = message.replace(/^\[(ERROR|WARNING)\]\s*/, "");
                  const timestamp = evt.created_at ? new Date(evt.created_at).toLocaleString(undefined, {
                    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit",
                  }) : "";

                  return (
                    <div key={evt.id || idx} className="flex items-start gap-3 px-4 py-2.5">
                      <div className={cn(
                        "mt-1 h-2 w-2 shrink-0 rounded-full",
                        isWarning ? "bg-amber-400" : "bg-red-500"
                      )} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className={cn(
                            "rounded px-1.5 py-0.5 text-[10px] font-semibold",
                            isWarning ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-700"
                          )}>
                            {source.toUpperCase()}
                          </span>
                          <span className="text-[10px] text-slate-400">{timestamp}</span>
                        </div>
                        <p className="mt-0.5 text-xs text-slate-600 whitespace-pre-wrap">{cleanMessage}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* ═══ Activity Timeline ═══ */}
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
                {events.map((event, idx) => {
                  const agent = getAgent(event.agent);
                  return (
                    <div
                      key={event.id}
                      className={cn(
                        "flex items-start gap-3 px-4 py-3 transition-all duration-300",
                        event.type === "active" ? "bg-blue-50/30" : "",
                        idx === 0 ? "animate-[slideDown_0.3s_ease-out]" : "",
                      )}
                    >
                      <div className="mt-1 flex flex-col items-center gap-1">
                        <div className={cn("h-2.5 w-2.5 rounded-full ring-2 ring-white", agent.color)} />
                      </div>

                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium text-slate-900">{agent.name}</span>
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
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </DashboardPageLayout>
  );
}
