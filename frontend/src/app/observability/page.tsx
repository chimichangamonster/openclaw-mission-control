"use client";

export const dynamic = "force-dynamic";

/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  XCircle,
} from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { FeatureGate } from "@/components/molecules/FeatureGate";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  getObservabilityStatus,
  listTraces,
  listScores,
  type LangfuseTrace,
  type LangfuseScore,
  type ObservabilityStatus,
} from "@/lib/observability-api";

const TRACE_NAMES = [
  { label: "All", value: "" },
  { label: "Gateway RPC", value: "gateway_rpc" },
  { label: "Embedding", value: "embedding" },
  { label: "Budget Cycle", value: "budget_check_cycle" },
  { label: "Compaction", value: "session_compaction" },
  { label: "LLM Resolve", value: "llm_endpoint_resolve" },
  { label: "Data Retention", value: "data_retention_cleanup" },
];

export default function ObservabilityPage() {
  const { isSignedIn } = useAuth();

  const [langfuseStatus, setLangfuseStatus] =
    useState<ObservabilityStatus | null>(null);
  const [traces, setTraces] = useState<LangfuseTrace[]>([]);
  const [scores, setScores] = useState<LangfuseScore[]>([]);
  const [totalTraces, setTotalTraces] = useState(0);
  const [tracePage, setTracePage] = useState(1);
  const [traceFilter, setTraceFilter] = useState("");
  const [expandedTrace, setExpandedTrace] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const s = await getObservabilityStatus();
      setLangfuseStatus(s);
    } catch {
      setLangfuseStatus(null);
    }
  }, []);

  const loadTraces = useCallback(
    async (page = 1) => {
      try {
        setLoading(true);
        setError(null);
        const res = await listTraces({
          limit: 25,
          page,
          name: traceFilter || undefined,
        });
        setTraces(res.data || []);
        setTotalTraces(res.meta?.totalItems || 0);
        setTracePage(page);
      } catch (err: any) {
        setError(err?.message || "Failed to load traces");
        setTraces([]);
      } finally {
        setLoading(false);
      }
    },
    [traceFilter],
  );

  const loadScores = useCallback(async () => {
    try {
      const res = await listScores({ limit: 50 });
      setScores(res.data || []);
    } catch {
      setScores([]);
    }
  }, []);

  useEffect(() => {
    if (isSignedIn) {
      loadStatus();
      loadTraces();
      loadScores();
    }
  }, [isSignedIn, loadStatus, loadTraces, loadScores]);

  const formatTimestamp = (ts: string) => {
    const d = new Date(ts);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHrs = Math.floor(diffMin / 60);
    if (diffHrs < 24) return `${diffHrs}h ago`;
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  };

  const getTraceIcon = (name: string) => {
    if (name.includes("rpc")) return "RPC";
    if (name.includes("embedding")) return "EMB";
    if (name.includes("budget")) return "BUD";
    if (name.includes("compaction")) return "CMP";
    if (name.includes("llm")) return "LLM";
    if (name.includes("retention")) return "RET";
    return "TRC";
  };

  const getTraceColor = (trace: LangfuseTrace) => {
    const obs = trace.observations || [];
    const hasError = obs.some((o) => o.level === "ERROR");
    if (hasError) return "text-red-500";
    return "text-green-500";
  };

  // Compute summary stats from loaded traces
  const tracesByName: Record<string, number> = {};
  const errorCount = traces.filter((t) =>
    (t.observations || []).some((o) => o.level === "ERROR"),
  ).length;
  for (const t of traces) {
    tracesByName[t.name] = (tracesByName[t.name] || 0) + 1;
  }

  const totalPages = Math.ceil(totalTraces / 25);

  return (
    <FeatureGate flag="observability" label="Observability">
      <DashboardPageLayout
        signedOut={{
          message: "Sign in to view observability data.",
          forceRedirectUrl: "/observability",
          signUpForceRedirectUrl: "/observability",
        }}
        title="Observability"
        description="Agent trace explorer and quality scores powered by Langfuse."
        headerActions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              loadStatus();
              loadTraces(tracePage);
              loadScores();
            }}
            disabled={loading}
          >
            <RefreshCw
              className={cn("mr-1.5 h-3.5 w-3.5", loading && "animate-spin")}
            />
            Refresh
          </Button>
        }
      >
        {/* Status + stats row */}
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] p-3">
            <p className="text-xs text-[color:var(--text-quiet)]">Langfuse</p>
            <div className="mt-1 flex items-center gap-2">
              {langfuseStatus?.configured ? (
                <>
                  <CheckCircle2 className="h-5 w-5 text-green-500" />
                  <span className="text-sm font-medium text-green-700 dark:text-green-400">
                    Connected
                  </span>
                </>
              ) : (
                <>
                  <XCircle className="h-5 w-5 text-red-500" />
                  <span className="text-sm font-medium text-red-700 dark:text-red-400">
                    Not configured
                  </span>
                </>
              )}
            </div>
          </div>
          <div className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] p-3">
            <p className="text-xs text-[color:var(--text-quiet)]">
              Total Traces
            </p>
            <p className="mt-1 text-2xl font-semibold text-[color:var(--text)]">
              {totalTraces}
            </p>
          </div>
          <div className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] p-3">
            <p className="text-xs text-[color:var(--text-quiet)]">
              Errors (this page)
            </p>
            <p
              className={cn(
                "mt-1 text-2xl font-semibold",
                errorCount > 0 ? "text-red-500" : "text-[color:var(--text)]",
              )}
            >
              {errorCount}
            </p>
          </div>
          <div className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] p-3">
            <p className="text-xs text-[color:var(--text-quiet)]">Scores</p>
            <p className="mt-1 text-2xl font-semibold text-[color:var(--text)]">
              {scores.length}
            </p>
          </div>
        </div>

        {/* Filter bar */}
        <div className="mb-4 flex items-center gap-3">
          <select
            value={traceFilter}
            onChange={(e) => setTraceFilter(e.target.value)}
            className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] px-3 py-2 text-sm text-[color:var(--text)]"
          >
            {TRACE_NAMES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            variant="outline"
            onClick={() => loadTraces(1)}
            disabled={loading}
          >
            Filter
          </Button>
        </div>

        {/* Error banner */}
        {error && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        {/* Trace list */}
        {loading ? (
          <div className="flex items-center justify-center py-16 text-[color:var(--text-quiet)]">
            <RefreshCw className="mr-2 h-5 w-5 animate-spin" />
            Loading traces...
          </div>
        ) : traces.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-[color:var(--text-quiet)]">
            <Activity className="mb-3 h-10 w-10 opacity-30" />
            <p>No traces found</p>
            <p className="mt-1 text-xs">
              Traces appear as agents make RPC calls, embeddings, and budget
              checks.
            </p>
          </div>
        ) : (
          <div className="space-y-1">
            {traces.map((trace) => {
              const isExpanded = expandedTrace === trace.id;
              const obs = trace.observations || [];
              const traceScores = (trace.scores || []) as LangfuseScore[];
              return (
                <div
                  key={trace.id}
                  className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] transition hover:border-[color:var(--accent-soft)]"
                >
                  <button
                    onClick={() =>
                      setExpandedTrace(isExpanded ? null : trace.id)
                    }
                    className="flex w-full items-center gap-3 px-4 py-2.5 text-left"
                  >
                    {isExpanded ? (
                      <ChevronDown className="h-4 w-4 shrink-0 text-[color:var(--text-quiet)]" />
                    ) : (
                      <ChevronRight className="h-4 w-4 shrink-0 text-[color:var(--text-quiet)]" />
                    )}
                    <span
                      className={cn(
                        "w-10 shrink-0 text-center text-[10px] font-bold uppercase",
                        getTraceColor(trace),
                      )}
                    >
                      {getTraceIcon(trace.name)}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm font-medium text-[color:var(--text)]">
                      {trace.name}
                    </span>
                    <span className="shrink-0 text-xs text-[color:var(--text-quiet)]">
                      {obs.length} obs
                    </span>
                    {traceScores.length > 0 && (
                      <span className="shrink-0 text-xs text-amber-600">
                        {traceScores.length} scores
                      </span>
                    )}
                    <span className="shrink-0 text-xs text-[color:var(--text-quiet)]">
                      {formatTimestamp(trace.timestamp)}
                    </span>
                  </button>

                  {isExpanded && (
                    <div className="border-t border-[color:var(--border)] px-4 py-3">
                      <div className="mb-2 text-xs text-[color:var(--text-quiet)]">
                        ID: {trace.id}
                      </div>

                      {/* Metadata */}
                      {trace.metadata &&
                        Object.keys(trace.metadata).length > 0 && (
                          <div className="mb-3">
                            <p className="mb-1 text-xs font-semibold text-[color:var(--text-quiet)]">
                              Metadata
                            </p>
                            <div className="flex flex-wrap gap-2">
                              {Object.entries(trace.metadata).map(
                                ([k, v]) => (
                                  <span
                                    key={k}
                                    className="inline-flex items-center rounded-full bg-[color:var(--surface-muted)] px-2 py-0.5 text-xs text-[color:var(--text)]"
                                  >
                                    <span className="font-medium">{k}:</span>
                                    &nbsp;{String(v)}
                                  </span>
                                ),
                              )}
                            </div>
                          </div>
                        )}

                      {/* Observations */}
                      {obs.length > 0 && (
                        <div className="mb-3">
                          <p className="mb-1 text-xs font-semibold text-[color:var(--text-quiet)]">
                            Observations
                          </p>
                          <div className="space-y-1">
                            {obs.map((o) => (
                              <div
                                key={o.id}
                                className="flex items-center gap-2 rounded bg-[color:var(--surface-muted)] px-3 py-1.5 text-xs"
                              >
                                <span
                                  className={cn(
                                    "font-medium",
                                    o.level === "ERROR"
                                      ? "text-red-500"
                                      : "text-[color:var(--text)]",
                                  )}
                                >
                                  {o.name}
                                </span>
                                {o.model && (
                                  <span className="text-[color:var(--text-quiet)]">
                                    model: {o.model}
                                  </span>
                                )}
                                {o.metadata?.duration_ms != null && (
                                  <span className="text-[color:var(--text-quiet)]">
                                    {o.metadata.duration_ms}ms
                                  </span>
                                )}
                                {o.level === "ERROR" && (
                                  <span className="rounded bg-red-100 px-1 text-red-700 dark:bg-red-900 dark:text-red-300">
                                    ERROR
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Scores */}
                      {traceScores.length > 0 && (
                        <div>
                          <p className="mb-1 text-xs font-semibold text-[color:var(--text-quiet)]">
                            Scores
                          </p>
                          <div className="space-y-1">
                            {traceScores.map((s) => (
                              <div
                                key={s.id}
                                className="flex items-center gap-2 rounded bg-[color:var(--surface-muted)] px-3 py-1.5 text-xs"
                              >
                                <span className="font-medium text-[color:var(--text)]">
                                  {s.name}
                                </span>
                                <span className="text-amber-600">
                                  {(s.value * 100).toFixed(0)}%
                                </span>
                                {s.comment && (
                                  <span className="text-[color:var(--text-quiet)]">
                                    — {s.comment}
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="mt-4 flex items-center justify-between">
            <p className="text-sm text-[color:var(--text-quiet)]">
              {totalTraces} traces total
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => loadTraces(tracePage - 1)}
                disabled={tracePage <= 1 || loading}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-sm text-[color:var(--text-quiet)]">
                {tracePage} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => loadTraces(tracePage + 1)}
                disabled={tracePage >= totalPages || loading}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </DashboardPageLayout>
    </FeatureGate>
  );
}
