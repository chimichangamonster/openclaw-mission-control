"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import type { CronJob, CronJobCreate, CronJobUpdate } from "@/lib/cron-api";

const AGENT_OPTIONS = [
  { value: "the-claw", label: "The Claw" },
  { value: "sports-analyst", label: "Sports Analyst" },
  { value: "market-scout", label: "Market Scout" },
  { value: "stock-analyst", label: "Stock Analyst" },
  { value: "risk-reviewer", label: "Risk Reviewer" },
  { value: "notification-agent", label: "Notification Agent" },
];

const SCHEDULE_PRESETS = [
  { label: "Weekdays 9 AM", type: "cron" as const, expr: "0 9 * * 1-5" },
  { label: "Every 6 hours", type: "every" as const, expr: "6h" },
  { label: "Daily 8 AM", type: "cron" as const, expr: "0 8 * * *" },
  { label: "Monday 9 AM", type: "cron" as const, expr: "0 9 * * 1" },
  { label: "Every 30 min", type: "every" as const, expr: "30m" },
  { label: "Custom", type: "cron" as const, expr: "" },
];

const THINKING_OPTIONS = [
  { value: "", label: "Default" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];

interface CronJobDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: "create" | "edit";
  job?: CronJob;
  onSubmit: (data: CronJobCreate | CronJobUpdate) => Promise<void>;
}

export function CronJobDialog({ open, onOpenChange, mode, job, onSubmit }: CronJobDialogProps) {
  const [name, setName] = useState("");
  const [agentId, setAgentId] = useState("the-claw");
  const [scheduleType, setScheduleType] = useState<"cron" | "every" | "at">("cron");
  const [scheduleExpr, setScheduleExpr] = useState("");
  const [timezone, setTimezone] = useState("America/Edmonton");
  const [message, setMessage] = useState("");
  const [thinking, setThinking] = useState("");
  const [timeoutSeconds, setTimeoutSeconds] = useState(300);
  const [sessionTarget, setSessionTarget] = useState("isolated");
  const [announce, setAnnounce] = useState(false);
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pre-populate for edit mode
  useEffect(() => {
    if (mode === "edit" && job) {
      setName(job.name);
      setAgentId(job.agent_id);
      setScheduleType((job.schedule_type as "cron" | "every" | "at") || "cron");
      setScheduleExpr(job.schedule_expr);
      setTimezone(job.timezone);
      setMessage(job.message);
      setThinking(job.thinking);
      setTimeoutSeconds(job.timeout_seconds || 300);
      setSessionTarget(job.session_target || "isolated");
      setAnnounce(job.announce);
      setDescription(job.description);
    } else if (mode === "create") {
      setName("");
      setAgentId("the-claw");
      setScheduleType("cron");
      setScheduleExpr("");
      setTimezone("America/Edmonton");
      setMessage("");
      setThinking("");
      setTimeoutSeconds(300);
      setSessionTarget("isolated");
      setAnnounce(false);
      setDescription("");
    }
    setError(null);
  }, [mode, job, open]);

  const handlePreset = (preset: typeof SCHEDULE_PRESETS[number]) => {
    setScheduleType(preset.type);
    if (preset.expr) setScheduleExpr(preset.expr);
  };

  const handleSubmit = async () => {
    setError(null);
    if (!name.trim() || !scheduleExpr.trim()) {
      setError("Name and schedule expression are required.");
      return;
    }
    setSubmitting(true);
    try {
      if (mode === "create") {
        const data: CronJobCreate = {
          name: name.trim(),
          agent_id: agentId,
          schedule_type: scheduleType,
          schedule_expr: scheduleExpr.trim(),
          timezone,
          message,
          thinking: thinking || undefined,
          timeout_seconds: timeoutSeconds,
          session_target: sessionTarget,
          announce,
          description,
        };
        await onSubmit(data);
      } else {
        const data: CronJobUpdate = {
          name: name.trim(),
          agent_id: agentId,
          schedule_type: scheduleType,
          schedule_expr: scheduleExpr.trim(),
          timezone,
          message,
          thinking: thinking || undefined,
          timeout_seconds: timeoutSeconds,
          session_target: sessionTarget,
          announce,
          description,
        };
        await onSubmit(data);
      }
      onOpenChange(false);
    } catch (err: any) {
      setError(err?.message || "Failed to save cron job.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[95vw] max-w-xl sm:w-auto">
        <DialogHeader>
          <DialogTitle>{mode === "create" ? "Create Scheduled Task" : "Edit Scheduled Task"}</DialogTitle>
          <DialogDescription>
            {mode === "create"
              ? "Configure a new automated task for an agent."
              : "Update this scheduled task's configuration."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Name + Agent row */}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="morning-scan"
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Agent</label>
              <select
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
              >
                {AGENT_OPTIONS.map((a) => (
                  <option key={a.value} value={a.value}>{a.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="text-xs font-medium text-slate-600 mb-1 block">Description</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description"
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
          </div>

          {/* Schedule */}
          <div>
            <label className="text-xs font-medium text-slate-600 mb-1 block">Schedule</label>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {SCHEDULE_PRESETS.map((p) => (
                <button
                  key={p.label}
                  type="button"
                  onClick={() => handlePreset(p)}
                  className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50 hover:border-slate-300 transition"
                >
                  {p.label}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3 sm:gap-3">
              <select
                value={scheduleType}
                onChange={(e) => setScheduleType(e.target.value as "cron" | "every" | "at")}
                className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
              >
                <option value="cron">Cron</option>
                <option value="every">Interval</option>
                <option value="at">One-time</option>
              </select>
              <input
                type="text"
                value={scheduleExpr}
                onChange={(e) => setScheduleExpr(e.target.value)}
                placeholder={scheduleType === "cron" ? "0 9 * * 1-5" : scheduleType === "every" ? "6h" : "+30m"}
                className="sm:col-span-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-mono focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
            </div>
            <div className="mt-2">
              <label className="text-xs font-medium text-slate-600 mb-1 block">Timezone</label>
              <input
                type="text"
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
            </div>
          </div>

          {/* Agent message */}
          <div>
            <label className="text-xs font-medium text-slate-600 mb-1 block">Agent Message</label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Instructions for the agent when this job runs..."
              rows={3}
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-mono focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400 resize-y"
            />
          </div>

          {/* Options row */}
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3 sm:gap-3">
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Thinking</label>
              <select
                value={thinking}
                onChange={(e) => setThinking(e.target.value)}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
              >
                {THINKING_OPTIONS.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Timeout (s)</label>
              <input
                type="number"
                value={timeoutSeconds}
                onChange={(e) => setTimeoutSeconds(parseInt(e.target.value) || 300)}
                min={30}
                max={3600}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-slate-600 mb-1 block">Session</label>
              <select
                value={sessionTarget}
                onChange={(e) => setSessionTarget(e.target.value)}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
              >
                <option value="isolated">Isolated</option>
                <option value="main">Main</option>
              </select>
            </div>
          </div>

          {/* Announce toggle */}
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={announce}
              onChange={(e) => setAnnounce(e.target.checked)}
              className="rounded border-slate-300"
            />
            <span className="text-sm text-slate-600">Announce results to Discord</span>
          </label>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-600">
              {error}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting
              ? mode === "create" ? "Creating..." : "Saving..."
              : mode === "create" ? "Create Task" : "Save Changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
