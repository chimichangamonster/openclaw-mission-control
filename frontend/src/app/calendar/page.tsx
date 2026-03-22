"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import {
  Calendar as CalendarIcon,
  Plus,
  MapPin,
  Clock,
  ChevronDown,
  ChevronUp,
  Trash2,
  ExternalLink,
  Users,
  X,
} from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { FeatureGate } from "@/components/molecules/FeatureGate";
import { customFetch } from "@/api/mutator";

interface CalendarEvent {
  id: string;
  summary: string;
  description: string;
  location: string;
  start: string;
  end: string;
  time_zone: string;
  status: string;
  html_link: string;
  attendees: { email: string; response: string }[];
  created: string;
  updated: string;
}

function formatDateTime(isoStr: string): string {
  if (!isoStr) return "";
  // All-day event (date only)
  if (isoStr.length <= 10) {
    const d = new Date(isoStr + "T00:00:00");
    return d.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  }
  const d = new Date(isoStr);
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  }) + " " + d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

function isAllDay(start: string): boolean {
  return start.length <= 10;
}

export default function CalendarPage() {
  const { isSignedIn } = useAuth();
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  // Create form state
  const [newSummary, setNewSummary] = useState("");
  const [newDate, setNewDate] = useState("");
  const [newStartTime, setNewStartTime] = useState("09:00");
  const [newEndTime, setNewEndTime] = useState("10:00");
  const [newAllDay, setNewAllDay] = useState(false);
  const [newLocation, setNewLocation] = useState("");
  const [newDescription, setNewDescription] = useState("");

  const loadStatus = useCallback(async () => {
    try {
      const raw: any = await customFetch("/api/v1/google-calendar/status", { method: "GET" });
      const data = raw?.data ?? raw;
      setConnected(data?.connected ?? false);
    } catch {
      setConnected(false);
    }
  }, []);

  const loadEvents = useCallback(async () => {
    try {
      setLoading(true);
      // Fetch next 30 days of events
      const now = new Date();
      const future = new Date();
      future.setDate(future.getDate() + 30);
      const raw: any = await customFetch(
        `/api/v1/google-calendar/events?time_min=${now.toISOString()}&time_max=${future.toISOString()}&max_results=50`,
        { method: "GET" },
      );
      const data = raw?.data ?? raw;
      setEvents(data?.events ?? []);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isSignedIn) {
      loadStatus().then(() => loadEvents());
    }
  }, [isSignedIn, loadStatus, loadEvents]);

  const handleCreate = async () => {
    if (!newSummary || !newDate) return;
    try {
      setCreating(true);
      const body: any = {
        summary: newSummary,
        description: newDescription,
        location: newLocation,
        time_zone: "America/Edmonton",
      };
      if (newAllDay) {
        body.start = newDate;
        // Google all-day end is exclusive — add one day
        const endDate = new Date(newDate + "T00:00:00");
        endDate.setDate(endDate.getDate() + 1);
        body.end = endDate.toISOString().split("T")[0];
      } else {
        body.start = `${newDate}T${newStartTime}:00`;
        body.end = `${newDate}T${newEndTime}:00`;
      }
      await customFetch("/api/v1/google-calendar/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      // Reset form
      setNewSummary("");
      setNewDate("");
      setNewStartTime("09:00");
      setNewEndTime("10:00");
      setNewAllDay(false);
      setNewLocation("");
      setNewDescription("");
      setShowCreate(false);
      await loadEvents();
    } catch {
      // ignore
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (eventId: string) => {
    try {
      setDeleting(eventId);
      await customFetch(`/api/v1/google-calendar/events/${eventId}`, { method: "DELETE" });
      setEvents((prev) => prev.filter((e) => e.id !== eventId));
      setExpandedId(null);
    } catch {
      // ignore
    } finally {
      setDeleting(null);
    }
  };

  if (!isSignedIn) return null;

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to view your calendar.",
        forceRedirectUrl: "/calendar",
        signUpForceRedirectUrl: "/calendar",
      }}
      title="Calendar"
      description="Manage your schedule and appointments."
    >
      <FeatureGate flag="google_calendar" label="Google Calendar">
        <div className="mx-auto max-w-3xl space-y-6 p-6">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold text-[color:var(--text)]">Calendar</h1>
              <p className="text-sm text-[color:var(--text-muted)]">
                {connected
                  ? "Upcoming events from Google Calendar"
                  : "Connect Google Calendar in Org Settings to get started"}
              </p>
            </div>
            {connected && (
              <button
                onClick={() => setShowCreate(!showCreate)}
                className="inline-flex items-center gap-2 rounded-lg bg-[color:var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 transition"
              >
                {showCreate ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
                {showCreate ? "Cancel" : "New Event"}
              </button>
            )}
          </div>

          {/* Not connected */}
          {connected === false && (
            <div className="rounded-xl border border-dashed border-[color:var(--border)] bg-[color:var(--surface)] p-12 text-center">
              <CalendarIcon className="mx-auto h-12 w-12 text-[color:var(--text-quiet)]" />
              <h3 className="mt-4 text-lg font-semibold text-[color:var(--text)]">
                Google Calendar not connected
              </h3>
              <p className="mt-1 text-sm text-[color:var(--text-muted)]">
                Go to Org Settings to connect your Google Calendar account.
              </p>
            </div>
          )}

          {/* Create event form */}
          {showCreate && (
            <div className="rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] shadow-sm">
              <div className="border-b border-[color:var(--border)] px-5 py-3">
                <h2 className="text-sm font-semibold text-[color:var(--text)] flex items-center gap-2">
                  <Plus className="h-4 w-4" /> Create Event
                </h2>
              </div>
              <div className="p-5 space-y-4">
                <div>
                  <label className="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
                    Event Title *
                  </label>
                  <input
                    type="text"
                    value={newSummary}
                    onChange={(e) => setNewSummary(e.target.value)}
                    placeholder="Site visit, meeting, appointment..."
                    className="w-full rounded-lg border border-[color:var(--border)] bg-[color:var(--bg)] px-3 py-2 text-sm text-[color:var(--text)] focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
                      Date *
                    </label>
                    <input
                      type="date"
                      value={newDate}
                      onChange={(e) => setNewDate(e.target.value)}
                      className="w-full rounded-lg border border-[color:var(--border)] bg-[color:var(--bg)] px-3 py-2 text-sm text-[color:var(--text)] focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
                    />
                  </div>
                  <div className="flex items-end">
                    <label className="flex items-center gap-2 text-sm text-[color:var(--text-muted)]">
                      <input
                        type="checkbox"
                        checked={newAllDay}
                        onChange={(e) => setNewAllDay(e.target.checked)}
                        className="rounded"
                      />
                      All day
                    </label>
                  </div>
                </div>
                {!newAllDay && (
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
                        Start Time
                      </label>
                      <input
                        type="time"
                        value={newStartTime}
                        onChange={(e) => setNewStartTime(e.target.value)}
                        className="w-full rounded-lg border border-[color:var(--border)] bg-[color:var(--bg)] px-3 py-2 text-sm text-[color:var(--text)] focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
                        End Time
                      </label>
                      <input
                        type="time"
                        value={newEndTime}
                        onChange={(e) => setNewEndTime(e.target.value)}
                        className="w-full rounded-lg border border-[color:var(--border)] bg-[color:var(--bg)] px-3 py-2 text-sm text-[color:var(--text)] focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
                      />
                    </div>
                  </div>
                )}
                <div>
                  <label className="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
                    Location
                  </label>
                  <input
                    type="text"
                    value={newLocation}
                    onChange={(e) => setNewLocation(e.target.value)}
                    placeholder="123 Main St, Calgary, AB"
                    className="w-full rounded-lg border border-[color:var(--border)] bg-[color:var(--bg)] px-3 py-2 text-sm text-[color:var(--text)] focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
                    Description
                  </label>
                  <textarea
                    value={newDescription}
                    onChange={(e) => setNewDescription(e.target.value)}
                    rows={2}
                    placeholder="Notes, agenda, instructions..."
                    className="w-full rounded-lg border border-[color:var(--border)] bg-[color:var(--bg)] px-3 py-2 text-sm text-[color:var(--text)] focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none resize-none"
                  />
                </div>
                <div className="flex justify-end">
                  <button
                    onClick={handleCreate}
                    disabled={creating || !newSummary || !newDate}
                    className="inline-flex items-center gap-2 rounded-lg bg-[color:var(--accent)] px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50 transition"
                  >
                    {creating ? "Creating..." : "Create Event"}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Events list */}
          {connected && (
            <>
              {loading ? (
                <div className="flex justify-center py-12">
                  <div className="h-8 w-8 animate-spin rounded-full border-2 border-[color:var(--border)] border-t-blue-500" />
                </div>
              ) : events.length === 0 ? (
                <div className="rounded-xl border border-dashed border-[color:var(--border)] bg-[color:var(--surface)] p-12 text-center">
                  <CalendarIcon className="mx-auto h-12 w-12 text-[color:var(--text-quiet)]" />
                  <h3 className="mt-4 text-lg font-semibold text-[color:var(--text)]">
                    No upcoming events
                  </h3>
                  <p className="mt-1 text-sm text-[color:var(--text-muted)]">
                    Your next 30 days are clear. Create an event to get started.
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {events.map((event) => (
                    <div
                      key={event.id}
                      className="rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] transition"
                    >
                      <button
                        onClick={() =>
                          setExpandedId(expandedId === event.id ? null : event.id)
                        }
                        className="flex w-full items-center gap-4 px-5 py-4 text-left hover:bg-[color:var(--surface-muted)] rounded-xl transition"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-sm text-[color:var(--text)] truncate">
                              {event.summary || "(No title)"}
                            </span>
                            {isAllDay(event.start) && (
                              <span className="inline-flex items-center rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
                                All day
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-3 mt-1 text-xs text-[color:var(--text-muted)]">
                            <span className="flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              {formatDateTime(event.start)}
                            </span>
                            {event.location && (
                              <span className="flex items-center gap-1 truncate">
                                <MapPin className="h-3 w-3" />
                                {event.location}
                              </span>
                            )}
                            {event.attendees.length > 0 && (
                              <span className="flex items-center gap-1">
                                <Users className="h-3 w-3" />
                                {event.attendees.length}
                              </span>
                            )}
                          </div>
                        </div>
                        {expandedId === event.id ? (
                          <ChevronUp className="h-4 w-4 text-[color:var(--text-quiet)]" />
                        ) : (
                          <ChevronDown className="h-4 w-4 text-[color:var(--text-quiet)]" />
                        )}
                      </button>
                      {expandedId === event.id && (
                        <div className="border-t border-[color:var(--border)] px-5 py-4 bg-[color:var(--surface-muted)] rounded-b-xl space-y-3">
                          <div className="grid grid-cols-2 gap-4 text-xs">
                            <div>
                              <span className="font-medium text-[color:var(--text-muted)]">Start</span>
                              <p className="text-[color:var(--text)]">{formatDateTime(event.start)}</p>
                            </div>
                            <div>
                              <span className="font-medium text-[color:var(--text-muted)]">End</span>
                              <p className="text-[color:var(--text)]">{formatDateTime(event.end)}</p>
                            </div>
                          </div>
                          {event.location && (
                            <div className="text-xs">
                              <span className="font-medium text-[color:var(--text-muted)]">Location</span>
                              <p className="text-[color:var(--text)]">{event.location}</p>
                            </div>
                          )}
                          {event.description && (
                            <div className="text-xs">
                              <span className="font-medium text-[color:var(--text-muted)]">Description</span>
                              <p className="text-[color:var(--text)] whitespace-pre-wrap">{event.description}</p>
                            </div>
                          )}
                          {event.attendees.length > 0 && (
                            <div className="text-xs">
                              <span className="font-medium text-[color:var(--text-muted)]">Attendees</span>
                              <div className="mt-1 space-y-1">
                                {event.attendees.map((a, i) => (
                                  <p key={i} className="text-[color:var(--text)]">
                                    {a.email}
                                    {a.response && (
                                      <span className="ml-2 text-[color:var(--text-quiet)]">
                                        ({a.response})
                                      </span>
                                    )}
                                  </p>
                                ))}
                              </div>
                            </div>
                          )}
                          <div className="flex items-center gap-3 pt-2">
                            {event.html_link && (
                              <a
                                href={event.html_link}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
                              >
                                <ExternalLink className="h-3 w-3" />
                                Open in Google Calendar
                              </a>
                            )}
                            <button
                              onClick={() => handleDelete(event.id)}
                              disabled={deleting === event.id}
                              className="inline-flex items-center gap-1 text-xs text-red-500 hover:text-red-700 disabled:opacity-50"
                            >
                              <Trash2 className="h-3 w-3" />
                              {deleting === event.id ? "Deleting..." : "Delete"}
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </FeatureGate>
    </DashboardPageLayout>
  );
}
