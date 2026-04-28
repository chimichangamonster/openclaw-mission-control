"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, Clock, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { customFetch } from "@/api/mutator";
import { formatRelativeTimestamp } from "@/lib/formatters";

type CronJob = {
  id: string;
  name: string;
  agent_id: string;
  enabled: boolean;
  schedule_expr: string;
  next_run: string | null;
  last_run: string | null;
  last_status: string | null;
};

export function CronJobsWidget() {
  const { data, isLoading, isError } = useQuery<CronJob[]>({
    queryKey: ["dashboard", "cron-widget"],
    queryFn: async () => {
      const raw: any = await customFetch("/api/v1/cron-jobs", {
        method: "GET",
      });
      const jobs = raw?.data ?? raw;
      return Array.isArray(jobs) ? jobs : [];
    },
    refetchInterval: 60_000,
    refetchOnMount: "always",
    retry: 2,
  });

  if (isLoading) {
    return <Shell loading />;
  }

  if (isError) {
    return <Shell error="Unable to load cron jobs" />;
  }

  const jobs = data ?? [];
  const enabled = jobs.filter((j) => j.enabled);
  const failed = enabled.filter((j) => j.last_status === "error");

  const nextUp = [...enabled]
    .filter((j) => j.next_run)
    .sort(
      (a, b) =>
        new Date(a.next_run!).getTime() - new Date(b.next_run!).getTime(),
    )[0];

  return (
    <Shell>
      <div className="flex items-end justify-between gap-2">
        <div>
          <p className="text-2xl font-bold text-slate-900">
            {enabled.length}
          </p>
          <p className="text-xs text-slate-500">
            active job{enabled.length !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="rounded-lg bg-violet-50 p-2">
          <Clock className="h-4 w-4 text-violet-600" />
        </div>
      </div>

      <div className="mt-3 space-y-1 border-t border-slate-100 pt-2">
        {nextUp ? (
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-500">Next run</span>
            <span className="font-medium text-slate-700">
              {nextUp.name}{" "}
              <span className="text-slate-400">
                {formatRelativeTimestamp(nextUp.next_run!)}
              </span>
            </span>
          </div>
        ) : null}

        {failed.length > 0 ? (
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-500">Failed</span>
            <span className="flex items-center gap-1 font-medium text-rose-600">
              <XCircle className="h-3 w-3" />
              {failed.length} job{failed.length !== 1 ? "s" : ""}
            </span>
          </div>
        ) : enabled.length > 0 ? (
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-500">Status</span>
            <span className="flex items-center gap-1 font-medium text-emerald-600">
              <CheckCircle2 className="h-3 w-3" />
              All healthy
            </span>
          </div>
        ) : null}

        {enabled.length === 0 ? (
          <p className="text-xs text-slate-400">No cron jobs configured.</p>
        ) : null}
      </div>

      <RecentRunsFeed jobs={enabled} />
    </Shell>
  );
}

function RecentRunsFeed({ jobs }: { jobs: CronJob[] }) {
  const recent = [...jobs]
    .filter((j) => j.last_run)
    .sort(
      (a, b) =>
        new Date(b.last_run!).getTime() - new Date(a.last_run!).getTime(),
    )
    .slice(0, 5);

  if (recent.length === 0) {
    return null;
  }

  return (
    <div className="mt-3 space-y-1 border-t border-slate-100 pt-2">
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
        Recent runs
      </p>
      <ul className="space-y-1">
        {recent.map((job) => {
          const ok = job.last_status === "ok";
          const errored = job.last_status === "error";
          return (
            <li
              key={job.id}
              className="flex items-center justify-between gap-2 text-xs"
            >
              <span className="flex min-w-0 items-center gap-1.5">
                <span
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                    errored
                      ? "bg-rose-500"
                      : ok
                        ? "bg-emerald-500"
                        : "bg-slate-300"
                  }`}
                  aria-hidden
                />
                <span className="truncate text-slate-700">{job.name}</span>
              </span>
              <span className="shrink-0 text-slate-400">
                {formatRelativeTimestamp(job.last_run!)}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Shell({
  loading,
  error,
  children,
}: {
  loading?: boolean;
  error?: string;
  children?: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-3 sm:p-4 md:p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          Cron Jobs
        </h3>
        <Link
          href="/cron-jobs"
          className="inline-flex items-center gap-1 text-xs text-slate-400 transition hover:text-slate-600"
        >
          View
          <ArrowUpRight className="h-3 w-3" />
        </Link>
      </div>
      {loading ? (
        <div className="flex h-24 items-center justify-center text-xs text-slate-400">
          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          Loading...
        </div>
      ) : error ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700">
          {error}
        </div>
      ) : (
        children
      )}
    </section>
  );
}
