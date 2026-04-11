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
  Paperclip,
  X,
  FileText,
  Image as ImageIcon,
  PanelLeft,
} from "lucide-react";
import { ChatSessionSidebar } from "@/components/ChatSessionSidebar";
import { ChatActivityPanel } from "@/components/ChatActivityPanel";
import type { LiveSSEEvent } from "@/components/ChatActivityPanel";
import { useNotifications } from "@/components/providers/NotificationProvider";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { customFetch } from "@/api/mutator";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Markdown } from "@/components/atoms/Markdown";
import { cn, extractTextContent } from "@/lib/utils";

// ─── Constants ────────────────────────────────────────────────────────────────

const MAX_UPLOAD_SIZE = 10 * 1024 * 1024; // 10 MB
const ALLOWED_UPLOAD_TYPES = new Set([
  "image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml",
  "application/pdf",
  "text/plain", "text/csv", "text/markdown",
  "application/json",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
]);

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
  timestamp?: string; // ISO string from gateway or locally assigned
}

interface ChatAttachment {
  filename: string;
  workspace_path: string;
  content_type: string;
  size_bytes: number;
  sanitized_workspace_path?: string | null;
  preview_url?: string; // local blob URL for image preview
}

// LiveSSEEvent imported from ChatActivityPanel

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

// extractTextContent is imported from @/lib/utils

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
      // Gateway may provide createdAt, timestamp, or created_at
      const ts = msg.createdAt ?? msg.timestamp ?? msg.created_at;
      return {
        id: String(msg.id ?? `msg-${i}`),
        role: normalizedRole,
        content: extractTextContent(msg.content),
        timestamp: typeof ts === "string" ? ts : undefined,
      };
    })
    .filter((msg) => msg.role !== "system" && msg.content.trim().length > 0);
}

function formatMessageTime(ts: string | undefined): string | null {
  if (!ts) return null;
  const date = new Date(ts);
  if (isNaN(date.getTime())) return null;
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday = date.toDateString() === yesterday.toDateString();

  const time = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (isToday) return time;
  if (isYesterday) return `Yesterday ${time}`;
  return `${date.toLocaleDateString([], { month: "short", day: "numeric" })} ${time}`;
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function ChatPage() {
  const { isSignedIn, getToken } = useAuth();
  const { unreadSessions, markSessionRead } = useNotifications();

  // Board resolution — pick first board with a gateway
  const [boardId, setBoardId] = useState<string | null>(null);
  const [boardResolving, setBoardResolving] = useState(true);

  useEffect(() => {
    if (!isSignedIn) return;
    let cancelled = false;
    (async () => {
      try {
        const raw: any = await customFetch("/api/v1/boards?limit=200", { method: "GET" });
        if (cancelled) return;
        const data = raw?.data ?? raw;
        const items: any[] = data?.items ?? [];
        const withGateway = items.find((b: any) => b.gateway_id);
        if (withGateway) {
          setBoardId(withGateway.id);
        }
      } catch { /* ignore */ }
      finally { if (!cancelled) setBoardResolving(false); }
    })();
    return () => { cancelled = true; };
  }, [isSignedIn]);

  // Session resolution
  const [sessionKey, setSessionKey] = useState<string | null>(null);
  const [sessionTokens, setSessionTokens] = useState<{ total: number; input: number; output: number; model: string } | null>(null);
  const [resolving, setResolving] = useState(true);
  const [resolveError, setResolveError] = useState<string | null>(null);

  // Multi-session state
  const [allSessions, setAllSessions] = useState<GatewaySession[]>([]);
  const [mainSessionKey, setMainSessionKey] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [agentTyping, setAgentTyping] = useState(false);

  // File uploads
  const [pendingFiles, setPendingFiles] = useState<ChatAttachment[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // SSE
  const [sseConnected, setSseConnected] = useState(false);

  // Activity panel
  const [activityEvents, setActivityEvents] = useState<LiveSSEEvent[]>([]);
  const [activityPanelOpen, setActivityPanelOpen] = useState(false);
  const manualPanelOverride = useRef(false);
  const MAX_ACTIVITY_EVENTS = 15;

  // Refs
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const sseRef = useRef<EventSource | null>(null);
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sessionKeyRef = useRef<string | null>(null);
  const boardIdRef = useRef<string | null>(null);

  // Keep refs in sync for SSE/polling callbacks
  useEffect(() => {
    sessionKeyRef.current = sessionKey;
  }, [sessionKey]);
  useEffect(() => {
    boardIdRef.current = boardId;
  }, [boardId]);

  // ─── Resolve The Claw's session on mount ──────────────────────────────────

  useEffect(() => {
    if (!isSignedIn || !boardId) {
      if (!boardResolving && !boardId) {
        setResolveError("No boards with a gateway found. Create a board first.");
        setResolving(false);
      }
      return;
    }
    let cancelled = false;

    (async () => {
      try {
        const raw: any = await customFetch(
          `/api/v1/gateways/sessions?board_id=${boardId}`,
          { method: "GET" },
        );
        if (cancelled) return;
        const data = raw?.data ?? raw;
        const list: GatewaySession[] = (data?.sessions || []).filter(
          (s: any) => typeof s === "object" && s !== null && s.key,
        );
        setAllSessions(list);
        const claw = findClawSession(list);
        if (claw) {
          setMainSessionKey(claw.key);
          setSessionKey(claw.key);
          markSessionRead(claw.key);
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
  }, [isSignedIn, boardId, boardResolving]);

  // ─── Poll session tokens ───────────────────────────────────────────────────

  useEffect(() => {
    if (!isSignedIn || !sessionKey || !boardId) return;
    const interval = setInterval(async () => {
      const bid = boardIdRef.current;
      if (!bid) return;
      try {
        const raw: any = await customFetch(
          `/api/v1/gateways/sessions?board_id=${bid}`,
          { method: "GET" },
        );
        const data = raw?.data ?? raw;
        const list: GatewaySession[] = (data?.sessions || []).filter(
          (s: any) => typeof s === "object" && s !== null && s.key,
        );
        setAllSessions(list);
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
  }, [isSignedIn, sessionKey, boardId]);

  // ─── Fetch chat history ───────────────────────────────────────────────────

  const fetchHistory = useCallback(async (key: string) => {
    if (!boardId) return;
    setMessagesLoading(true);
    try {
      const raw: any = await customFetch(
        `/api/v1/gateways/sessions/${encodeURIComponent(key)}/history?board_id=${boardId}`,
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
  }, [boardId]);

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
    let cancelled = false;
    let es: EventSource | null = null;

    // Fetch auth token async (Clerk is async, local/wechat are sync)
    void getToken().then((token) => {
      if (cancelled || !token) return;
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || "";
      const url = `${baseUrl}/api/v1/activity/live/stream?token=${encodeURIComponent(token)}`;
      es = new EventSource(url);
      sseRef.current = es;

      es.onopen = () => setSseConnected(true);
      es.onerror = () => setSseConnected(false);

      es.addEventListener("activity", (e) => {
        try {
          const data: LiveSSEEvent = JSON.parse(e.data);
          const eventType = data.event_type || "";

          // Accept events from any agent on this org — web chat uses
          // dynamic gateway agent IDs that don't match static names
          const ignoredTypes = ["cron."];
          if (ignoredTypes.some((t) => eventType.startsWith(t))) return;

          // Accumulate for activity panel
          setActivityEvents((prev) => {
            const next = [...prev, data];
            return next.length > MAX_ACTIVITY_EVENTS
              ? next.slice(next.length - MAX_ACTIVITY_EVENTS)
              : next;
          });

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
            // Auto-expand activity panel (unless user manually toggled)
            if (!manualPanelOverride.current) {
              setActivityPanelOpen(true);
            }
          }

          // Agent responded — refetch history
          if (
            eventType.includes("responded") ||
            eventType.includes("completed")
          ) {
            setAgentTyping(false);
            if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
            // Auto-collapse activity panel
            if (!manualPanelOverride.current) {
              setActivityPanelOpen(false);
            }
            manualPanelOverride.current = false;
            const currentKey = sessionKeyRef.current;
            if (currentKey) {
              setTimeout(() => void fetchHistory(currentKey), 500);
            }

          }
        } catch {
          /* ignore parse errors */
        }
      });
    });

    return () => {
      cancelled = true;
      es?.close();
      sseRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSignedIn, fetchHistory]);

  // ─── File upload helpers ──────────────────────────────────────────────────

  const uploadFile = useCallback(async (file: File): Promise<ChatAttachment | null> => {
    if (!sessionKey) return null;
    if (!ALLOWED_UPLOAD_TYPES.has(file.type)) {
      alert(`File type "${file.type || "unknown"}" is not supported.`);
      return null;
    }
    if (file.size > MAX_UPLOAD_SIZE) {
      alert(`File too large (${(file.size / 1024 / 1024).toFixed(1)} MB, max 10 MB).`);
      return null;
    }

    const formData = new FormData();
    formData.append("file", file);

    const baseUrl = process.env.NEXT_PUBLIC_API_URL || "";
    const bid = boardIdRef.current;
    if (!bid) return null;
    const url = `${baseUrl}/api/v1/gateways/sessions/${encodeURIComponent(sessionKey)}/upload?board_id=${bid}`;

    // Build auth headers (can't use customFetch — it forces Content-Type: application/json)
    const headers: Record<string, string> = {};
    const localToken = typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;
    if (localToken) {
      headers["Authorization"] = `Bearer ${localToken}`;
    } else {
      const clerk = (window as unknown as { Clerk?: { session?: { getToken: () => Promise<string> } } }).Clerk;
      if (clerk?.session) {
        try { headers["Authorization"] = `Bearer ${await clerk.session.getToken()}`; } catch { /* ignore */ }
      }
    }

    const res = await fetch(url, { method: "POST", headers, body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Upload failed" }));
      alert((err as { detail?: string }).detail || "Upload failed");
      return null;
    }
    const data = (await res.json()) as ChatAttachment;
    // Create local preview for images
    if (file.type.startsWith("image/")) {
      data.preview_url = URL.createObjectURL(file);
    }
    return data;
  }, [sessionKey]);

  const handleFileSelect = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      const results = await Promise.all(
        Array.from(files).map((f) => uploadFile(f)),
      );
      const uploaded = results.filter((r): r is ChatAttachment => r !== null);
      if (uploaded.length > 0) {
        setPendingFiles((prev) => [...prev, ...uploaded]);
      }
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }, [uploadFile]);

  const removePendingFile = useCallback((idx: number) => {
    setPendingFiles((prev) => {
      const removed = prev[idx];
      if (removed?.preview_url) URL.revokeObjectURL(removed.preview_url);
      return prev.filter((_, i) => i !== idx);
    });
  }, []);

  // ─── Send message ─────────────────────────────────────────────────────────

  const sendMessage = useCallback(async () => {
    if (!sessionKey || isSending) return;
    if (!input.trim() && pendingFiles.length === 0) return;

    const content = input.trim() || (pendingFiles.length > 0 ? "Please review the attached file(s)." : "");
    const attachments = pendingFiles.length > 0 ? [...pendingFiles] : undefined;
    setInput("");
    setPendingFiles([]);
    setIsSending(true);

    // Optimistic: add user message immediately
    const displayContent = attachments
      ? `${attachments.map((a) => `📎 ${a.filename}`).join("\n")}\n\n${content}`
      : content;
    const optimisticMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: displayContent,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticMsg]);
    setAgentTyping(true);

    try {
      const body: Record<string, unknown> = { content };
      if (attachments) {
        body.attachments = attachments.map(({ filename, workspace_path, content_type, size_bytes, sanitized_workspace_path }) => ({
          filename, workspace_path, content_type, size_bytes, sanitized_workspace_path,
        }));
      }
      await customFetch(
        `/api/v1/gateways/sessions/${encodeURIComponent(sessionKey)}/message?board_id=${boardId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
    } catch {
      setMessages((prev) => prev.filter((m) => m.id !== optimisticMsg.id));
      setInput(content);
      if (attachments) setPendingFiles(attachments);
      setAgentTyping(false);
    } finally {
      setIsSending(false);
      textareaRef.current?.focus();
    }
  }, [sessionKey, input, isSending, pendingFiles, boardId]);

  // ─── Safety-net polling while agent is working ─────────────────────────────
  // Always poll when agentTyping, even if SSE is connected — SSE provides
  // instant refetch on responded/completed events, but if the event is missed
  // (wrong type, dropped connection) this catches it within 3s.
  const lastMessageCountRef = useRef(0);
  useEffect(() => {
    lastMessageCountRef.current = messages.length;
  }, [messages]);

  useEffect(() => {
    if (!agentTyping || !sessionKey) return;
    const countBefore = lastMessageCountRef.current;
    const poll = setInterval(async () => {
      const bid = boardIdRef.current;
      if (!bid) return;
      try {
        const raw: any = await customFetch(
          `/api/v1/gateways/sessions/${encodeURIComponent(sessionKey)}/history?board_id=${bid}`,
          { method: "GET" },
        );
        const data = raw?.data ?? raw;
        const history = Array.isArray(data?.history) ? data.history : [];
        const parsed = parseHistory(history);
        // If we got more messages than before sending, agent has responded
        if (parsed.length > countBefore) {
          setMessages(parsed);
          setAgentTyping(false);
          if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
        }
      } catch { /* ignore */ }
    }, 3000);
    return () => clearInterval(poll);
  }, [agentTyping, sessionKey]);

  // ─── Session commands ─────────────────────────────────────────────────────

  const [commandLoading, setCommandLoading] = useState<string | null>(null);

  const abortChat = useCallback(async () => {
    if (!sessionKey) return;
    try {
      await customFetch(
        `/api/v1/gateways/sessions/${encodeURIComponent(sessionKey)}/abort?board_id=${boardId}`,
        { method: "POST" },
      );
    } catch { /* ignore */ }
    setAgentTyping(false);
    if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    // Refetch to get whatever partial response was generated
    setTimeout(() => { if (sessionKey) void fetchHistory(sessionKey); }, 500);
  }, [sessionKey, boardId, fetchHistory]);

  const compactChat = useCallback(async () => {
    if (!sessionKey || commandLoading) return;
    setCommandLoading("compact");
    try {
      await customFetch(
        `/api/v1/gateways/sessions/${encodeURIComponent(sessionKey)}/compact?board_id=${boardId}`,
        { method: "POST" },
      );
      await fetchHistory(sessionKey);
    } catch { /* ignore */ }
    finally { setCommandLoading(null); }
  }, [sessionKey, boardId, commandLoading, fetchHistory]);

  const clearChat = useCallback(async () => {
    if (!sessionKey || commandLoading) return;
    if (!window.confirm("Clear the entire conversation? This cannot be undone.")) return;
    setCommandLoading("clear");
    try {
      await customFetch(
        `/api/v1/gateways/sessions/${encodeURIComponent(sessionKey)}/reset?board_id=${boardId}`,
        { method: "POST" },
      );
      await fetchHistory(sessionKey);
    } catch { /* ignore */ }
    finally { setCommandLoading(null); }
  }, [sessionKey, boardId, commandLoading, fetchHistory]);

  // ─── Session CRUD (multi-session) ─────────────────────────────────────────

  const refreshSessions = useCallback(async () => {
    const bid = boardIdRef.current;
    if (!bid) return;
    try {
      const raw: any = await customFetch(
        `/api/v1/gateways/sessions?board_id=${bid}`,
        { method: "GET" },
      );
      const data = raw?.data ?? raw;
      const list: GatewaySession[] = (data?.sessions || []).filter(
        (s: any) => typeof s === "object" && s !== null && s.key,
      );
      setAllSessions(list);
    } catch { /* ignore */ }
  }, []);

  const createSession = useCallback(async (label: string) => {
    if (!boardId) return;
    try {
      const raw: any = await customFetch(
        `/api/v1/gateways/sessions?board_id=${boardId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ label }),
        },
      );
      const data = raw?.data ?? raw;
      if (data?.session_key) {
        setSessionKey(data.session_key);
        setSessionTokens({ total: 0, input: 0, output: 0, model: "" });
      }
      await refreshSessions();
    } catch { /* ignore */ }
  }, [boardId, refreshSessions]);

  const renameSession = useCallback(async (key: string, label: string) => {
    if (!boardId) return;
    try {
      await customFetch(
        `/api/v1/gateways/sessions/${encodeURIComponent(key)}?board_id=${boardId}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ label }),
        },
      );
      await refreshSessions();
    } catch { /* ignore */ }
  }, [boardId, refreshSessions]);

  const deleteSession = useCallback(async (key: string) => {
    if (!boardId) return;
    try {
      await customFetch(
        `/api/v1/gateways/sessions/${encodeURIComponent(key)}/reset?board_id=${boardId}`,
        { method: "POST" },
      );
      if (sessionKey === key) {
        setSessionKey(mainSessionKey);
      }
      await refreshSessions();
    } catch { /* ignore */ }
  }, [boardId, sessionKey, mainSessionKey, refreshSessions]);

  const toggleActivityPanel = useCallback(() => {
    manualPanelOverride.current = true;
    setActivityPanelOpen((prev) => !prev);
  }, []);

  const handleSelectSession = useCallback((key: string) => {
    if (key === sessionKey) return;
    setSessionKey(key);
    setAgentTyping(false);
    setActivityEvents([]);
    setActivityPanelOpen(false);
    manualPanelOverride.current = false;
    markSessionRead(key);
    // Update token display from allSessions
    const match = allSessions.find((s) => s.key === key);
    if (match) {
      setSessionTokens({
        total: match.totalTokens ?? 0,
        input: match.inputTokens ?? 0,
        output: match.outputTokens ?? 0,
        model: match.model ?? "",
      });
    } else {
      setSessionTokens(null);
    }
  }, [sessionKey, allSessions]);

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
      <div className="flex h-full">
        {/* ─── Session sidebar ───────────────────────────────────────── */}
        {sidebarOpen && (
          <div className="hidden md:block">
            <ChatSessionSidebar
              sessions={allSessions}
              activeSessionKey={sessionKey}
              mainSessionKey={mainSessionKey}
              unreadSessions={unreadSessions}
              onSelectSession={handleSelectSession}
              onCreateSession={createSession}
              onRenameSession={renameSession}
              onDeleteSession={deleteSession}
              onClose={() => setSidebarOpen(false)}
              isLoading={resolving}
            />
          </div>
        )}
        {/* Mobile sidebar overlay */}
        {sidebarOpen && (
          <div className="fixed inset-0 z-40 md:hidden">
            <div className="absolute inset-0 bg-black/40" onClick={() => setSidebarOpen(false)} />
            <div className="relative z-50 h-full">
              <ChatSessionSidebar
                sessions={allSessions}
                activeSessionKey={sessionKey}
                mainSessionKey={mainSessionKey}
                unreadSessions={unreadSessions}
                onSelectSession={(key) => { handleSelectSession(key); setSidebarOpen(false); }}
                onCreateSession={createSession}
                onRenameSession={renameSession}
                onDeleteSession={deleteSession}
                onClose={() => setSidebarOpen(false)}
                isLoading={resolving}
              />
            </div>
          </div>
        )}

        {/* ─── Main chat area ────────────────────────────────────────── */}
        <div className="flex h-full flex-1 flex-col min-w-0">
        {/* ─── Header bar ──────────────────────────────────────────────── */}
        <div className="flex items-center justify-between border-b border-[color:var(--border)] bg-[color:var(--surface)] px-4 py-3">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="rounded-md p-2.5 sm:p-1.5 text-[color:var(--text-quiet)] hover:bg-[color:var(--surface-muted)] hover:text-[color:var(--text)] transition"
              title={sidebarOpen ? "Hide conversations" : "Show conversations"}
            >
              <PanelLeft className="h-5 w-5 sm:h-4 sm:w-4" />
            </button>
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-500">
              <Bot className="h-4.5 w-4.5 text-white" />
            </div>
            <div>
              <p className="text-sm font-medium text-[color:var(--text)]">
                {sessionKey === mainSessionKey ? "The Claw" : (allSessions.find((s) => s.key === sessionKey)?.displayName || "Conversation")}
              </p>
              {agentTyping ? (
                <p className="text-xs text-emerald-600">typing...</p>
              ) : (
                <p className="text-xs text-[color:var(--text-quiet)]">
                  {sessionKey === mainSessionKey ? "#general" : "chat session"}
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
                  className="rounded-md p-2.5 sm:p-1.5 text-[color:var(--text-quiet)] hover:bg-[color:var(--surface-muted)] hover:text-[color:var(--text)] transition disabled:opacity-40"
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
                  className="rounded-md p-2.5 sm:p-1.5 text-[color:var(--text-quiet)] hover:bg-[color:var(--surface-muted)] hover:text-rose-500 transition disabled:opacity-40"
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
                <div className="hidden sm:flex items-center gap-2 ml-1" title={`${sessionTokens.total.toLocaleString()} / ${maxTokens.toLocaleString()} tokens (${sessionTokens.input.toLocaleString()} in / ${sessionTokens.output.toLocaleString()} out)`}>
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
                    <span className="hidden sm:inline text-[10px] tabular-nums text-[color:var(--text-quiet)]">
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
        <div className="flex-1 overflow-y-auto overflow-x-hidden px-3 py-4 space-y-4 sm:px-4">
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
                    className="rounded-full border border-[color:var(--border)] bg-[color:var(--surface)] px-3 py-1.5 md:px-4 md:py-2 text-xs text-[color:var(--text)] hover:bg-[color:var(--surface-muted)] transition"
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
                <div>
                  <div
                    className={cn(
                      "max-w-[90%] md:max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
                      msg.role === "user"
                        ? "bg-[color:var(--accent-strong)] text-white rounded-br-md"
                        : "bg-[color:var(--surface-muted)] text-[color:var(--text)] rounded-bl-md",
                    )}
                  >
                    {msg.role === "user" ? (
                      <p className="whitespace-pre-wrap break-words">{typeof msg.content === "string" ? msg.content : String(msg.content)}</p>
                    ) : (
                      <div className="break-words [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                        <Markdown content={typeof msg.content === "string" ? msg.content : String(msg.content)} variant="description" />
                      </div>
                    )}
                  </div>
                  {formatMessageTime(msg.timestamp) && (
                    <p className={cn(
                      "mt-1 text-[10px] text-[color:var(--text-quiet)]",
                      msg.role === "user" ? "text-right" : "text-left",
                    )}>
                      {formatMessageTime(msg.timestamp)}
                    </p>
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

        {/* ─── Activity panel ────────────────────────────────────────── */}
        {(activityEvents.length > 0 || agentTyping) && (
          <ChatActivityPanel
            events={activityEvents}
            isOpen={activityPanelOpen}
            onToggle={toggleActivityPanel}
            onAbort={abortChat}
            agentTyping={agentTyping}
          />
        )}

        {/* ─── Input area ──────────────────────────────────────────────── */}
        {!resolving && !resolveError ? (
          <div className="border-t border-[color:var(--border)] bg-[color:var(--surface)] px-3 py-3 sm:p-4">
            <div className="mx-auto max-w-3xl">
              {/* Pending file chips */}
              {pendingFiles.length > 0 ? (
                <div className="mb-2 flex flex-wrap gap-2">
                  {pendingFiles.map((att, idx) => (
                    <div
                      key={`${att.workspace_path}-${idx}`}
                      className="flex items-center gap-1.5 rounded-lg border border-[color:var(--border)] bg-[color:var(--surface-muted)] px-2.5 py-1.5 text-xs text-[color:var(--text)]"
                    >
                      {att.preview_url ? (
                        <img src={att.preview_url} alt="" className="h-6 w-6 rounded object-cover" />
                      ) : att.content_type === "application/pdf" ? (
                        <FileText className="h-4 w-4 text-rose-500" />
                      ) : att.content_type.startsWith("image/") ? (
                        <ImageIcon className="h-4 w-4 text-blue-500" />
                      ) : (
                        <FileText className="h-4 w-4 text-[color:var(--text-quiet)]" />
                      )}
                      <span className="max-w-[120px] truncate">{att.filename}</span>
                      <span className="text-[color:var(--text-quiet)]">
                        {att.size_bytes < 1024 ? `${att.size_bytes}B` : `${(att.size_bytes / 1024).toFixed(0)}KB`}
                      </span>
                      <button
                        onClick={() => removePendingFile(idx)}
                        className="ml-0.5 rounded p-0.5 hover:bg-[color:var(--surface)] transition"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}
              <div className="flex gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  accept="image/*,.pdf,.txt,.csv,.md,.json,.docx,.xlsx"
                  onChange={(e) => void handleFileSelect(e.target.files)}
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading || isSending}
                  title="Attach a file"
                  className="shrink-0 flex h-[44px] w-[44px] items-center justify-center rounded-md text-[color:var(--text-quiet)] hover:bg-[color:var(--surface-muted)] hover:text-[color:var(--text)] transition disabled:opacity-40"
                >
                  {uploading ? (
                    <Loader2 className="h-4.5 w-4.5 animate-spin" />
                  ) : (
                    <Paperclip className="h-4.5 w-4.5" />
                  )}
                </button>
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
                  onPaste={(e) => {
                    const items = e.clipboardData?.items;
                    if (!items) return;
                    const files: File[] = [];
                    for (let i = 0; i < items.length; i++) {
                      const item = items[i];
                      if (item.kind === "file") {
                        const file = item.getAsFile();
                        if (file) files.push(file);
                      }
                    }
                    if (files.length > 0) {
                      e.preventDefault();
                      const dt = new DataTransfer();
                      files.forEach((f) => dt.items.add(f));
                      void handleFileSelect(dt.files);
                    }
                  }}
                  placeholder={pendingFiles.length > 0 ? "Add a message or press Enter to send..." : "Message The Claw..."}
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
                    disabled={isSending || (!input.trim() && pendingFiles.length === 0)}
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
          </div>
        ) : null}
      </div>
      </div>
    </DashboardPageLayout>
  );
}
