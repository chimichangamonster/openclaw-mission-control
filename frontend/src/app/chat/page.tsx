"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Bot,
  MessageSquare,
  Send,
  Loader2,
  Radio,
  WifiOff,
  Minimize2,
  Trash2,
  Square,
} from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { customFetch } from "@/api/mutator";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Markdown } from "@/components/atoms/Markdown";
import { cn } from "@/lib/utils";

// ─── Constants ────────────────────────────────────────────────────────────────

const BOARD_ID = "fc95c061-3c32-4c82-a87d-9e21225e59fd";

// ─── Types ────────────────────────────────────────────────────────────────────

interface GatewaySession {
  key: string;
  displayName?: string;
  groupChannel?: string;
  model?: string;
  totalTokens?: number;
  inputTokens?: number;
  outputTokens?: number;
}

// Context windows by model family
function getContextWindow(model: string): number {
  const short = (model || "").split("/").pop() || "";
  if (short.includes("opus")) return 1_000_000;
  if (short.includes("deepseek")) return 128_000;
  if (short.includes("grok")) return 131_072;
  if (short.includes("nano")) return 128_000;
  if (short.includes("flash")) return 1_000_000;
  // Sonnet 4, default
  return 200_000;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
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

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Pick The Claw's primary session from the gateway session list.
 * Priority: #general channel > mc-gateway main > first available with "the-claw" or "main"
 */
function findClawSession(sessions: GatewaySession[]): GatewaySession | null {
  // 1. The Claw on #general
  const general = sessions.find(
    (s) => s.groupChannel === "general" && s.key.includes("the-claw"),
  );
  if (general) return general;

  // 2. Any session on #general channel
  const anyGeneral = sessions.find((s) => s.groupChannel === "general");
  if (anyGeneral) return anyGeneral;

  // 3. The mc-gateway main session (board lead)
  const mcGateway = sessions.find((s) => s.key.includes("mc-gateway") && s.key.endsWith(":main"));
  if (mcGateway) return mcGateway;

  // 4. Any session with "the-claw" in the key
  const theClaw = sessions.find((s) => s.key.includes("the-claw"));
  if (theClaw) return theClaw;

  // 5. Fallback to first session
  return sessions[0] ?? null;
}

function extractTextContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .filter(
        (p): p is { type: string; text: string } =>
          typeof p === "object" &&
          p !== null &&
          p.type === "text" &&
          typeof p.text === "string",
      )
      .map((p) => p.text)
      .join("\n");
  }
  return String(content ?? "");
}

function parseHistory(history: unknown[]): ChatMessage[] {
  return history
    .filter(
      (msg): msg is Record<string, unknown> =>
        typeof msg === "object" && msg !== null,
    )
    .map((msg, i) => {
      const role = String(msg.role ?? "system");
      const normalizedRole: ChatMessage["role"] =
        role === "user" || role === "human"
          ? "user"
          : role === "assistant" || role === "model"
            ? "assistant"
            : "system";
      return {
        id: String(msg.id ?? `msg-${i}`),
        role: normalizedRole,
        content: extractTextContent(msg.content),
      };
    })
    .filter((msg) => msg.role !== "system" && msg.content.trim().length > 0);
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function ChatPage() {
  const { isSignedIn } = useAuth();

  // Session resolution
  const [sessionKey, setSessionKey] = useState<string | null>(null);
  const [sessionTokens, setSessionTokens] = useState<{ total: number; input: number; output: number; model: string } | null>(null);
  const [resolving, setResolving] = useState(true);
  const [resolveError, setResolveError] = useState<string | null>(null);

  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [agentTyping, setAgentTyping] = useState(false);

  // SSE
  const [sseConnected, setSseConnected] = useState(false);

  // Refs
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const sseRef = useRef<EventSource | null>(null);
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sessionKeyRef = useRef<string | null>(null);

  // Keep ref in sync for SSE callback
  useEffect(() => {
    sessionKeyRef.current = sessionKey;
  }, [sessionKey]);

  // ─── Resolve The Claw's session on mount ──────────────────────────────────

  useEffect(() => {
    if (!isSignedIn) return;
    let cancelled = false;

    (async () => {
      try {
        const raw: any = await customFetch(
          `/api/v1/gateways/sessions?board_id=${BOARD_ID}`,
          { method: "GET" },
        );
        if (cancelled) return;
        const data = raw?.data ?? raw;
        const list: GatewaySession[] = (data?.sessions || []).filter(
          (s: any) => typeof s === "object" && s !== null && s.key,
        );
        const claw = findClawSession(list);
        if (claw) {
          setSessionKey(claw.key);
          setSessionTokens({
            total: claw.totalTokens ?? 0,
            input: claw.inputTokens ?? 0,
            output: claw.outputTokens ?? 0,
            model: claw.model ?? "",
          });
        } else {
          setResolveError("No active agent sessions. The gateway may be offline.");
        }
      } catch {
        if (!cancelled) setResolveError("Could not connect to the gateway.");
      } finally {
        if (!cancelled) setResolving(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [isSignedIn]);

  // ─── Poll session tokens ───────────────────────────────────────────────────

  useEffect(() => {
    if (!isSignedIn || !sessionKey) return;
    const interval = setInterval(async () => {
      try {
        const raw: any = await customFetch(
          `/api/v1/gateways/sessions?board_id=${BOARD_ID}`,
          { method: "GET" },
        );
        const data = raw?.data ?? raw;
        const list: GatewaySession[] = (data?.sessions || []).filter(
          (s: any) => typeof s === "object" && s !== null && s.key,
        );
        const match = list.find((s) => s.key === sessionKey);
        if (match) {
          setSessionTokens({
            total: match.totalTokens ?? 0,
            input: match.inputTokens ?? 0,
            output: match.outputTokens ?? 0,
            model: match.model ?? "",
          });
        }
      } catch { /* ignore */ }
    }, 15_000);
    return () => clearInterval(interval);
  }, [isSignedIn, sessionKey]);

  // ─── Fetch chat history ───────────────────────────────────────────────────

  const fetchHistory = useCallback(async (key: string) => {
    setMessagesLoading(true);
    try {
      const raw: any = await customFetch(
        `/api/v1/gateways/sessions/${encodeURIComponent(key)}/history?board_id=${BOARD_ID}`,
        { method: "GET" },
      );
      const data = raw?.data ?? raw;
      const history = Array.isArray(data?.history) ? data.history : [];
      setMessages(parseHistory(history));
    } catch {
      setMessages([]);
    } finally {
      setMessagesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!sessionKey || !isSignedIn) return;
    void fetchHistory(sessionKey);
  }, [sessionKey, isSignedIn, fetchHistory]);

  // ─── Auto-scroll ──────────────────────────────────────────────────────────

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, agentTyping]);

  // ─── SSE for real-time events ─────────────────────────────────────────────

  useEffect(() => {
    if (!isSignedIn) return;
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("auth_token") || ""
        : "";
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || "";
    const url = `${baseUrl}/api/v1/activity/live/stream?token=${encodeURIComponent(token)}`;
    const es = new EventSource(url);
    sseRef.current = es;

    es.onopen = () => setSseConnected(true);
    es.onerror = () => setSseConnected(false);

    es.addEventListener("activity", (e) => {
      try {
        const data: LiveSSEEvent = JSON.parse(e.data);
        const eventType = data.event_type || "";

        // Only care about events from The Claw / main agent
        const agent = data.agent_name || "";
        const isRelevant =
          agent.includes("the-claw") ||
          agent.includes("main") ||
          agent.includes("mc-gateway");
        if (!isRelevant) return;

        // Agent is thinking/working
        if (
          eventType.includes("thinking") ||
          eventType.includes("working") ||
          eventType.includes("tool_call")
        ) {
          setAgentTyping(true);
          if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
          typingTimeoutRef.current = setTimeout(
            () => setAgentTyping(false),
            15000,
          );
        }

        // Agent responded — refetch history
        if (
          eventType.includes("responded") ||
          eventType.includes("completed")
        ) {
          setAgentTyping(false);
          if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
          const currentKey = sessionKeyRef.current;
          if (currentKey) {
            setTimeout(() => void fetchHistory(currentKey), 500);
          }
        }
      } catch {
        /* ignore parse errors */
      }
    });

    return () => {
      es.close();
      sseRef.current = null;
    };
  }, [isSignedIn, fetchHistory]);

  // ─── Send message ─────────────────────────────────────────────────────────

  const sendMessage = useCallback(async () => {
    if (!sessionKey || !input.trim() || isSending) return;

    const content = input.trim();
    setInput("");
    setIsSending(true);

    // Optimistic: add user message immediately
    const optimisticMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content,
    };
    setMessages((prev) => [...prev, optimisticMsg]);
    setAgentTyping(true);

    try {
      await customFetch(
        `/api/v1/gateways/sessions/${encodeURIComponent(sessionKey)}/message?board_id=${BOARD_ID}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content }),
        },
      );
    } catch {
      setMessages((prev) => prev.filter((m) => m.id !== optimisticMsg.id));
      setInput(content);
      setAgentTyping(false);
    } finally {
      setIsSending(false);
      textareaRef.current?.focus();
    }
  }, [sessionKey, input, isSending]);

  // ─── Session commands ─────────────────────────────────────────────────────

  const [commandLoading, setCommandLoading] = useState<string | null>(null);

  const abortChat = useCallback(async () => {
    if (!sessionKey) return;
    try {
      await customFetch(
        `/api/v1/gateways/sessions/${encodeURIComponent(sessionKey)}/abort?board_id=${BOARD_ID}`,
        { method: "POST" },
      );
    } catch { /* ignore */ }
    setAgentTyping(false);
    if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    // Refetch to get whatever partial response was generated
    setTimeout(() => { if (sessionKey) void fetchHistory(sessionKey); }, 500);
  }, [sessionKey, fetchHistory]);

  const compactChat = useCallback(async () => {
    if (!sessionKey || commandLoading) return;
    setCommandLoading("compact");
    try {
      await customFetch(
        `/api/v1/gateways/sessions/${encodeURIComponent(sessionKey)}/compact?board_id=${BOARD_ID}`,
        { method: "POST" },
      );
      await fetchHistory(sessionKey);
    } catch { /* ignore */ }
    finally { setCommandLoading(null); }
  }, [sessionKey, commandLoading, fetchHistory]);

  const clearChat = useCallback(async () => {
    if (!sessionKey || commandLoading) return;
    if (!window.confirm("Clear the entire conversation? This cannot be undone.")) return;
    setCommandLoading("clear");
    try {
      await customFetch(
        `/api/v1/gateways/sessions/${encodeURIComponent(sessionKey)}/reset?board_id=${BOARD_ID}`,
        { method: "POST" },
      );
      setMessages([]);
    } catch { /* ignore */ }
    finally { setCommandLoading(null); }
  }, [sessionKey, commandLoading]);

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to chat with The Claw",
        forceRedirectUrl: "/chat",
      }}
      title="Chat"
      description="Talk to The Claw — your AI assistant that coordinates all agents"
      mainClassName="!overflow-hidden"
      contentClassName="!p-0 h-[calc(100vh-130px)]"
    >
      <div className="flex h-full flex-col">
        {/* ─── Header bar ──────────────────────────────────────────────── */}
        <div className="flex items-center justify-between border-b border-[color:var(--border)] bg-[color:var(--surface)] px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-500">
              <Bot className="h-4.5 w-4.5 text-white" />
            </div>
            <div>
              <p className="text-sm font-medium text-[color:var(--text)]">
                The Claw
              </p>
              {agentTyping ? (
                <p className="text-xs text-emerald-600">typing...</p>
              ) : (
                <p className="text-xs text-[color:var(--text-quiet)]">
                  #general
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {sessionKey ? (
              <>
                <button
                  onClick={() => void compactChat()}
                  disabled={commandLoading !== null}
                  title="Compact — summarise and trim history to save tokens"
                  className="rounded-md p-1.5 text-[color:var(--text-quiet)] hover:bg-[color:var(--surface-muted)] hover:text-[color:var(--text)] transition disabled:opacity-40"
                >
                  {commandLoading === "compact" ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Minimize2 className="h-4 w-4" />
                  )}
                </button>
                <button
                  onClick={() => void clearChat()}
                  disabled={commandLoading !== null}
                  title="Clear — reset the entire conversation"
                  className="rounded-md p-1.5 text-[color:var(--text-quiet)] hover:bg-[color:var(--surface-muted)] hover:text-rose-500 transition disabled:opacity-40"
                >
                  {commandLoading === "clear" ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                </button>
              </>
            ) : null}
            {sessionTokens ? (() => {
              const maxTokens = getContextWindow(sessionTokens.model);
              const pct = sessionTokens.total / maxTokens;
              const maxLabel = maxTokens >= 1_000_000 ? `${maxTokens / 1_000_000}M` : `${maxTokens / 1000}K`;
              return (
                <div className="flex items-center gap-2 ml-1" title={`${sessionTokens.total.toLocaleString()} / ${maxTokens.toLocaleString()} tokens (${sessionTokens.input.toLocaleString()} in / ${sessionTokens.output.toLocaleString()} out)`}>
                  <div className="flex items-center gap-1.5">
                    <div className="h-1.5 w-16 rounded-full bg-[color:var(--surface-muted)] overflow-hidden">
                      <div
                        className={cn(
                          "h-full rounded-full transition-all duration-500",
                          pct > 0.8 ? "bg-rose-500" : pct > 0.5 ? "bg-amber-500" : "bg-emerald-500",
                        )}
                        style={{ width: `${Math.min(100, pct * 100)}%` }}
                      />
                    </div>
                    <span className="text-[10px] tabular-nums text-[color:var(--text-quiet)]">
                      {sessionTokens.total >= 1000
                        ? `${(sessionTokens.total / 1000).toFixed(1)}K`
                        : sessionTokens.total}
                      <span className="text-[color:var(--text-quiet)] opacity-50">/{maxLabel}</span>
                    </span>
                  </div>
                </div>
              );
            })() : null}
            <div className="flex items-center gap-1.5 text-xs text-[color:var(--text-quiet)] ml-1">
              {sseConnected ? (
                <>
                  <Radio className="h-3.5 w-3.5 text-emerald-500" />
                </>
              ) : (
                <>
                  <WifiOff className="h-3.5 w-3.5" />
                </>
              )}
            </div>
          </div>
        </div>

        {/* ─── Messages ────────────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {resolving || messagesLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="h-6 w-6 animate-spin text-[color:var(--text-muted)]" />
            </div>
          ) : resolveError ? (
            <div className="flex flex-col items-center justify-center py-20 text-[color:var(--text-muted)]">
              <WifiOff className="h-10 w-10 mb-3 opacity-40" />
              <p className="text-sm">{resolveError}</p>
            </div>
          ) : messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-[color:var(--text-muted)]">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-blue-50 dark:bg-blue-950 mb-4">
                <Bot className="h-8 w-8 text-blue-500" />
              </div>
              <p className="text-lg font-medium text-[color:var(--text)]">
                Hey! I&apos;m The Claw.
              </p>
              <p className="mt-1 text-sm text-center max-w-md">
                I can help with trading, sports betting, emails, documents, and
                more. I&apos;ll bring in the right specialist agent when needed.
              </p>
              <div className="mt-6 flex flex-wrap justify-center gap-2">
                {[
                  "What's the market doing today?",
                  "Any pending sports bets?",
                  "Check my email",
                  "Generate a proposal",
                ].map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => {
                      setInput(suggestion);
                      textareaRef.current?.focus();
                    }}
                    className="rounded-full border border-[color:var(--border)] bg-[color:var(--surface)] px-4 py-2 text-xs text-[color:var(--text)] hover:bg-[color:var(--surface-muted)] transition"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  "flex gap-3",
                  msg.role === "user" ? "justify-end" : "justify-start",
                )}
              >
                {msg.role === "assistant" ? (
                  <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-500">
                    <Bot className="h-4 w-4 text-white" />
                  </div>
                ) : null}
                <div
                  className={cn(
                    "max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
                    msg.role === "user"
                      ? "bg-[color:var(--accent-strong)] text-white rounded-br-md"
                      : "bg-[color:var(--surface-muted)] text-[color:var(--text)] rounded-bl-md",
                  )}
                >
                  {msg.role === "user" ? (
                    <p className="whitespace-pre-wrap break-words">{msg.content}</p>
                  ) : (
                    <div className="break-words [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                      <Markdown content={msg.content} variant="description" />
                    </div>
                  )}
                </div>
              </div>
            ))
          )}

          {/* Typing indicator */}
          {agentTyping ? (
            <div className="flex gap-3">
              <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-500">
                <Bot className="h-4 w-4 text-white" />
              </div>
              <div className="rounded-2xl rounded-bl-md bg-[color:var(--surface-muted)] px-4 py-3">
                <div className="flex gap-1.5">
                  <span className="h-2 w-2 animate-bounce rounded-full bg-[color:var(--text-quiet)] [animation-delay:0ms]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-[color:var(--text-quiet)] [animation-delay:150ms]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-[color:var(--text-quiet)] [animation-delay:300ms]" />
                </div>
              </div>
            </div>
          ) : null}

          <div ref={messagesEndRef} />
        </div>

        {/* ─── Input area ──────────────────────────────────────────────── */}
        {!resolving && !resolveError ? (
          <div className="border-t border-[color:var(--border)] bg-[color:var(--surface)] p-4">
            <div className="mx-auto flex max-w-3xl gap-2">
              <Textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key !== "Enter") return;
                  if (e.nativeEvent.isComposing) return;
                  if (e.shiftKey) return;
                  e.preventDefault();
                  void sendMessage();
                }}
                placeholder="Message The Claw..."
                className="min-h-[44px] max-h-[160px] resize-none"
                rows={1}
                disabled={isSending}
              />
              {agentTyping ? (
                <Button
                  onClick={() => void abortChat()}
                  className="shrink-0 h-[44px] w-[44px] px-0 bg-rose-500 hover:bg-rose-600"
                  title="Stop response"
                >
                  <Square className="h-4 w-4 fill-current" />
                </Button>
              ) : (
                <Button
                  onClick={() => void sendMessage()}
                  disabled={isSending || !input.trim()}
                  className="shrink-0 h-[44px] w-[44px] px-0"
                >
                  {isSending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}
                </Button>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </DashboardPageLayout>
  );
}
