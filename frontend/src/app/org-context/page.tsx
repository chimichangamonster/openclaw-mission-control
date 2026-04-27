"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Eye,
  EyeOff,
  FileText,
  Loader2,
  Lock,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { FeatureGate } from "@/components/molecules/FeatureGate";
import { Button } from "@/components/ui/button";
import { useOrganizationMembership } from "@/lib/use-organization-membership";
import { cn } from "@/lib/utils";
import {
  CATEGORIES,
  MODERATE_CATEGORIES,
  type Category,
  type OrgContextFile,
  type OrgContextFileDetail,
  type Visibility,
  deleteFile,
  getFile,
  getStats,
  listFiles,
  patchFile,
  uploadFile,
} from "@/lib/org-context-api";

const STALENESS_THRESHOLD_DAYS = 60;

function ageBadge(ageDays: number, isLiving: boolean): {
  label: string;
  tone: "ok" | "warn";
} {
  if (ageDays === 0) return { label: "today", tone: "ok" };
  const label = ageDays === 1 ? "1 day ago" : `${ageDays} days ago`;
  // Staleness only matters for living data — static reference docs are
  // expected to outlast the threshold (regulations don't expire).
  if (isLiving && ageDays >= STALENESS_THRESHOLD_DAYS) {
    return { label, tone: "warn" };
  }
  return { label, tone: "ok" };
}

function CategoryPill({ category }: { category: string }) {
  const moderate = MODERATE_CATEGORIES.has(category);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium",
        moderate
          ? "border-blue-200 bg-blue-50 text-blue-700"
          : "border-slate-200 bg-slate-50 text-slate-700"
      )}
      title={
        moderate
          ? "Moderate redaction — phones, emails, and addresses are preserved"
          : "Strict redaction — all PII stripped before embedding"
      }
    >
      {category}
    </span>
  );
}

function VisibilityIcon({ visibility }: { visibility: Visibility }) {
  return visibility === "private" ? (
    <span title="Private — only owner + admins can see this">
      <EyeOff className="h-3.5 w-3.5 text-amber-600" />
    </span>
  ) : (
    <span title="Shared — visible to all org members">
      <Eye className="h-3.5 w-3.5 text-emerald-600" />
    </span>
  );
}

function StalenessBanner({ ageDays }: { ageDays: number }) {
  if (ageDays < STALENESS_THRESHOLD_DAYS) return null;
  return (
    <div className="mb-3 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <div>
        <p className="font-medium">
          This file is {ageDays} days old.
        </p>
        <p className="mt-0.5 text-amber-800">
          If it&apos;s tagged as living data (prospects, customers,
          deployments), agents will warn when citing it. Re-upload to
          refresh.
        </p>
      </div>
    </div>
  );
}

function OrgContextPageInner() {
  const { isSignedIn } = useAuth();
  const { isAdmin } = useOrganizationMembership(isSignedIn);

  const [files, setFiles] = useState<OrgContextFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterCategory, setFilterCategory] = useState<string>("");
  const [stats, setStats] = useState<{
    total: number;
    by_category: { category: string; count: number }[];
  } | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<OrgContextFileDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Upload form state
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadFile_, setUploadFile_] = useState<File | null>(null);
  const [uploadCategory, setUploadCategory] = useState<Category>("other");
  const [uploadSource, setUploadSource] = useState("");
  const [uploadVisibility, setUploadVisibility] = useState<Visibility>("shared");
  const [uploadLiving, setUploadLiving] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const [deleting, setDeleting] = useState<string | null>(null);

  const refreshFiles = useCallback(async () => {
    try {
      setLoading(true);
      const [listResult, statsResult] = await Promise.all([
        listFiles(filterCategory || undefined),
        getStats(),
      ]);
      setFiles(listResult);
      setStats(statsResult);
    } catch {
      setFiles([]);
    } finally {
      setLoading(false);
    }
  }, [filterCategory]);

  useEffect(() => {
    if (isSignedIn) {
      refreshFiles();
    }
  }, [isSignedIn, refreshFiles]);

  const openFile = async (id: string) => {
    try {
      setSelectedId(id);
      setLoadingDetail(true);
      const d = await getFile(id);
      setDetail(d);
    } catch {
      setDetail(null);
    } finally {
      setLoadingDetail(false);
    }
  };

  const submitUpload = async () => {
    if (!uploadFile_) return;
    try {
      setUploading(true);
      setUploadError(null);
      await uploadFile(uploadFile_, {
        category: uploadCategory,
        source: uploadSource || null,
        visibility: uploadVisibility,
        is_living_data: uploadLiving,
      });
      // Reset form
      setUploadFile_(null);
      setUploadSource("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      await refreshFiles();
    } catch (e) {
      setUploadError(
        e instanceof Error ? e.message : "Upload failed — see console"
      );
    } finally {
      setUploading(false);
    }
  };

  const togglePatch = async (
    id: string,
    field: "visibility" | "is_living_data",
    nextValue: Visibility | boolean
  ) => {
    try {
      const updated = await patchFile(id, { [field]: nextValue });
      setFiles((prev) => prev.map((f) => (f.id === id ? updated : f)));
      if (selectedId === id && detail) {
        setDetail({ ...detail, ...updated });
      }
    } catch {
      // Revert on next refresh
      await refreshFiles();
    }
  };

  const handleDelete = async (id: string) => {
    if (
      !window.confirm(
        "Delete this org-context file? Agents will lose access to its content immediately."
      )
    )
      return;
    try {
      setDeleting(id);
      await deleteFile(id);
      if (selectedId === id) {
        setSelectedId(null);
        setDetail(null);
      }
      await refreshFiles();
    } finally {
      setDeleting(null);
    }
  };

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to manage org-context files.",
        forceRedirectUrl: "/org-context",
        signUpForceRedirectUrl: "/org-context",
      }}
      title="Org-Context Files"
      description="Persistent organizational context — prospects, regulations, brand guides — that any chat, cron, or agent can query."
    >
      {/* Stats strip */}
      {stats && (
        <div className="mb-4 flex flex-wrap gap-3 text-xs text-[color:var(--text-quiet)]">
          <span>
            <strong className="text-[color:var(--text)]">{stats.total}</strong> files
          </span>
          {stats.by_category.map((c) => (
            <span key={c.category}>
              {c.category}: <strong className="text-[color:var(--text)]">{c.count}</strong>
            </span>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[420px_1fr]">
        {/* Left column — list + upload */}
        <div className="space-y-4">
          {/* Upload card (admin-only) */}
          {isAdmin ? (
            <div className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] p-4">
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <Upload className="h-4 w-4" />
                Upload context file
              </h3>

              <input
                ref={fileInputRef}
                type="file"
                onChange={(e) => setUploadFile_(e.target.files?.[0] ?? null)}
                className="mb-2 w-full text-xs"
                accept=".pdf,.png,.jpg,.jpeg,.gif,.webp,.txt,.csv,.md,.json"
              />

              <div className="mb-2 grid grid-cols-2 gap-2">
                <label className="block text-xs">
                  <span className="mb-0.5 block text-[color:var(--text-quiet)]">
                    Category
                  </span>
                  <select
                    value={uploadCategory}
                    onChange={(e) => setUploadCategory(e.target.value as Category)}
                    className="w-full rounded border border-[color:var(--border)] bg-[color:var(--surface)] px-2 py-1 text-xs"
                  >
                    {CATEGORIES.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-xs">
                  <span className="mb-0.5 block text-[color:var(--text-quiet)]">
                    Visibility
                  </span>
                  <select
                    value={uploadVisibility}
                    onChange={(e) =>
                      setUploadVisibility(e.target.value as Visibility)
                    }
                    className="w-full rounded border border-[color:var(--border)] bg-[color:var(--surface)] px-2 py-1 text-xs"
                  >
                    <option value="shared">Shared</option>
                    <option value="private">Private</option>
                  </select>
                </label>
              </div>

              <label className="mb-2 block text-xs">
                <span className="mb-0.5 block text-[color:var(--text-quiet)]">
                  Source (optional note)
                </span>
                <input
                  type="text"
                  value={uploadSource}
                  onChange={(e) => setUploadSource(e.target.value)}
                  placeholder="e.g. exported from HubSpot, 2026-04-27"
                  className="w-full rounded border border-[color:var(--border)] bg-[color:var(--surface)] px-2 py-1 text-xs"
                />
              </label>

              <label className="mb-3 flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={uploadLiving}
                  onChange={(e) => setUploadLiving(e.target.checked)}
                />
                <span>
                  Living data (changes over time — agents will surface staleness
                  warnings after {STALENESS_THRESHOLD_DAYS} days)
                </span>
              </label>

              {/* Redaction info banner */}
              <p className="mb-3 text-[11px] text-[color:var(--text-quiet)]">
                {MODERATE_CATEGORIES.has(uploadCategory) ? (
                  <>
                    <strong>Moderate redaction:</strong> credentials and
                    financials stripped. Phones, emails, and addresses
                    preserved (signal for this category).
                  </>
                ) : (
                  <>
                    <strong>Strict redaction:</strong> credentials, financials,
                    AND PII (phones, emails, addresses) all stripped before
                    embedding.
                  </>
                )}
              </p>

              {uploadError && (
                <p className="mb-2 rounded bg-rose-50 px-2 py-1 text-[11px] text-rose-700">
                  {uploadError}
                </p>
              )}

              <Button
                size="sm"
                onClick={submitUpload}
                disabled={!uploadFile_ || uploading}
                className="w-full"
              >
                {uploading ? (
                  <>
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    Uploading...
                  </>
                ) : (
                  <>
                    <Upload className="mr-1.5 h-3.5 w-3.5" />
                    Upload + extract + embed
                  </>
                )}
              </Button>
            </div>
          ) : (
            <div className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface-muted)] p-3 text-xs text-[color:var(--text-quiet)]">
              <Lock className="mr-1 inline h-3 w-3" />
              Only org admins can upload context files.
            </div>
          )}

          {/* List */}
          <div>
            <div className="mb-2 flex items-center justify-between gap-2">
              <select
                value={filterCategory}
                onChange={(e) => setFilterCategory(e.target.value)}
                className="rounded border border-[color:var(--border)] bg-[color:var(--surface)] px-2 py-1 text-xs"
              >
                <option value="">All categories</option>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <button
                onClick={refreshFiles}
                className="text-[color:var(--text-quiet)] hover:text-[color:var(--text)]"
                aria-label="Refresh"
              >
                <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
              </button>
            </div>

            {loading ? (
              <p className="text-xs text-[color:var(--text-quiet)]">Loading...</p>
            ) : files.length === 0 ? (
              <p className="text-xs text-[color:var(--text-quiet)]">
                No files yet. Upload one above to give agents persistent
                context they can cite.
              </p>
            ) : (
              <ul className="space-y-1">
                {files.map((f) => {
                  const age = ageBadge(f.age_days, f.is_living_data);
                  return (
                    <li
                      key={f.id}
                      className={cn(
                        "rounded-md border px-2 py-2 text-xs transition cursor-pointer",
                        selectedId === f.id
                          ? "border-blue-300 bg-blue-50"
                          : "border-[color:var(--border)] hover:bg-[color:var(--surface-muted)]"
                      )}
                      onClick={() => openFile(f.id)}
                    >
                      <div className="flex items-center gap-2">
                        <FileText className="h-3.5 w-3.5 shrink-0 text-[color:var(--text-quiet)]" />
                        <span className="flex-1 truncate font-medium">
                          {f.filename}
                        </span>
                        <VisibilityIcon visibility={f.visibility} />
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        <CategoryPill category={f.category} />
                        <span
                          className={cn(
                            "text-[10px]",
                            age.tone === "warn"
                              ? "font-medium text-amber-700"
                              : "text-[color:var(--text-quiet)]"
                          )}
                        >
                          {age.label}
                        </span>
                        {f.is_living_data ? (
                          <span className="text-[10px] text-[color:var(--text-quiet)]">
                            living
                          </span>
                        ) : (
                          <span className="text-[10px] text-[color:var(--text-quiet)]">
                            static
                          </span>
                        )}
                        {!f.has_embedding && (
                          <span className="text-[10px] font-medium text-rose-600">
                            (no embedding)
                          </span>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>

        {/* Right column — detail */}
        <div className="min-w-0 rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] p-4">
          {!selectedId ? (
            <div className="flex flex-col items-center justify-center py-12 text-[color:var(--text-quiet)]">
              <FileText className="mb-3 h-10 w-10 opacity-30" />
              <p className="text-sm">Select a file to preview</p>
              <p className="mt-1 text-xs">
                The text shown is the redacted, embedded version — same view
                agents see.
              </p>
            </div>
          ) : loadingDetail ? (
            <div className="flex items-center justify-center py-12 text-[color:var(--text-quiet)]">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Loading...
            </div>
          ) : !detail ? (
            <p className="text-xs text-rose-600">Failed to load file.</p>
          ) : (
            <div>
              <div className="mb-3 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="truncate text-base font-semibold">
                    {detail.filename}
                  </h3>
                  <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-[color:var(--text-quiet)]">
                    <CategoryPill category={detail.category} />
                    <VisibilityIcon visibility={detail.visibility} />
                    {detail.visibility}
                    {" · "}
                    {detail.is_living_data ? "living" : "static"}
                    {" · "}
                    uploaded{" "}
                    {ageBadge(detail.age_days, detail.is_living_data).label}
                    {detail.source && (
                      <>
                        {" · "}
                        from {detail.source}
                      </>
                    )}
                  </p>
                </div>
                {isAdmin && (
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      onClick={() =>
                        togglePatch(
                          detail.id,
                          "visibility",
                          detail.visibility === "shared" ? "private" : "shared"
                        )
                      }
                      className="rounded border border-[color:var(--border)] px-2 py-1 text-[11px] hover:bg-[color:var(--surface-muted)]"
                      title="Toggle visibility"
                    >
                      Make {detail.visibility === "shared" ? "private" : "shared"}
                    </button>
                    <button
                      onClick={() =>
                        togglePatch(
                          detail.id,
                          "is_living_data",
                          !detail.is_living_data
                        )
                      }
                      className="rounded border border-[color:var(--border)] px-2 py-1 text-[11px] hover:bg-[color:var(--surface-muted)]"
                      title="Toggle living-data flag"
                    >
                      Mark {detail.is_living_data ? "static" : "living"}
                    </button>
                    <button
                      onClick={() => handleDelete(detail.id)}
                      disabled={deleting === detail.id}
                      className="rounded border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700 hover:bg-rose-100 disabled:opacity-50"
                      title="Delete file"
                    >
                      {deleting === detail.id ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <Trash2 className="h-3 w-3" />
                      )}
                    </button>
                  </div>
                )}
              </div>

              <StalenessBanner ageDays={detail.age_days} />

              <pre className="max-h-[600px] w-full overflow-auto whitespace-pre-wrap rounded-lg border border-[color:var(--border)] bg-[color:var(--surface-muted)] p-4 font-mono text-xs leading-relaxed text-[color:var(--text)]">
                {detail.extracted_text || "(no extracted text)"}
              </pre>
            </div>
          )}
        </div>
      </div>
    </DashboardPageLayout>
  );
}

export default function OrgContextPage() {
  return (
    <FeatureGate flag="org_context" label="Org-Context Files">
      <OrgContextPageInner />
    </FeatureGate>
  );
}
