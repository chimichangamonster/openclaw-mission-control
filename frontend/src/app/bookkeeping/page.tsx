"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen,
  Upload,
  ListChecks,
  BarChart3,
  Lock,
  Unlock,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Loader2,
  Save,
  X,
  Sparkles,
} from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { FeatureGate } from "@/components/molecules/FeatureGate";
import { cn } from "@/lib/utils";
import {
  BUCKETS,
  BUCKET_COLORS,
  BUCKET_LABELS,
  bulkImportStatement,
  createMonth,
  createVendorRule,
  currentPeriod,
  detectSource,
  getMonth,
  lastMonthPeriod,
  listMonths,
  listStatements,
  listTransactions,
  listVendorRules,
  lockMonth,
  periodsBack,
  promoteToRule,
  updateStatement,
  updateTransaction,
  updateVendorRule,
  uploadStatement,
  type Bucket,
  type BulkImportResult,
  type ReconciliationMonth,
  type Source,
  type StatementFile,
  type StatementImportResult,
  type Transaction,
  type VendorRule,
} from "@/lib/personal-bookkeeping-api";

type Tab = "import" | "review" | "reports";

const DEFAULT_LOCAL_PATH_ROOT =
  "C:\\Users\\Raphael\\OneDrive\\Documents\\ACCOUNTING-CB-002-Raphael";

function currencyFmt(n: number): string {
  return n.toLocaleString(undefined, {
    style: "currency",
    currency: "CAD",
    minimumFractionDigits: 2,
  });
}

function periodLabel(p: string): string {
  const [y, m] = p.split("-").map(Number);
  const d = new Date(y, m - 1, 1);
  return d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

function BucketBadge({ bucket }: { bucket: Bucket }) {
  return (
    <span
      className={cn(
        "inline-block rounded border px-2 py-0.5 text-[10px] font-medium",
        BUCKET_COLORS[bucket]
      )}
    >
      {BUCKET_LABELS[bucket]}
    </span>
  );
}

export default function BookkeepingPage() {
  return (
    <FeatureGate flag="personal_bookkeeping" label="Personal Bookkeeping">
      <DashboardPageLayout
        signedOut={{
          message: "Sign in to access bookkeeping.",
          forceRedirectUrl: "/bookkeeping",
          signUpForceRedirectUrl: "/bookkeeping",
        }}
        title="Personal Bookkeeping"
        description="Sole-prop statement reconciliation, T2125 tagging, and vendor rules."
      >
        <BookkeepingInner />
      </DashboardPageLayout>
    </FeatureGate>
  );
}

function BookkeepingInner() {
  const { isSignedIn } = useAuth();

  const [period, setPeriod] = useState<string>(() => lastMonthPeriod());
  const [tab, setTab] = useState<Tab>("review");

  const [month, setMonth] = useState<ReconciliationMonth | null>(null);
  const [allMonths, setAllMonths] = useState<ReconciliationMonth[]>([]);
  const [loadingMonth, setLoadingMonth] = useState(true);
  const [lockBusy, setLockBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  // Refresh month + all-months list
  const refreshMonth = useCallback(async () => {
    if (!isSignedIn) return;
    setLoadingMonth(true);
    try {
      const [m, all] = await Promise.all([getMonth(period), listMonths()]);
      setMonth(m);
      setAllMonths(all);
    } finally {
      setLoadingMonth(false);
    }
  }, [isSignedIn, period]);

  useEffect(() => {
    refreshMonth();
  }, [refreshMonth]);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 3500);
    return () => clearTimeout(id);
  }, [toast]);

  const handleCreateMonth = useCallback(async () => {
    try {
      await createMonth(period);
      setToast(`Created ${periodLabel(period)} — upload statements to begin.`);
      refreshMonth();
    } catch (e: unknown) {
      setToast(`Create failed: ${(e as Error).message}`);
    }
  }, [period, refreshMonth]);

  const handleLock = useCallback(async () => {
    if (!month) return;
    if (month.flagged_line_count > 0) {
      setToast(
        `Cannot lock: ${month.flagged_line_count} flagged line(s) remain. Resolve them in Review.`
      );
      return;
    }
    setLockBusy(true);
    try {
      await lockMonth(period);
      setToast(`Locked ${periodLabel(period)}.`);
      refreshMonth();
    } catch (e: unknown) {
      setToast(`Lock failed: ${(e as Error).message}`);
    } finally {
      setLockBusy(false);
    }
  }, [month, period, refreshMonth]);

  // Period dropdown options: previous 24 months + any months that exist in DB
  const periodOptions = useMemo(() => {
    const base = new Set<string>(periodsBack(currentPeriod(), 24));
    allMonths.forEach((m) => base.add(m.period));
    return Array.from(base).sort((a, b) => (a < b ? 1 : -1));
  }, [allMonths]);

  return (
    <div className="space-y-4">
      {toast ? (
        <div className="fixed bottom-6 right-6 z-40 max-w-sm rounded-lg bg-slate-900 px-4 py-3 text-sm text-white shadow-lg">
          {toast}
        </div>
      ) : null}

      {/* Header: month picker + status + actions */}
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white p-4">
        <BookOpen className="h-5 w-5 text-slate-400" />
        <label className="flex items-center gap-2 text-sm">
          <span className="text-slate-600">Month:</span>
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="rounded border border-slate-300 bg-white px-2 py-1 text-sm"
          >
            {periodOptions.map((p) => (
              <option key={p} value={p}>
                {periodLabel(p)}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-center gap-2 text-sm">
          <span className="text-slate-500">Status:</span>
          {month ? (
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs font-medium",
                month.status === "locked"
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : month.status === "reviewed"
                    ? "border-blue-200 bg-blue-50 text-blue-700"
                    : "border-slate-200 bg-slate-50 text-slate-700"
              )}
            >
              {month.status === "locked" ? <Lock className="h-3 w-3" /> : <Unlock className="h-3 w-3" />}
              {month.status}
            </span>
          ) : loadingMonth ? (
            <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
          ) : (
            <span className="text-xs text-slate-400">Not created</span>
          )}
        </div>

        {month && month.flagged_line_count > 0 ? (
          <span className="inline-flex items-center gap-1 rounded border border-red-200 bg-red-50 px-2 py-0.5 text-xs text-red-700">
            <AlertTriangle className="h-3 w-3" />
            {month.flagged_line_count} flagged
          </span>
        ) : null}

        <div className="ml-auto flex items-center gap-2">
          {!month && !loadingMonth ? (
            <button
              type="button"
              onClick={handleCreateMonth}
              className="rounded bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800"
            >
              Create month
            </button>
          ) : null}
          {month && month.status !== "locked" ? (
            <button
              type="button"
              onClick={handleLock}
              disabled={lockBusy || month.flagged_line_count > 0}
              className="inline-flex items-center gap-1 rounded bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
              title={
                month.flagged_line_count > 0
                  ? "Resolve flagged lines before locking"
                  : "Lock this month — no more edits"
              }
            >
              <Lock className="h-3 w-3" />
              Lock month
            </button>
          ) : null}
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-slate-200">
        <TabButton active={tab === "import"} onClick={() => setTab("import")} icon={Upload}>
          Import
        </TabButton>
        <TabButton active={tab === "review"} onClick={() => setTab("review")} icon={ListChecks}>
          Review
        </TabButton>
        <TabButton active={tab === "reports"} onClick={() => setTab("reports")} icon={BarChart3}>
          Reports
        </TabButton>
      </div>

      {/* Tab content */}
      {tab === "import" ? (
        <ImportTab
          period={period}
          month={month}
          onChanged={() => refreshMonth()}
          setToast={setToast}
        />
      ) : tab === "review" ? (
        <ReviewTab
          period={period}
          month={month}
          onChanged={() => refreshMonth()}
          setToast={setToast}
        />
      ) : (
        <ReportsTab
          month={month}
          allMonths={allMonths}
          onPickMonth={(p) => {
            setPeriod(p);
            setTab("review");
          }}
          setToast={setToast}
        />
      )}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon: Icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium",
        active
          ? "border-slate-900 text-slate-900"
          : "border-transparent text-slate-500 hover:text-slate-700"
      )}
    >
      <Icon className="h-4 w-4" />
      {children}
    </button>
  );
}

// ===========================================================================
// IMPORT TAB
// ===========================================================================

function ImportTab({
  period,
  month,
  onChanged,
  setToast,
}: {
  period: string;
  month: ReconciliationMonth | null;
  onChanged: () => void;
  setToast: (s: string) => void;
}) {
  const [statements, setStatements] = useState<StatementFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [lastResult, setLastResult] = useState<StatementImportResult | null>(null);
  const [lastBulkResult, setLastBulkResult] = useState<BulkImportResult | null>(null);
  const [sourceOverride, setSourceOverride] = useState<Source | "auto">("auto");
  const [bulkMode, setBulkMode] = useState(false);
  const [editingPathId, setEditingPathId] = useState<string | null>(null);
  const [editPathValue, setEditPathValue] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const list = await listStatements(period);
      setStatements(list);
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return;
      setUploading(true);
      setLastResult(null);
      setLastBulkResult(null);
      try {
        for (const file of Array.from(files)) {
          let source: Source | null =
            sourceOverride !== "auto" ? (sourceOverride as Source) : null;
          if (!source) {
            source = detectSource(file);
          }
          if (!source) {
            setToast(
              `${file.name}: filename not recognised (expected accountactivity* or Summary*). Pick source manually.`
            );
            continue;
          }
          try {
            if (bulkMode) {
              const result = await bulkImportStatement(source, file);
              setLastBulkResult(result);
              const periods = result.per_period.length;
              setToast(
                `${file.name}: ${result.total_inserted} inserted across ${periods} month${periods === 1 ? "" : "s"}, ${result.total_skipped} skipped.`
              );
            } else {
              const result = await uploadStatement(period, source, file);
              setLastResult(result);
              setToast(
                `${file.name}: ${result.inserted_count} inserted, ${result.skipped_count} skipped.`
              );
            }
          } catch (e: unknown) {
            setToast(`${file.name}: ${(e as Error).message}`);
          }
        }
        refresh();
        onChanged();
      } finally {
        setUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    },
    [period, sourceOverride, bulkMode, setToast, refresh, onChanged]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  const savePath = useCallback(
    async (stmtId: string) => {
      try {
        await updateStatement(stmtId, { local_path: editPathValue || null });
        setEditingPathId(null);
        refresh();
        setToast("Local path updated.");
      } catch (e: unknown) {
        setToast(`Update failed: ${(e as Error).message}`);
      }
    },
    [editPathValue, refresh, setToast]
  );

  const isLocked = month?.status === "locked";

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-slate-700">
            {bulkMode
              ? "Bulk import (multi-month)"
              : `Upload statements for ${periodLabel(period)}`}
          </h2>
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600">
            <label
              className="inline-flex items-center gap-1.5"
              title="Split one file across the months its rows belong to. Use when you forgot to reconcile monthly; the default single-month flow is the habit."
            >
              <input
                type="checkbox"
                checked={bulkMode}
                onChange={(e) => setBulkMode(e.target.checked)}
                className="rounded border-slate-300"
              />
              Catch-up (multi-month)
            </label>
            <label className="flex items-center gap-2">
              Source:
              <select
                value={sourceOverride}
                onChange={(e) => setSourceOverride(e.target.value as Source | "auto")}
                className="rounded border border-slate-300 px-2 py-1"
              >
                <option value="auto">Auto-detect</option>
                <option value="TD">TD CSV</option>
                <option value="AMEX">AMEX XLS</option>
              </select>
            </label>
          </div>
        </div>

        {bulkMode ? (
          <p className="mb-3 rounded border border-blue-200 bg-blue-50 p-2 text-[11px] text-blue-800">
            Rows will be grouped by date and imported into their matching months.
            Missing months are auto-created as drafts. Rows for a locked month are skipped.
            Monthly is still the habit — this is for when you forgot.
          </p>
        ) : null}

        {isLocked && !bulkMode ? (
          <p className="rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
            {periodLabel(period)} is locked. Uploads blocked for this month — switch
            month or use catch-up mode to import into other months.
          </p>
        ) : (
          <div
            onDrop={onDrop}
            onDragOver={(e) => e.preventDefault()}
            onClick={() => fileInputRef.current?.click()}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-2 rounded border-2 border-dashed border-slate-300 bg-slate-50 py-10 text-sm text-slate-500 transition",
              uploading ? "pointer-events-none opacity-60" : "hover:border-slate-400 hover:bg-slate-100"
            )}
          >
            {uploading ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                <span>Uploading…</span>
              </>
            ) : (
              <>
                <Upload className="h-5 w-5" />
                <span>Drop TD CSV or AMEX XLS here, or click to browse</span>
                <span className="text-xs text-slate-400">
                  Auto-detects source by file magic bytes + date format
                </span>
              </>
            )}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".csv,.xls,application/vnd.ms-excel,text/csv"
              className="hidden"
              onChange={(e) => handleFiles(e.target.files)}
            />
          </div>
        )}

        {lastResult ? (
          <div className="mt-3 rounded border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">
            <div className="font-medium">Last import:</div>
            <div>
              {lastResult.inserted_count} inserted, {lastResult.skipped_count} skipped (dup row-hashes).
            </div>
            {Object.keys(lastResult.classification_summary).length > 0 ? (
              <div className="mt-1 flex flex-wrap gap-1.5">
                {Object.entries(lastResult.classification_summary).map(([bucket, count]) => (
                  <span key={bucket} className="inline-flex items-center gap-1">
                    <BucketBadge bucket={bucket as Bucket} />
                    <span className="text-slate-700">{count}</span>
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        {lastBulkResult ? (
          <div className="mt-3 rounded border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">
            <div className="font-medium">
              Bulk import: {lastBulkResult.total_inserted} inserted across{" "}
              {lastBulkResult.per_period.length} month
              {lastBulkResult.per_period.length === 1 ? "" : "s"},{" "}
              {lastBulkResult.total_skipped} skipped.
            </div>
            <table className="mt-2 w-full text-[11px]">
              <thead className="text-left text-emerald-700">
                <tr>
                  <th className="py-1 pr-2 font-medium">Period</th>
                  <th className="py-1 pr-2 text-right font-medium">Inserted</th>
                  <th className="py-1 pr-2 text-right font-medium">Skipped</th>
                  <th className="py-1 font-medium">Buckets</th>
                </tr>
              </thead>
              <tbody>
                {lastBulkResult.per_period.map((p) => (
                  <tr
                    key={p.period}
                    className={cn(p.month_locked_and_skipped && "text-amber-700")}
                  >
                    <td className="py-0.5 pr-2 font-mono">
                      {p.period}
                      {p.month_locked_and_skipped ? (
                        <span className="ml-1 rounded bg-amber-100 px-1 text-[9px] text-amber-800">
                          locked
                        </span>
                      ) : null}
                    </td>
                    <td className="py-0.5 pr-2 text-right font-mono">{p.inserted_count}</td>
                    <td className="py-0.5 pr-2 text-right font-mono">{p.skipped_count}</td>
                    <td className="py-0.5">
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(p.classification_summary).map(([b, n]) => (
                          <span key={b} className="inline-flex items-center gap-0.5">
                            <BucketBadge bucket={b as Bucket} />
                            <span className="text-slate-700">{n}</span>
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-4 py-2 text-xs font-semibold text-slate-600">
          Uploaded statements ({statements.length})
        </div>
        {loading ? (
          <div className="flex items-center justify-center py-6 text-sm text-slate-400">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Loading…
          </div>
        ) : statements.length === 0 ? (
          <div className="px-4 py-6 text-center text-sm text-slate-400">
            No statements uploaded for this month yet.
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead className="bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-3 py-2 font-medium">Source</th>
                <th className="px-3 py-2 font-medium">Filename</th>
                <th className="px-3 py-2 font-medium">Size</th>
                <th className="px-3 py-2 font-medium">Uploaded</th>
                <th className="px-3 py-2 font-medium">Keep until</th>
                <th className="px-3 py-2 font-medium">Local mirror</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {statements.map((s) => (
                <tr key={s.id}>
                  <td className="px-3 py-2">
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px]">
                      {s.source}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono text-[11px] text-slate-700" title={s.sha256}>
                    {s.original_filename}
                  </td>
                  <td className="px-3 py-2 text-slate-500">{(s.byte_size / 1024).toFixed(1)} KB</td>
                  <td className="px-3 py-2 text-slate-500">
                    {new Date(s.uploaded_at).toLocaleDateString()}
                  </td>
                  <td className="px-3 py-2 text-slate-500">{s.retention_until}</td>
                  <td className="px-3 py-2">
                    {editingPathId === s.id ? (
                      <div className="flex items-center gap-1">
                        <input
                          type="text"
                          value={editPathValue}
                          onChange={(e) => setEditPathValue(e.target.value)}
                          className="flex-1 rounded border border-slate-300 px-2 py-1 font-mono text-[10px]"
                          placeholder={`${DEFAULT_LOCAL_PATH_ROOT}\\${period.split("-")[0]}\\statements\\…`}
                        />
                        <button
                          type="button"
                          onClick={() => savePath(s.id)}
                          className="rounded bg-slate-900 p-1 text-white hover:bg-slate-800"
                          title="Save"
                        >
                          <Save className="h-3 w-3" />
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingPathId(null)}
                          className="rounded border border-slate-300 p-1 text-slate-600 hover:bg-slate-100"
                          title="Cancel"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setEditingPathId(s.id);
                          setEditPathValue(
                            s.local_path ||
                              `${DEFAULT_LOCAL_PATH_ROOT}\\${period.split("-")[0]}\\statements\\${s.original_filename}`
                          );
                        }}
                        className="text-left font-mono text-[10px] text-slate-500 hover:text-slate-900"
                        title="Click to edit"
                      >
                        {s.local_path || <span className="italic text-slate-400">Not set — click to add</span>}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ===========================================================================
// REVIEW TAB
// ===========================================================================

function ReviewTab({
  period,
  month,
  onChanged,
  setToast,
}: {
  period: string;
  month: ReconciliationMonth | null;
  onChanged: () => void;
  setToast: (s: string) => void;
}) {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [bucketFilter, setBucketFilter] = useState<Bucket | "all">("all");
  const [sourceFilter, setSourceFilter] = useState<Source | "all">("all");
  const [flaggedOnly, setFlaggedOnly] = useState(() =>
    (month?.flagged_line_count ?? 0) > 0
  );
  const [editId, setEditId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<Partial<Transaction>>({});
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    if (!month) {
      setTransactions([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const list = await listTransactions(period);
      setTransactions(list);
    } finally {
      setLoading(false);
    }
  }, [month, period]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Sync flaggedOnly to month's flagged count when it changes across loads
  useEffect(() => {
    if (month) {
      setFlaggedOnly((prev) => (prev && month.flagged_line_count === 0 ? false : prev));
    }
  }, [month]);

  const filtered = useMemo(() => {
    return transactions.filter((t) => {
      if (bucketFilter !== "all" && t.bucket !== bucketFilter) return false;
      if (sourceFilter !== "all" && t.source !== sourceFilter) return false;
      if (flaggedOnly && t.bucket !== "ambiguous" && t.bucket !== "income_pending") return false;
      return true;
    });
  }, [transactions, bucketFilter, sourceFilter, flaggedOnly]);

  const startEdit = useCallback((t: Transaction) => {
    setEditId(t.id);
    setEditDraft({
      bucket: t.bucket,
      t2125_line: t.t2125_line,
      category: t.category,
      needs_receipt: t.needs_receipt,
      receipt_filed: t.receipt_filed,
      user_note: t.user_note,
    });
  }, []);

  const cancelEdit = useCallback(() => {
    setEditId(null);
    setEditDraft({});
  }, []);

  const save = useCallback(
    async (promote: boolean) => {
      if (!editId) return;
      setSaving(true);
      try {
        await updateTransaction(editId, {
          bucket: editDraft.bucket as Bucket | undefined,
          t2125_line: editDraft.t2125_line ?? null,
          category: editDraft.category ?? null,
          needs_receipt: editDraft.needs_receipt,
          receipt_filed: editDraft.receipt_filed,
          user_note: editDraft.user_note ?? null,
        });
        if (promote) {
          await promoteToRule(editId);
          setToast("Saved + rule created.");
        } else {
          setToast("Saved.");
        }
        setEditId(null);
        setEditDraft({});
        refresh();
        onChanged();
      } catch (e: unknown) {
        setToast(`Save failed: ${(e as Error).message}`);
      } finally {
        setSaving(false);
      }
    },
    [editId, editDraft, refresh, onChanged, setToast]
  );

  const isLocked = month?.status === "locked";

  if (!month) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
        Create the {periodLabel(period)} month first (header button), then upload statements on the Import tab.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {isLocked ? (
        <div className="rounded border border-emerald-200 bg-emerald-50 p-2.5 text-xs text-emerald-800">
          <Lock className="mr-1 inline h-3 w-3" />
          Locked on {month.locked_at ? new Date(month.locked_at).toLocaleDateString() : "—"}. Transactions read-only.
        </div>
      ) : null}

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white p-3 text-xs">
        <label className="flex items-center gap-1">
          <span className="text-slate-500">Bucket:</span>
          <select
            value={bucketFilter}
            onChange={(e) => setBucketFilter(e.target.value as Bucket | "all")}
            className="rounded border border-slate-300 px-2 py-1"
          >
            <option value="all">All</option>
            {BUCKETS.map((b) => (
              <option key={b} value={b}>
                {BUCKET_LABELS[b]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1">
          <span className="text-slate-500">Source:</span>
          <select
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value as Source | "all")}
            className="rounded border border-slate-300 px-2 py-1"
          >
            <option value="all">All</option>
            <option value="TD">TD</option>
            <option value="AMEX">AMEX</option>
          </select>
        </label>
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={flaggedOnly}
            onChange={(e) => setFlaggedOnly(e.target.checked)}
            className="rounded border-slate-300"
          />
          <span className="text-slate-700">Flagged only (ambiguous + income_pending)</span>
        </label>
        <div className="ml-auto text-slate-500">
          {filtered.length} / {transactions.length} rows
        </div>
      </div>

      {/* Transaction table */}
      <div className="rounded-lg border border-slate-200 bg-white">
        {loading ? (
          <div className="flex items-center justify-center py-6 text-sm text-slate-400">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Loading…
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-4 py-6 text-center text-sm text-slate-400">
            {transactions.length === 0
              ? "No transactions — upload a statement on the Import tab."
              : "No rows match filters."}
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead className="bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-2 py-2 font-medium">Date</th>
                <th className="px-2 py-2 font-medium">Src</th>
                <th className="px-2 py-2 font-medium">Description</th>
                <th className="px-2 py-2 text-right font-medium">Amount</th>
                <th className="px-2 py-2 font-medium">Bucket</th>
                <th className="px-2 py-2 font-medium">T2125</th>
                <th className="px-2 py-2 font-medium">Category</th>
                <th className="px-2 py-2 font-medium">Receipt</th>
                <th className="px-2 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((t) =>
                editId === t.id ? (
                  <EditRow
                    key={t.id}
                    txn={t}
                    draft={editDraft}
                    setDraft={setEditDraft}
                    onCancel={cancelEdit}
                    onSave={() => save(false)}
                    onSavePromote={() => save(true)}
                    saving={saving}
                  />
                ) : (
                  <tr
                    key={t.id}
                    onClick={() => (isLocked ? null : startEdit(t))}
                    className={cn(
                      "hover:bg-slate-50",
                      !isLocked && "cursor-pointer",
                      t.bucket === "ambiguous" || t.bucket === "income_pending"
                        ? "bg-red-50/40"
                        : undefined
                    )}
                  >
                    <td className="px-2 py-1.5 whitespace-nowrap text-slate-600">{t.txn_date}</td>
                    <td className="px-2 py-1.5">
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px]">
                        {t.source}
                      </span>
                    </td>
                    <td className="px-2 py-1.5 text-slate-800">{t.description}</td>
                    <td
                      className={cn(
                        "px-2 py-1.5 text-right font-mono",
                        t.incoming ? "text-emerald-600" : "text-slate-700"
                      )}
                    >
                      {t.incoming ? "+" : ""}
                      {currencyFmt(Math.abs(t.amount))}
                    </td>
                    <td className="px-2 py-1.5">
                      <BucketBadge bucket={t.bucket} />
                    </td>
                    <td className="px-2 py-1.5 font-mono text-slate-600">{t.t2125_line || "—"}</td>
                    <td className="px-2 py-1.5 text-slate-600">{t.category || "—"}</td>
                    <td className="px-2 py-1.5">
                      {t.receipt_filed ? (
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                      ) : t.needs_receipt ? (
                        <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                    <td className="px-2 py-1.5 text-right text-slate-400">
                      {t.classified_by === "user" ? (
                        <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[9px] font-medium text-blue-700">
                          user
                        </span>
                      ) : (
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[9px] text-slate-500">
                          auto
                        </span>
                      )}
                    </td>
                  </tr>
                )
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function EditRow({
  txn,
  draft,
  setDraft,
  onCancel,
  onSave,
  onSavePromote,
  saving,
}: {
  txn: Transaction;
  draft: Partial<Transaction>;
  setDraft: (d: Partial<Transaction>) => void;
  onCancel: () => void;
  onSave: () => void;
  onSavePromote: () => void;
  saving: boolean;
}) {
  return (
    <tr className="bg-blue-50/50">
      <td colSpan={9} className="px-3 py-3">
        <div className="mb-2 flex items-center gap-2 text-xs text-slate-600">
          <FileText className="h-3.5 w-3.5 text-slate-400" />
          <span className="font-mono">{txn.txn_date}</span>
          <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px]">{txn.source}</span>
          <span className="font-medium text-slate-800">{txn.description}</span>
          <span
            className={cn(
              "ml-auto font-mono",
              txn.incoming ? "text-emerald-600" : "text-slate-700"
            )}
          >
            {txn.incoming ? "+" : ""}
            {currencyFmt(Math.abs(txn.amount))}
          </span>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <label className="flex flex-col gap-1 text-[11px] text-slate-600">
            Bucket
            <select
              value={(draft.bucket as Bucket) || txn.bucket}
              onChange={(e) => setDraft({ ...draft, bucket: e.target.value as Bucket })}
              className="rounded border border-slate-300 px-2 py-1"
            >
              {BUCKETS.map((b) => (
                <option key={b} value={b}>
                  {BUCKET_LABELS[b]}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-[11px] text-slate-600">
            T2125 line <span className="text-slate-400">(e.g. 8810, 8871, 9200)</span>
            <input
              type="text"
              value={draft.t2125_line ?? ""}
              onChange={(e) => setDraft({ ...draft, t2125_line: e.target.value })}
              className="rounded border border-slate-300 px-2 py-1 font-mono"
            />
          </label>
          <label className="flex flex-col gap-1 text-[11px] text-slate-600">
            Category
            <input
              type="text"
              value={draft.category ?? ""}
              onChange={(e) => setDraft({ ...draft, category: e.target.value })}
              className="rounded border border-slate-300 px-2 py-1"
            />
          </label>
          <div className="flex flex-col gap-1 text-[11px] text-slate-600">
            Receipt
            <div className="flex items-center gap-3 py-1">
              <label className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={draft.needs_receipt ?? txn.needs_receipt}
                  onChange={(e) => setDraft({ ...draft, needs_receipt: e.target.checked })}
                  className="rounded border-slate-300"
                />
                Needs
              </label>
              <label className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={draft.receipt_filed ?? txn.receipt_filed}
                  onChange={(e) => setDraft({ ...draft, receipt_filed: e.target.checked })}
                  className="rounded border-slate-300"
                />
                Filed
              </label>
            </div>
          </div>
        </div>
        <label className="mt-2 flex flex-col gap-1 text-[11px] text-slate-600">
          Note
          <textarea
            rows={2}
            value={draft.user_note ?? ""}
            onChange={(e) => setDraft({ ...draft, user_note: e.target.value })}
            className="rounded border border-slate-300 px-2 py-1"
          />
        </label>
        <div className="mt-2 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-slate-300 px-3 py-1 text-xs text-slate-600 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onSavePromote}
            disabled={saving}
            className="inline-flex items-center gap-1 rounded border border-blue-300 bg-blue-50 px-3 py-1 text-xs text-blue-700 hover:bg-blue-100 disabled:opacity-50"
            title="Save + create vendor rule from this description"
          >
            <Sparkles className="h-3 w-3" />
            Save & promote to rule
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            className="inline-flex items-center gap-1 rounded bg-slate-900 px-3 py-1 text-xs text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />}
            Save
          </button>
        </div>
      </td>
    </tr>
  );
}

// ===========================================================================
// REPORTS TAB
// ===========================================================================

type PeriodGrouping = "month" | "quarter";

interface QuarterBucket {
  key: string; // "2026-Q1"
  year: number;
  q: 1 | 2 | 3 | 4;
  label: string; // "Q1 2026"
  months: ReconciliationMonth[];
  business_income: number;
  business_expenses: number;
  vehicle_expenses: number;
  gst_collected: number;
  gst_paid: number;
  flagged: number;
  all_locked: boolean;
}

function groupByQuarter(months: ReconciliationMonth[]): QuarterBucket[] {
  const byKey = new Map<string, QuarterBucket>();
  for (const m of months) {
    const [yStr, monStr] = m.period.split("-");
    const year = Number(yStr);
    const monNum = Number(monStr);
    const q = (Math.ceil(monNum / 3) as 1 | 2 | 3 | 4);
    const key = `${year}-Q${q}`;
    let bucket = byKey.get(key);
    if (!bucket) {
      bucket = {
        key,
        year,
        q,
        label: `Q${q} ${year}`,
        months: [],
        business_income: 0,
        business_expenses: 0,
        vehicle_expenses: 0,
        gst_collected: 0,
        gst_paid: 0,
        flagged: 0,
        all_locked: true,
      };
      byKey.set(key, bucket);
    }
    bucket.months.push(m);
    bucket.business_income += m.business_income;
    bucket.business_expenses += m.business_expenses;
    bucket.vehicle_expenses += m.vehicle_expenses;
    bucket.gst_collected += m.gst_collected_informational;
    bucket.gst_paid += m.gst_paid_informational;
    bucket.flagged += m.flagged_line_count;
    if (m.status !== "locked") bucket.all_locked = false;
  }
  // Sort months within each quarter ascending, quarters themselves newest-first
  for (const bucket of byKey.values()) {
    bucket.months.sort((a, b) => (a.period < b.period ? -1 : 1));
  }
  return Array.from(byKey.values()).sort((a, b) =>
    b.year !== a.year ? b.year - a.year : b.q - a.q
  );
}

function ReportsTab({
  month,
  allMonths,
  onPickMonth,
  setToast,
}: {
  month: ReconciliationMonth | null;
  allMonths: ReconciliationMonth[];
  onPickMonth: (period: string) => void;
  setToast: (s: string) => void;
}) {
  const [rules, setRules] = useState<VendorRule[]>([]);
  const [loadingRules, setLoadingRules] = useState(true);
  const [showInactive, setShowInactive] = useState(false);
  const [grouping, setGrouping] = useState<PeriodGrouping>("month");
  const [expandedQuarter, setExpandedQuarter] = useState<string | null>(null);

  const refreshRules = useCallback(async () => {
    setLoadingRules(true);
    try {
      const list = await listVendorRules(
        showInactive ? undefined : { active: true }
      );
      setRules(list);
    } finally {
      setLoadingRules(false);
    }
  }, [showInactive]);

  useEffect(() => {
    refreshRules();
  }, [refreshRules]);

  const toggleRule = useCallback(
    async (r: VendorRule) => {
      try {
        await updateVendorRule(r.id, { active: !r.active });
        refreshRules();
      } catch (e: unknown) {
        setToast(`Update failed: ${(e as Error).message}`);
      }
    },
    [refreshRules, setToast]
  );

  const sortedMonths = useMemo(
    () => [...allMonths].sort((a, b) => (a.period < b.period ? 1 : -1)),
    [allMonths]
  );

  // Current-year YTD aggregates from locked months
  const ytd = useMemo(() => {
    const currentYear = new Date().getFullYear();
    const locked = sortedMonths.filter(
      (m) => m.status === "locked" && m.period.startsWith(String(currentYear))
    );
    return locked.reduce(
      (acc, m) => ({
        business_income: acc.business_income + m.business_income,
        business_expenses: acc.business_expenses + m.business_expenses,
        vehicle_expenses: acc.vehicle_expenses + m.vehicle_expenses,
        gst_collected: acc.gst_collected + m.gst_collected_informational,
        gst_paid: acc.gst_paid + m.gst_paid_informational,
        count: acc.count + 1,
      }),
      {
        business_income: 0,
        business_expenses: 0,
        vehicle_expenses: 0,
        gst_collected: 0,
        gst_paid: 0,
        count: 0,
      }
    );
  }, [sortedMonths]);

  return (
    <div className="space-y-4">
      {/* Current month summary */}
      {month ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <SummaryCard
            label="Business income"
            value={currencyFmt(month.business_income)}
            subtle={`GST (info): ${currencyFmt(month.gst_collected_informational)}`}
          />
          <SummaryCard
            label="Business expenses"
            value={currencyFmt(month.business_expenses)}
            subtle={`GST (info): ${currencyFmt(month.gst_paid_informational)}`}
          />
          <SummaryCard
            label="Vehicle expenses"
            value={currencyFmt(month.vehicle_expenses)}
            subtle="Apply business-km %"
          />
          <SummaryCard
            label="Lines"
            value={`${month.td_line_count + month.amex_line_count}`}
            subtle={`TD ${month.td_line_count} · AMEX ${month.amex_line_count}`}
          />
        </div>
      ) : null}

      {/* YTD / grouping table */}
      <div className="rounded-lg border border-slate-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-2">
          <div className="flex items-center gap-3">
            <div className="text-xs font-semibold text-slate-600">
              {grouping === "month"
                ? `Locked months${ytd.count > 0 ? ` — ${new Date().getFullYear()} YTD (${ytd.count})` : ""}`
                : "By quarter"}
            </div>
            <div className="inline-flex rounded border border-slate-200 p-0.5 text-[10px]">
              <button
                type="button"
                onClick={() => setGrouping("month")}
                className={cn(
                  "rounded px-2 py-0.5",
                  grouping === "month"
                    ? "bg-slate-900 text-white"
                    : "text-slate-500 hover:text-slate-700"
                )}
              >
                Months
              </button>
              <button
                type="button"
                onClick={() => setGrouping("quarter")}
                className={cn(
                  "rounded px-2 py-0.5",
                  grouping === "quarter"
                    ? "bg-slate-900 text-white"
                    : "text-slate-500 hover:text-slate-700"
                )}
              >
                Quarters
              </button>
            </div>
          </div>
          {ytd.count > 0 ? (
            <div className="text-xs text-slate-500">
              Income: <span className="font-semibold text-emerald-700">{currencyFmt(ytd.business_income)}</span>
              {" · "}
              Expenses: <span className="font-semibold text-slate-700">{currencyFmt(ytd.business_expenses)}</span>
              {" · "}
              Vehicle: <span className="font-semibold text-amber-700">{currencyFmt(ytd.vehicle_expenses)}</span>
            </div>
          ) : null}
        </div>
        {sortedMonths.length === 0 ? (
          <div className="px-4 py-6 text-center text-sm text-slate-400">No months yet.</div>
        ) : grouping === "month" ? (
          <table className="w-full text-xs">
            <thead className="bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-3 py-2 font-medium">Period</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 text-right font-medium">Business income</th>
                <th className="px-3 py-2 text-right font-medium">Business exp.</th>
                <th className="px-3 py-2 text-right font-medium">Vehicle exp.</th>
                <th className="px-3 py-2 text-right font-medium">Flagged</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {sortedMonths.map((m) => (
                <tr key={m.id} className="hover:bg-slate-50">
                  <td className="px-3 py-1.5 font-medium">{periodLabel(m.period)}</td>
                  <td className="px-3 py-1.5">
                    <span
                      className={cn(
                        "rounded border px-2 py-0.5 text-[10px]",
                        m.status === "locked"
                          ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                          : "border-slate-200 bg-slate-50 text-slate-600"
                      )}
                    >
                      {m.status}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono text-emerald-700">
                    {currencyFmt(m.business_income)}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono text-slate-700">
                    {currencyFmt(m.business_expenses)}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono text-amber-700">
                    {currencyFmt(m.vehicle_expenses)}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    {m.flagged_line_count > 0 ? (
                      <span className="text-red-600">{m.flagged_line_count}</span>
                    ) : (
                      <span className="text-slate-300">0</span>
                    )}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    <button
                      type="button"
                      onClick={() => onPickMonth(m.period)}
                      className="text-blue-600 hover:underline"
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="w-full text-xs">
            <thead className="bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-3 py-2 font-medium">Quarter</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 text-right font-medium">Business income</th>
                <th className="px-3 py-2 text-right font-medium">Business exp.</th>
                <th className="px-3 py-2 text-right font-medium">Vehicle exp.</th>
                <th className="px-3 py-2 text-right font-medium">Flagged</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {groupByQuarter(sortedMonths).flatMap((q) => {
                const isExpanded = expandedQuarter === q.key;
                const quarterRow = (
                  <tr
                    key={q.key}
                    onClick={() => setExpandedQuarter(isExpanded ? null : q.key)}
                    className="cursor-pointer bg-slate-50/50 hover:bg-slate-100/60"
                  >
                    <td className="px-3 py-1.5 font-semibold text-slate-700">
                      <span className="mr-1 inline-block w-3 text-slate-400">
                        {isExpanded ? "▾" : "▸"}
                      </span>
                      {q.label}
                      <span className="ml-2 text-[10px] font-normal text-slate-400">
                        ({q.months.length} mo)
                      </span>
                    </td>
                    <td className="px-3 py-1.5">
                      <span
                        className={cn(
                          "rounded border px-2 py-0.5 text-[10px]",
                          q.all_locked
                            ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                            : "border-slate-200 bg-slate-50 text-slate-600"
                        )}
                      >
                        {q.all_locked ? "locked" : "partial"}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono font-semibold text-emerald-700">
                      {currencyFmt(q.business_income)}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono font-semibold text-slate-700">
                      {currencyFmt(q.business_expenses)}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono font-semibold text-amber-700">
                      {currencyFmt(q.vehicle_expenses)}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      {q.flagged > 0 ? (
                        <span className="text-red-600">{q.flagged}</span>
                      ) : (
                        <span className="text-slate-300">0</span>
                      )}
                    </td>
                    <td className="px-3 py-1.5 text-right text-slate-400" />
                  </tr>
                );
                if (!isExpanded) return [quarterRow];
                const monthRows = q.months.map((m) => (
                  <tr key={m.id} className="hover:bg-slate-50">
                    <td className="px-3 py-1.5 pl-10 text-slate-600">{periodLabel(m.period)}</td>
                    <td className="px-3 py-1.5">
                      <span
                        className={cn(
                          "rounded border px-2 py-0.5 text-[10px]",
                          m.status === "locked"
                            ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                            : "border-slate-200 bg-slate-50 text-slate-600"
                        )}
                      >
                        {m.status}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono text-emerald-700">
                      {currencyFmt(m.business_income)}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono text-slate-700">
                      {currencyFmt(m.business_expenses)}
                    </td>
                    <td className="px-3 py-1.5 text-right font-mono text-amber-700">
                      {currencyFmt(m.vehicle_expenses)}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      {m.flagged_line_count > 0 ? (
                        <span className="text-red-600">{m.flagged_line_count}</span>
                      ) : (
                        <span className="text-slate-300">0</span>
                      )}
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onPickMonth(m.period);
                        }}
                        className="text-blue-600 hover:underline"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ));
                return [quarterRow, ...monthRows];
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Vendor rules */}
      <div className="rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2">
          <div className="text-xs font-semibold text-slate-600">
            Vendor rules ({rules.length})
          </div>
          <label className="flex items-center gap-1 text-xs text-slate-500">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
              className="rounded border-slate-300"
            />
            Show inactive
          </label>
        </div>
        {loadingRules ? (
          <div className="flex items-center justify-center py-6 text-sm text-slate-400">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Loading…
          </div>
        ) : rules.length === 0 ? (
          <div className="px-4 py-6 text-center text-sm text-slate-400">
            No rules yet. Use &quot;Save &amp; promote to rule&quot; on Review to create them as you classify.
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead className="bg-slate-50 text-left text-slate-500">
              <tr>
                <th className="px-3 py-2 font-medium">Pattern</th>
                <th className="px-3 py-2 font-medium">Bucket</th>
                <th className="px-3 py-2 font-medium">T2125</th>
                <th className="px-3 py-2 font-medium">Source</th>
                <th className="px-3 py-2 font-medium">Learned</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rules.map((r) => (
                <tr key={r.id} className={cn(!r.active && "opacity-50")}>
                  <td className="px-3 py-1.5 font-mono text-[11px] text-slate-700">{r.pattern}</td>
                  <td className="px-3 py-1.5">
                    <BucketBadge bucket={r.bucket} />
                  </td>
                  <td className="px-3 py-1.5 font-mono text-slate-600">{r.t2125_line || "—"}</td>
                  <td className="px-3 py-1.5 text-slate-600">{r.applies_to_source || "both"}</td>
                  <td className="px-3 py-1.5 text-slate-500">{r.source_month}</td>
                  <td className="px-3 py-1.5 text-right">
                    <button
                      type="button"
                      onClick={() => toggleRule(r)}
                      className={cn(
                        "rounded px-2 py-0.5 text-[10px] font-medium",
                        r.active
                          ? "bg-slate-100 text-slate-600 hover:bg-slate-200"
                          : "bg-emerald-100 text-emerald-700 hover:bg-emerald-200"
                      )}
                    >
                      {r.active ? "Deactivate" : "Reactivate"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  subtle,
}: {
  label: string;
  value: string;
  subtle?: string;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-lg font-semibold text-slate-800">{value}</div>
      {subtle ? <div className="mt-0.5 text-[10px] text-slate-400">{subtle}</div> : null}
    </div>
  );
}

// Unused helper exports kept out: createVendorRule is not wired (rules created via promote-to-rule
// on Review tab); intentionally omitted to keep the UI focused. Manual-rule creation dialog can
// be added in Session 4 if Henz needs a free-form rule editor.
void createVendorRule;
