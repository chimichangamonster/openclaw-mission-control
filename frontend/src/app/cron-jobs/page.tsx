"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import { Clock, Play, Pause, Trash2, Zap, Timer, Bot } from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { FeatureGate } from "@/components/molecules/FeatureGate";
import { cn } from "@/lib/utils";
import { customFetch } from "@/api/mutator";

interface CronJob {
  id: string;
  name: string;
  description: string;
  agent_id: string;
  enabled: boolean;
  schedule_type: string;
  schedule_expr: string;
  timezone: string;
  message: string;
  thinking: string;
  timeout_seconds: number;
  session_target: string;
  announce: boolean;
  next_run: string | null;
  last_run: string | null;
  last_status: string | null;
  created_at: string;
}

const AGENT_LABELS: Record<string, { name: string; color: string }> = {
  "the-claw": { name: "The Claw", color: "bg-blue-100 text-blue-700" },
  "sports-analyst": { name: "Sports Analyst", color: "bg-emerald-100 text-emerald-700" },
  "market-scout": { name: "Market Scout", color: "bg-purple-100 text-purple-700" },
  "stock-analyst": { name: "Stock Analyst", color: "bg-amber-100 text-amber-700" },
};

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
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

export default function CronJobsPage() {
  const { isSignedIn } = useAuth();
  const [jobs, setJobs] = useState<CronJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedJob, setExpandedJob] = useState<string | null>(null);

  const loadJobs = useCallback(async () => {
    try {
      const res: any = await customFetch("/api/v1/cron-jobs", { method: "GET" });
      const data = Array.isArray(res?.data) ? res.data : Array.isArray(res) ? res : [];
      setJobs(data);
    } catch {
      setJobs([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isSignedIn) loadJobs();
  }, [isSignedIn, loadJobs]);

  return (
    <FeatureGate flag="cron_jobs" label="Scheduled Tasks">
    <DashboardPageLayout
      signedOut={{ message: "Sign in to view scheduled tasks.", forceRedirectUrl: "/cron-jobs", signUpForceRedirectUrl: "/cron-jobs" }}
      title="Scheduled Tasks"
      description="Cron jobs that run agents on autopilot."
    >
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-blue-500" />
        </div>
      ) : jobs.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-12 text-center">
          <Clock className="mx-auto h-12 w-12 text-slate-300" />
          <h3 className="mt-4 text-lg font-semibold text-slate-800">No scheduled tasks</h3>
          <p className="mt-1 text-sm text-slate-500">
            Ask an agent in Discord to &quot;schedule a daily check&quot; or create cron jobs via the CLI.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Summary bar */}
          <div className="flex gap-4 text-sm">
            <span className="flex items-center gap-1.5 text-slate-600">
              <Timer className="h-4 w-4" /> {jobs.length} total
            </span>
            <span className="flex items-center gap-1.5 text-emerald-600">
              <Zap className="h-4 w-4" /> {jobs.filter(j => j.enabled).length} active
            </span>
            <span className="flex items-center gap-1.5 text-slate-400">
              <Pause className="h-4 w-4" /> {jobs.filter(j => !j.enabled).length} paused
            </span>
          </div>

          {/* Job cards */}
          <div className="space-y-3">
            {jobs.map((job) => {
              const agent = AGENT_LABELS[job.agent_id] || { name: job.agent_id, color: "bg-slate-100 text-slate-600" };
              const isExpanded = expandedJob === job.id;

              return (
                <div key={job.id} className={cn("rounded-xl border bg-white transition", job.enabled ? "border-slate-200" : "border-slate-100 opacity-60")}>
                  <button
                    onClick={() => setExpandedJob(isExpanded ? null : job.id)}
                    className="flex w-full items-center gap-4 px-5 py-4 text-left hover:bg-slate-50/50 transition"
                  >
                    {/* Status indicator */}
                    <div className={cn("h-2.5 w-2.5 rounded-full shrink-0", job.enabled ? "bg-emerald-500" : "bg-slate-300")} />

                    {/* Name & description */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-slate-800 text-sm">{job.name}</span>
                        <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", agent.color)}>
                          <Bot className="inline h-3 w-3 mr-0.5 -mt-0.5" />{agent.name}
                        </span>
                      </div>
                      {job.description && (
                        <p className="mt-0.5 text-xs text-slate-500 truncate">{job.description}</p>
                      )}
                    </div>

                    {/* Schedule */}
                    <div className="text-right shrink-0">
                      <div className="text-xs font-mono text-slate-600">{job.schedule_expr}</div>
                      <div className="text-xs text-slate-400">{job.timezone}</div>
                    </div>

                    {/* Next run */}
                    <div className="text-right shrink-0 min-w-[100px]">
                      <div className="text-xs text-slate-600">{formatTime(job.next_run)}</div>
                      <div className="text-xs text-slate-400">{timeUntil(job.next_run)}</div>
                    </div>
                  </button>

                  {/* Expanded details */}
                  {isExpanded && (
                    <div className="border-t border-slate-100 px-5 py-4 bg-slate-50/50">
                      <div className="grid grid-cols-2 gap-x-8 gap-y-3 text-xs sm:grid-cols-4">
                        <div>
                          <span className="text-slate-400">Schedule Type</span>
                          <div className="font-medium text-slate-700">{job.schedule_type}</div>
                        </div>
                        <div>
                          <span className="text-slate-400">Session</span>
                          <div className="font-medium text-slate-700">{job.session_target || "main"}</div>
                        </div>
                        <div>
                          <span className="text-slate-400">Thinking</span>
                          <div className="font-medium text-slate-700">{job.thinking || "default"}</div>
                        </div>
                        <div>
                          <span className="text-slate-400">Timeout</span>
                          <div className="font-medium text-slate-700">{job.timeout_seconds}s</div>
                        </div>
                        <div>
                          <span className="text-slate-400">Announce</span>
                          <div className="font-medium text-slate-700">{job.announce ? "Yes" : "No"}</div>
                        </div>
                        <div>
                          <span className="text-slate-400">Last Run</span>
                          <div className="font-medium text-slate-700">{formatTime(job.last_run)}</div>
                        </div>
                        <div>
                          <span className="text-slate-400">Last Status</span>
                          <div className={cn("font-medium", job.last_status === "success" ? "text-emerald-600" : job.last_status === "error" ? "text-red-600" : "text-slate-400")}>
                            {job.last_status || "never run"}
                          </div>
                        </div>
                        <div>
                          <span className="text-slate-400">Created</span>
                          <div className="font-medium text-slate-700">{formatTime(job.created_at)}</div>
                        </div>
                      </div>

                      {job.message && (
                        <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
                          <div className="text-xs font-semibold text-slate-500 mb-1">Agent Message</div>
                          <p className="text-xs text-slate-700 whitespace-pre-wrap font-mono">{job.message.substring(0, 500)}{job.message.length > 500 ? "..." : ""}</p>
                        </div>
                      )}

                      <div className="mt-3 text-xs text-slate-400">
                        ID: {job.id}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Help text */}
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-xs text-slate-500">
            <p className="font-medium text-slate-700 mb-1">Managing cron jobs</p>
            <p>To create, enable, disable, or delete jobs, ask any agent in Discord (e.g., &quot;schedule a daily stock check at 9am&quot;) or use the gateway CLI: <code className="bg-white px-1 py-0.5 rounded text-slate-600">npx openclaw cron add --help</code></p>
          </div>
        </div>
      )}
    </DashboardPageLayout>
    </FeatureGate>
  );
}
