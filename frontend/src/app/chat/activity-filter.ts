import type { LiveSSEEvent } from "@/components/ChatActivityPanel";

/**
 * Should an incoming SSE activity event be shown in the /chat page's
 * activity panel?
 *
 * The panel is scoped to the currently-viewed chat session. Backend
 * tags chat + agent events with `channel = sessionKey`. Cron and
 * gateway-wide events carry a different (or empty) channel and are
 * surfaced elsewhere — cron toasts via NotificationProvider, gateway
 * lifecycle events via the page-level SSE status dot.
 *
 * This is the filter that prevents cross-session leakage: e.g. a
 * Personal trading cron firing while the user is viewing a Vantage
 * chat session should NOT show up as "Morning Scan stuck..." in the
 * Vantage panel.
 */
export function shouldAcceptActivityEvent(
  event: LiveSSEEvent,
  activeSessionKey: string | null,
): boolean {
  if (!activeSessionKey) return false;
  return event.channel === activeSessionKey;
}
