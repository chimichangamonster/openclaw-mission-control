"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Calendar, Loader2 } from "lucide-react";
import { customFetch } from "@/api/mutator";

type CalendarEvent = {
  id: string;
  summary: string;
  start: string;
  end: string;
  location?: string;
  html_link?: string;
};

type StatusResponse = {
  connected: boolean;
  connections?: { id: string }[];
};

function formatEventTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const isToday =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const isTomorrow =
    d.getFullYear() === tomorrow.getFullYear() &&
    d.getMonth() === tomorrow.getMonth() &&
    d.getDate() === tomorrow.getDate();

  const time = d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });

  if (isToday) return `Today ${time}`;
  if (isTomorrow) return `Tomorrow ${time}`;
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  }) + ` ${time}`;
}

export function UpcomingEventsWidget() {
  const statusQuery = useQuery<StatusResponse>({
    queryKey: ["dashboard", "calendar-status"],
    queryFn: async () => {
      const raw: any = await customFetch(
        "/api/v1/google-calendar/status",
        { method: "GET" },
      );
      return raw?.data ?? raw;
    },
    refetchOnMount: "always",
    retry: 1,
    staleTime: 120_000,
  });

  const connected = statusQuery.data?.connected ?? false;

  const eventsQuery = useQuery<CalendarEvent[]>({
    queryKey: ["dashboard", "calendar-events"],
    enabled: connected,
    queryFn: async () => {
      const now = new Date().toISOString();
      const future = new Date(
        Date.now() + 7 * 24 * 60 * 60 * 1000,
      ).toISOString();
      const raw: any = await customFetch(
        `/api/v1/google-calendar/events?time_min=${encodeURIComponent(now)}&time_max=${encodeURIComponent(future)}&max_results=5`,
        { method: "GET" },
      );
      const data = raw?.data ?? raw;
      const events = data?.events ?? data;
      return Array.isArray(events) ? events : [];
    },
    refetchInterval: 120_000,
    refetchOnMount: "always",
    retry: 1,
  });

  const isLoading = statusQuery.isLoading || (connected && eventsQuery.isLoading);
  const events = eventsQuery.data ?? [];

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 md:p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          Upcoming Events
        </h3>
        <Link
          href="/calendar"
          className="inline-flex items-center gap-1 text-xs text-slate-400 transition hover:text-slate-600"
        >
          View
          <ArrowUpRight className="h-3 w-3" />
        </Link>
      </div>

      {isLoading ? (
        <div className="flex h-24 items-center justify-center text-xs text-slate-400">
          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          Loading...
        </div>
      ) : !connected ? (
        <div className="flex h-24 flex-col items-center justify-center text-center">
          <Calendar className="mb-1.5 h-5 w-5 text-slate-300" />
          <p className="text-xs text-slate-400">No calendar connected</p>
          <Link
            href="/org-settings"
            className="mt-1 text-[11px] text-blue-500 hover:text-blue-600"
          >
            Connect in settings
          </Link>
        </div>
      ) : events.length === 0 ? (
        <div className="flex h-24 flex-col items-center justify-center text-center">
          <Calendar className="mb-1.5 h-5 w-5 text-slate-300" />
          <p className="text-xs text-slate-400">No events in the next 7 days</p>
        </div>
      ) : (
        <div className="space-y-2">
          {events.slice(0, 5).map((event) => (
            <div
              key={event.id}
              className="rounded-lg border border-slate-100 px-3 py-2"
            >
              <p className="truncate text-sm font-medium text-slate-800">
                {event.summary || "Untitled"}
              </p>
              <p className="mt-0.5 text-xs text-slate-500">
                {formatEventTime(event.start)}
                {event.location ? ` · ${event.location}` : ""}
              </p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
