"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ExternalLink, RefreshCw, Search, Star, GitFork, TrendingUp } from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { FeatureGate } from "@/components/molecules/FeatureGate";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  listEcosystemRepos,
  getEcosystemStatus,
  refreshEcosystem,
  type EcosystemCategory,
  type EcosystemRepo,
  type EcosystemSort,
  type EcosystemStatus,
} from "@/lib/ecosystem-intel-api";

const CATEGORY_TABS: { key: EcosystemCategory; label: string }[] = [
  { key: "all", label: "All" },
  { key: "ai_ml", label: "AI / ML" },
  { key: "swe", label: "SWE" },
  { key: "skills_ecosystem", label: "Skills Ecosystem" },
  { key: "trending", label: "Trending" },
];

const SORT_TABS: { key: EcosystemSort; label: string }[] = [
  { key: "stars", label: "Stars" },
  { key: "forks", label: "Forks" },
  { key: "growth_24h", label: "24h Growth" },
];

const CATEGORY_BADGE_COLOR: Record<string, string> = {
  ai_ml: "bg-purple-500/10 text-purple-300 border-purple-500/30",
  ai_ml_trending: "bg-purple-500/10 text-purple-300 border-purple-500/30",
  swe: "bg-blue-500/10 text-blue-300 border-blue-500/30",
  swe_trending: "bg-blue-500/10 text-blue-300 border-blue-500/30",
  skills_ecosystem: "bg-amber-500/10 text-amber-300 border-amber-500/30",
  other: "bg-slate-500/10 text-slate-400 border-slate-500/30",
};

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function formatRelativeTime(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const hours = Math.floor(diff / 3_600_000);
  if (hours < 1) return "just now";
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function categoryLabel(category: string): string {
  switch (category) {
    case "ai_ml":
    case "ai_ml_trending":
      return "AI/ML";
    case "swe":
    case "swe_trending":
      return "SWE";
    case "skills_ecosystem":
      return "Skills";
    default:
      return category;
  }
}

export default function EcosystemIntelPage() {
  const { isSignedIn } = useAuth();
  const [repos, setRepos] = useState<EcosystemRepo[]>([]);
  const [status, setStatus] = useState<EcosystemStatus | null>(null);
  const [category, setCategory] = useState<EcosystemCategory>("all");
  const [sort, setSort] = useState<EcosystemSort>("stars");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      const s = await getEcosystemStatus();
      setStatus(s);
    } catch {
      setStatus(null);
    }
  }, []);

  const loadRepos = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listEcosystemRepos({ category, sort, limit: 250 });
      setRepos(data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to load ecosystem feed";
      setError(message);
      setRepos([]);
    } finally {
      setLoading(false);
    }
  }, [category, sort]);

  useEffect(() => {
    if (!isSignedIn) return;
    void loadStatus();
    void loadRepos();
  }, [isSignedIn, loadStatus, loadRepos]);

  const filtered = useMemo(() => {
    if (!search.trim()) return repos;
    const q = search.toLowerCase();
    return repos.filter(
      (r) =>
        r.full_name.toLowerCase().includes(q) ||
        r.description?.toLowerCase().includes(q) ||
        r.topics.some((t) => t.toLowerCase().includes(q)),
    );
  }, [repos, search]);

  const handleRefresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    setError(null);
    try {
      const result = await refreshEcosystem();
      if (result.error) {
        setError(`Refresh completed with warning: ${result.error}`);
      }
      await loadStatus();
      await loadRepos();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Refresh failed";
      setError(message);
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <FeatureGate flag="ecosystem_intel" label="Ecosystem Intel">
      <DashboardPageLayout
        signedOut={{
          message: "Sign in to view ecosystem intel.",
          forceRedirectUrl: "/ecosystem-intel",
          signUpForceRedirectUrl: "/ecosystem-intel",
        }}
        title="Ecosystem Intel"
        description="Trending repos in the Claude Code / agent ecosystem. Refreshes every 24h."
      >
        <div className="space-y-4">
          {/* Header strip */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[color:var(--surface-border)] bg-[color:var(--surface-card)] px-4 py-3">
            <div className="flex flex-wrap items-center gap-4 text-sm text-[color:var(--text-muted)]">
              <span>
                <span className="font-medium text-[color:var(--text)]">
                  {status?.repo_count ?? "—"}
                </span>{" "}
                repos tracked
              </span>
              <span>Synced {formatRelativeTime(status?.last_synced_at ?? null)}</span>
              {status && !status.has_token ? (
                <span className="rounded bg-amber-500/10 px-2 py-0.5 text-xs text-amber-300">
                  No GITHUB_API_TOKEN configured — refresh disabled
                </span>
              ) : null}
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={handleRefresh}
              disabled={refreshing || !status?.has_token}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
              <span className="ml-1.5">{refreshing ? "Refreshing…" : "Refresh"}</span>
            </Button>
          </div>

          {/* Filter tabs */}
          <div className="flex flex-wrap items-center gap-2">
            {CATEGORY_TABS.map((tab) => (
              <button
                type="button"
                key={tab.key}
                onClick={() => setCategory(tab.key)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm font-medium transition",
                  category === tab.key
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)]"
                    : "text-[color:var(--text-muted)] hover:bg-[color:var(--surface-muted)]",
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Sort + Search */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              {SORT_TABS.map((tab) => (
                <button
                  type="button"
                  key={tab.key}
                  onClick={() => setSort(tab.key)}
                  className={cn(
                    "flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-medium transition",
                    sort === tab.key
                      ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)]"
                      : "text-[color:var(--text-muted)] hover:bg-[color:var(--surface-muted)]",
                  )}
                >
                  {tab.key === "stars" ? (
                    <Star className="h-3 w-3" />
                  ) : tab.key === "forks" ? (
                    <GitFork className="h-3 w-3" />
                  ) : (
                    <TrendingUp className="h-3 w-3" />
                  )}
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[color:var(--text-muted)]" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search repos…"
                className="w-64 rounded-md border border-[color:var(--surface-border)] bg-[color:var(--surface-card)] py-1.5 pl-8 pr-3 text-sm placeholder:text-[color:var(--text-muted)] focus:border-[color:var(--accent)] focus:outline-none"
              />
            </div>
          </div>

          {/* Error banner */}
          {error ? (
            <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
              {error}
            </div>
          ) : null}

          {/* Repo table */}
          <div className="overflow-hidden rounded-lg border border-[color:var(--surface-border)] bg-[color:var(--surface-card)]">
            <table className="w-full text-sm">
              <thead className="border-b border-[color:var(--surface-border)] text-left text-xs uppercase tracking-wide text-[color:var(--text-muted)]">
                <tr>
                  <th className="px-3 py-2 w-10">#</th>
                  <th className="px-3 py-2">Repository</th>
                  <th className="px-3 py-2">Category</th>
                  <th className="px-3 py-2">Language</th>
                  <th className="px-3 py-2 text-right">Stars</th>
                  <th className="px-3 py-2 text-right">Forks</th>
                  <th className="px-3 py-2 text-right">24h Growth</th>
                  <th className="px-3 py-2">Last Pushed</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={8} className="px-3 py-8 text-center text-[color:var(--text-muted)]">
                      Loading…
                    </td>
                  </tr>
                ) : filtered.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-3 py-8 text-center text-[color:var(--text-muted)]">
                      {repos.length === 0
                        ? "No repos yet. Click Refresh to fetch the first batch."
                        : "No repos match the current filter."}
                    </td>
                  </tr>
                ) : (
                  filtered.map((r, i) => (
                    <tr
                      key={r.id}
                      className="border-b border-[color:var(--surface-border)] transition hover:bg-[color:var(--surface-muted)] last:border-b-0"
                    >
                      <td className="px-3 py-2 text-xs text-[color:var(--text-muted)]">{i + 1}</td>
                      <td className="px-3 py-2 min-w-0">
                        <a
                          href={r.html_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="group inline-flex items-center gap-1.5"
                        >
                          <span className="font-medium text-[color:var(--text)] group-hover:text-[color:var(--accent-strong)]">
                            {r.full_name}
                          </span>
                          <ExternalLink className="h-3 w-3 text-[color:var(--text-muted)] opacity-0 transition group-hover:opacity-100" />
                        </a>
                        {r.description ? (
                          <div className="mt-0.5 line-clamp-1 text-xs text-[color:var(--text-muted)]">
                            {r.description}
                          </div>
                        ) : null}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={cn(
                            "inline-flex rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide",
                            CATEGORY_BADGE_COLOR[r.category] ?? CATEGORY_BADGE_COLOR.other,
                          )}
                        >
                          {categoryLabel(r.category)}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-xs text-[color:var(--text-muted)]">
                        {r.language ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        <span className="inline-flex items-center gap-1">
                          <Star className="h-3 w-3 text-amber-400" />
                          {formatNumber(r.stars)}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-[color:var(--text-muted)]">
                        {formatNumber(r.forks)}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {r.growth_24h > 0 ? (
                          <span className="text-emerald-400">+{formatNumber(r.growth_24h)}</span>
                        ) : (
                          <span className="text-[color:var(--text-muted)]">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-xs text-[color:var(--text-muted)]">
                        {formatRelativeTime(r.pushed_at)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <p className="text-xs text-[color:var(--text-muted)]">
            Data from GitHub Search API. Refresh runs automatically every 24 hours; admin can
            trigger manual refresh. Showing top {filtered.length} of {repos.length}.
          </p>
        </div>
      </DashboardPageLayout>
    </FeatureGate>
  );
}
