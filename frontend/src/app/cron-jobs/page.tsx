"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import { Clock, Play, Pause, Trash2, Zap, Timer, Bot, Plus, Pencil, RotateCw, History } from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { FeatureGate } from "@/components/molecules/FeatureGate";
import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";
import { CronJobDialog } from "@/components/cron/CronJobDialog";
import { cn } from "@/lib/utils";
import {
  listCronJobs,
  createCronJob,
  updateCronJob,
  deleteCronJob,
  runCronJob,
  getCronJobRuns,
  type CronJob,
  type CronJobCreate,
  type CronJobUpdate,
  type CronRunRecord,
} from "@/lib/cron-api";

const AGENT_LABELS: Record<string, { name: string; color: string }> = {
  "the-claw": { name: "The Claw", color: "bg-blue-100 text-blue-700" },
  "sports-analyst": { name: "Sports Analyst", color: "bg-emerald-100 text-emerald-700" },
  "market-scout": { name: "Market Scout", color: "bg-purple-100 text-purple-700" },
  "stock-analyst": { name: "Stock Analyst", color: "bg-amber-100 text-amber-700" },
  "risk-reviewer": { name: "Risk Reviewer", color: "bg-red-100 text-red-700" },
  "notification-agent": { name: "Notification Agent", color: "bg-slate-100 text-slate-700" },
};

function formatTime(iso: string | null): string {
  if (!iso) return "\u2014";
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

  // Dialog state
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogMode, setDialogMode] = useState<"create" | "edit">("create");
  const [editJob, setEditJob] = useState<CronJob | undefined>(undefined);

  // Delete confirmation
  const [deleteTarget, setDeleteTarget] = useState<CronJob | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Run history
  const [runHistoryJobId, setRunHistoryJobId] = useState<string | null>(null);
  const [runHistory, setRunHistory] = useState<CronRunRecord[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Toast-like feedback
  const [toast, setToast] = useState<string | null>(null);

  const loadJobs = useCallback(async () => {
    try {
      const data = await listCronJobs();
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

  // Auto-dismiss toast
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  const handleCreate = () => {
    setDialogMode("create");
    setEditJob(undefined);
    setDialogOpen(true);
  };

  const handleEdit = (job: CronJob) => {
    setDialogMode("edit");
    setEditJob(job);
    setDialogOpen(true);
  };

  const handleDialogSubmit = async (data: CronJobCreate | CronJobUpdate) => {
    if (dialogMode === "create") {
      await createCronJob(data as CronJobCreate);
      setToast("Task created");
    } else if (editJob) {
      await updateCronJob(editJob.id, data as CronJobUpdate);
      setToast("Task updated");
    }
    await loadJobs();
  };

  const handleToggleEnabled = async (job: CronJob) => {
    try {
      await updateCronJob(job.id, { enabled: !job.enabled });
      setToast(job.enabled ? "Task paused" : "Task enabled");
      await loadJobs();
    } catch {
      setToast("Failed to update task");
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteCronJob(deleteTarget.id);
      setDeleteTarget(null);
      setToast("Task deleted");
      await loadJobs();
    } catch (err: any) {
      setDeleteError(err?.message || "Failed to delete task");
    } finally {
      setDeleting(false);
    }
  };

  const handleRunNow = async (job: CronJob) => {
    try {
      await runCronJob(job.id);
      setToast(`Running "${job.name}"...`);
    } catch {
      setToast("Failed to trigger task");
    }
  };

  const handleToggleHistory = async (jobId: string) => {
    if (runHistoryJobId === jobId) {
      setRunHistoryJobId(null);
      return;
    }
    setRunHistoryJobId(jobId);
    setLoadingHistory(true);
    try {
      const runs = await getCronJobRuns(jobId);
      setRunHistory(runs);
    } catch {
      setRunHistory([]);
    } finally {
      setLoadingHistory(false);
    }
  };

  return (
    <FeatureGate flag="cron_jobs" label="Scheduled Tasks">
    <DashboardPageLayout
      signedOut={{ message: "Sign in to view scheduled tasks.", forceRedirectUrl: "/cron-jobs", signUpForceRedirectUrl: "/cron-jobs" }}
      title="Scheduled Tasks"
      description="Cron jobs that run agents on autopilot."
    >
      {/* Toast notification */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-700 shadow-lg animate-in fade-in slide-in-from-top-2">
          {toast}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-blue-500" />
        </div>
      ) : (
        <div className="space-y-4">
          {/* Summary bar + Create button */}
          <div className="flex items-center justify-between">
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
            <button
              onClick={handleCreate}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 transition"
            >
              <Plus className="h-4 w-4" /> Create Task
            </button>
          </div>

          {jobs.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-300 bg-white p-12 text-center">
              <Clock className="mx-auto h-12 w-12 text-slate-300" />
              <h3 className="mt-4 text-lg font-semibold text-slate-800">No scheduled tasks</h3>
              <p className="mt-1 text-sm text-slate-500">
                Create your first scheduled task to automate agent work.
              </p>
              <button
                onClick={handleCreate}
                className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition"
              >
                <Plus className="h-4 w-4" /> Create Task
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {jobs.map((job) => {
                const agent = AGENT_LABELS[job.agent_id] || { name: job.agent_id, color: "bg-slate-100 text-slate-600" };
                const isExpanded = expandedJob === job.id;
                const showingHistory = runHistoryJobId === job.id;

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
                        {/* Action buttons */}
                        <div className="flex items-center gap-2 mb-4">
                          <button
                            onClick={() => handleToggleEnabled(job)}
                            className={cn(
                              "flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition",
                              job.enabled
                                ? "border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100"
                                : "border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                            )}
                          >
                            {job.enabled ? <><Pause className="h-3.5 w-3.5" /> Pause</> : <><Play className="h-3.5 w-3.5" /> Enable</>}
                          </button>
                          <button
                            onClick={() => handleRunNow(job)}
                            className="flex items-center gap-1.5 rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-100 transition"
                          >
                            <RotateCw className="h-3.5 w-3.5" /> Run Now
                          </button>
                          <button
                            onClick={() => handleEdit(job)}
                            className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 transition"
                          >
                            <Pencil className="h-3.5 w-3.5" /> Edit
                          </button>
                          <button
                            onClick={() => handleToggleHistory(job.id)}
                            className={cn(
                              "flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition",
                              showingHistory
                                ? "border-slate-300 bg-slate-100 text-slate-700"
                                : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                            )}
                          >
                            <History className="h-3.5 w-3.5" /> History
                          </button>
                          <div className="flex-1" />
                          <button
                            onClick={() => { setDeleteError(null); setDeleteTarget(job); }}
                            className="flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-100 transition"
                          >
                            <Trash2 className="h-3.5 w-3.5" /> Delete
                          </button>
                        </div>

                        {/* Detail grid */}
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

                        {/* Run history panel */}
                        {showingHistory && (
                          <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
                            <div className="text-xs font-semibold text-slate-500 mb-2">Run History</div>
                            {loadingHistory ? (
                              <div className="flex justify-center py-4">
                                <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-200 border-t-blue-500" />
                              </div>
                            ) : runHistory.length === 0 ? (
                              <p className="text-xs text-slate-400 py-2">No run history available.</p>
                            ) : (
                              <div className="space-y-1.5">
                                {runHistory.slice(0, 20).map((run, i) => (
                                  <div key={run.run_id || i} className="flex items-center gap-3 text-xs">
                                    <div className={cn(
                                      "h-1.5 w-1.5 rounded-full shrink-0",
                                      run.status === "success" ? "bg-emerald-500" : run.status === "error" ? "bg-red-500" : "bg-amber-500"
                                    )} />
                                    <span className="text-slate-500 min-w-[120px]">{formatTime(run.started_at)}</span>
                                    <span className={cn(
                                      "font-medium",
                                      run.status === "success" ? "text-emerald-600" : run.status === "error" ? "text-red-600" : "text-amber-600"
                                    )}>
                                      {run.status}
                                    </span>
                                    {run.duration_ms != null && (
                                      <span className="text-slate-400">{(run.duration_ms / 1000).toFixed(1)}s</span>
                                    )}
                                    {run.error && (
                                      <span className="text-red-500 truncate flex-1">{run.error}</span>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
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
          )}
        </div>
      )}

      {/* Create/Edit dialog */}
      <CronJobDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        mode={dialogMode}
        job={editJob}
        onSubmit={handleDialogSubmit}
      />

      {/* Delete confirmation */}
      <ConfirmActionDialog
        open={!!deleteTarget}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
        title="Delete Scheduled Task"
        description={<>Are you sure you want to delete <strong>{deleteTarget?.name}</strong>? This action cannot be undone.</>}
        onConfirm={handleDelete}
        isConfirming={deleting}
        errorMessage={deleteError}
        confirmLabel="Delete Task"
        confirmingLabel="Deleting..."
      />
    </DashboardPageLayout>
    </FeatureGate>
  );
}
