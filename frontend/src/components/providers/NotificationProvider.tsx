"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { useAuth } from "@/auth/clerk";
import { X, Bell, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import { useOrganizationMembership } from "@/lib/use-organization-membership";

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
  /** Count of silent-disk cron reports landed since the user last opened
   *  the Reports tab. Scoped to the current org via localStorage. */
  unreadReportsCount: number;
  /** Mark the Reports tab as read (clears badge for current org). */
  markReportsRead: () => void;
}

const NotificationContext = createContext<NotificationContextValue>({
  notify: () => {},
  unreadSessions: new Set(),
  markSessionRead: () => {},
  unreadReportsCount: 0,
  markReportsRead: () => {},
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

// ── Unread-reports store ──────────────────────────────────────────────
// localStorage is the source of truth, scoped per-org. We expose it via a
// small subscribe/getSnapshot store so consumers can read it through
// useSyncExternalStore — that keeps render-time reads consistent across
// org switches without setState-in-effect.

const REPORTS_STORAGE_PREFIX = "vc:unreadReports:";

type ReportsListener = () => void;
const reportsListeners = new Set<ReportsListener>();

function reportsKey(orgId: string | null | undefined): string | null {
  return orgId ? `${REPORTS_STORAGE_PREFIX}${orgId}` : null;
}

function readUnreadReports(orgId: string | null | undefined): number {
  const key = reportsKey(orgId);
  if (!key || typeof window === "undefined") return 0;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return 0;
    const n = Number.parseInt(raw, 10);
    return Number.isFinite(n) && n > 0 ? n : 0;
  } catch {
    return 0;
  }
}

function writeUnreadReports(orgId: string | null | undefined, count: number): void {
  const key = reportsKey(orgId);
  if (!key || typeof window === "undefined") return;
  try {
    if (count <= 0) {
      window.localStorage.removeItem(key);
    } else {
      window.localStorage.setItem(key, String(count));
    }
  } catch {
    /* ignore quota / disabled storage */
  }
  reportsListeners.forEach((fn) => fn());
}

function bumpUnreadReports(orgId: string | null | undefined): void {
  if (!orgId) return;
  writeUnreadReports(orgId, readUnreadReports(orgId) + 1);
}

function subscribeReports(listener: ReportsListener): () => void {
  reportsListeners.add(listener);
  return () => {
    reportsListeners.delete(listener);
  };
}

function useUnreadReportsCount(orgId: string | null | undefined): number {
  return useSyncExternalStore(
    subscribeReports,
    () => readUnreadReports(orgId),
    () => 0, // SSR snapshot
  );
}

export function NotificationProvider({ children }: { children: ReactNode }) {
  const { isSignedIn, getToken } = useAuth();
  const { member } = useOrganizationMembership(isSignedIn);
  const orgId = member?.organization_id ?? null;
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [unreadSessions, setUnreadSessions] = useState<Set<string>>(new Set());
  const unreadReportsCount = useUnreadReportsCount(orgId);
  const activeSessionRef = useRef<string | null>(null);
  const sseRef = useRef<EventSource | null>(null);
  const orgIdRef = useRef<string | null>(null);

  // Keep the latest orgId in a ref so the SSE handler reads the current
  // org without re-binding the listener on every org switch. Effect-only
  // write — no setState, just mirroring an external React value into a ref.
  useEffect(() => {
    orgIdRef.current = orgId;
  }, [orgId]);

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

  // ── Unread reports tracking (silent-disk cron outputs) ────────────────
  // Count itself is sourced from useUnreadReportsCount() above (backed by
  // localStorage via useSyncExternalStore). markReportsRead writes through
  // the store, which notifies subscribers — no local setState needed.

  const markReportsRead = useCallback(() => {
    writeUnreadReports(orgIdRef.current, 0);
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
          // Backend normaliser maps gateway `deliveryStatus` → delivery_mode:
          //   "announce" (delivered)     → silent toast (already notified elsewhere)
          //   "webhook"  (delivered)     → silent toast (downstream handles)
          //   "none"     (not-requested) → "New report available" → /memory?tab=reports
          //   "error"    (not-delivered) → warn toast (delivery attempted but failed)
          //   null/unknown               → legacy "Check the conversation" → /chat
          if (eventType === "cron.completed") {
            const jobName =
              (data.metadata?.name as string) ||
              (data.metadata?.summary as string) ||
              data.agent_name ||
              "Scheduled task";
            const deliveryMode = data.metadata?.delivery_mode as string | null | undefined;
            if (deliveryMode === "announce" || deliveryMode === "webhook") {
              // Already notified via Discord / webhook; don't duplicate.
            } else if (deliveryMode === "none") {
              notify({
                title: "New report available",
                body: `${jobName} completed. Report saved to memory.`,
                href: "/memory?tab=reports",
                variant: "success",
              });
              // Bump the per-org unread-reports counter so the sidebar
              // Memory entry can show a badge until the user opens the
              // Reports tab.
              bumpUnreadReports(orgIdRef.current);
            } else if (deliveryMode === "error") {
              notify({
                title: "Cron delivery failed",
                body: `${jobName} finished but delivery was not confirmed.`,
                href: "/cron-jobs",
                variant: "warning",
              });
            } else {
              notify({
                title: "Cron job completed",
                body: `${jobName} finished. Check the conversation for results.`,
                href: "/chat",
                variant: "success",
              });
            }
          }

          // ── Cron job failed ────────────────────────────────────
          // Always toast errors regardless of delivery.mode — silent-disk crons
          // failing are exactly the case where the user needs to know.
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
    <NotificationContext.Provider
      value={{
        notify,
        unreadSessions,
        markSessionRead,
        unreadReportsCount,
        markReportsRead,
      }}
    >
      {children}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </NotificationContext.Provider>
  );
}
