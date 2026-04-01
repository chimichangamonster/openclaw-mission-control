"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useAuth } from "@/auth/clerk";
import { X, Bell, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Toast types
// ---------------------------------------------------------------------------

interface Toast {
  id: string;
  title: string;
  body: string;
  href?: string; // optional link (e.g., to chat page)
  variant?: "info" | "success" | "warning";
  createdAt: number;
}

interface NotificationContextValue {
  /** Push a toast notification visible on any page. */
  notify: (toast: Omit<Toast, "id" | "createdAt">) => void;
  /** Set of session keys that have unread agent messages. */
  unreadSessions: Set<string>;
  /** Mark a session as read (user opened it). */
  markSessionRead: (sessionKey: string) => void;
}

const NotificationContext = createContext<NotificationContextValue>({
  notify: () => {},
  unreadSessions: new Set(),
  markSessionRead: () => {},
});

export function useNotifications() {
  return useContext(NotificationContext);
}

// ---------------------------------------------------------------------------
// Toast display
// ---------------------------------------------------------------------------

const TOAST_DURATION = 8000; // auto-dismiss after 8s

function ToastContainer({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: string) => void }) {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[9999] flex flex-col-reverse gap-2 max-w-sm">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={cn(
            "flex items-start gap-3 rounded-lg border px-4 py-3 shadow-lg animate-in slide-in-from-right-5 fade-in duration-300",
            "bg-[color:var(--surface)] border-[color:var(--border)] text-[color:var(--text)]",
          )}
        >
          <Bell className={cn(
            "h-4 w-4 mt-0.5 shrink-0",
            t.variant === "success" ? "text-emerald-500"
              : t.variant === "warning" ? "text-amber-500"
              : "text-blue-500",
          )} />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium">{t.title}</p>
            <p className="mt-0.5 text-xs text-[color:var(--text-quiet)] line-clamp-2">{t.body}</p>
            {t.href && (
              <a
                href={t.href}
                className="mt-1.5 inline-flex items-center gap-1 text-xs text-[color:var(--accent)] hover:underline"
              >
                View <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
          <button
            onClick={() => onDismiss(t.id)}
            className="shrink-0 rounded p-0.5 text-[color:var(--text-quiet)] hover:text-[color:var(--text)] transition"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function NotificationProvider({ children }: { children: ReactNode }) {
  const { isSignedIn, getToken } = useAuth();
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [unreadSessions, setUnreadSessions] = useState<Set<string>>(new Set());
  const activeSessionRef = useRef<string | null>(null);
  const sseRef = useRef<EventSource | null>(null);

  // ── Toast management ──────────────────────────────────────────────────

  const notify = useCallback((toast: Omit<Toast, "id" | "createdAt">) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    setToasts((prev) => [...prev, { ...toast, id, createdAt: Date.now() }]);
    // Auto-dismiss
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, TOAST_DURATION);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // ── Unread session tracking ───────────────────────────────────────────

  const markSessionRead = useCallback((sessionKey: string) => {
    activeSessionRef.current = sessionKey;
    setUnreadSessions((prev) => {
      if (!prev.has(sessionKey)) return prev;
      const next = new Set(prev);
      next.delete(sessionKey);
      return next;
    });
  }, []);

  // ── Global SSE listener for cron + agent events ───────────────────────

  useEffect(() => {
    if (!isSignedIn) return;
    let cancelled = false;

    void getToken().then((token) => {
      if (cancelled || !token) return;
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || "";
      const url = `${baseUrl}/api/v1/activity/live/stream?token=${encodeURIComponent(token)}`;
      const es = new EventSource(url);
      sseRef.current = es;

      es.addEventListener("activity", (e) => {
        try {
          const data = JSON.parse(e.data) as {
            event_type: string;
            agent_name: string;
            message: string;
            metadata: Record<string, unknown>;
            timestamp: string;
          };

          const eventType = data.event_type || "";

          // ── Cron job completed ─────────────────────────────────
          if (eventType === "cron.completed") {
            const jobName = data.metadata?.name as string || data.agent_name || "Scheduled task";
            notify({
              title: "Cron job completed",
              body: `${jobName} finished. Check the conversation for results.`,
              href: "/chat",
              variant: "success",
            });
          }

          // ── Cron job failed ────────────────────────────────────
          if (eventType === "cron.error") {
            const jobName = data.metadata?.name as string || data.agent_name || "Scheduled task";
            notify({
              title: "Cron job failed",
              body: `${jobName} encountered an error.`,
              href: "/cron-jobs",
              variant: "warning",
            });
          }

          // ── Agent responded in a session (unread tracking) ────
          if (eventType.includes("responded") || eventType.includes("completed")) {
            // If there's a session key in metadata, mark it as unread
            // (unless the user is currently viewing that session)
            const sessionKey = data.metadata?.sessionKey as string | undefined;
            if (sessionKey && sessionKey !== activeSessionRef.current) {
              setUnreadSessions((prev) => {
                if (prev.has(sessionKey)) return prev;
                const next = new Set(prev);
                next.add(sessionKey);
                return next;
              });
            }
          }
        } catch {
          /* ignore parse errors */
        }
      });

      es.onerror = () => {
        /* EventSource auto-reconnects */
      };
    });

    return () => {
      cancelled = true;
      sseRef.current?.close();
      sseRef.current = null;
    };
  }, [isSignedIn, getToken, notify]);

  return (
    <NotificationContext.Provider value={{ notify, unreadSessions, markSessionRead }}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </NotificationContext.Provider>
  );
}
