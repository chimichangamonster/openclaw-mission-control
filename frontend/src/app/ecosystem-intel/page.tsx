"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ExternalLink,
  RefreshCw,
  Search,
  Star,
  GitFork,
  TrendingUp,
  Pin,
} from "lucide-react";

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
  { key: "trending", label: "Trending" },
  { key: "all", label: "All" },
  { key: "ai_ml", label: "AI / ML" },
  { key: "swe", label: "SWE" },
  { key: "skills_ecosystem", label: "Skills Ecosystem" },
];

const SORT_TABS: { key: EcosystemSort; label: string }[] = [
  { key: "stars", label: "Stars" },
  { key: "forks", label: "Forks" },
  { key: "growth_24h", label: "24h Growth" },
];

// Section dividers for "All" tab — order + cap per section
const ALL_TAB_SECTIONS: { category: string; label: string; cap: number }[] = [
  { category: "skills_ecosystem", label: "Skills Ecosystem", cap: 50 },
  { category: "ai_ml_trending", label: "AI/ML — Trending", cap: 20 },
  { category: "ai_ml", label: "AI / ML", cap: 30 },
  { category: "swe_trending", label: "SWE — Trending", cap: 15 },
  { category: "swe", label: "Software Engineering", cap: 30 },
];

const LANGUAGE_COLORS: Record<string, string> = {
  TypeScript: "bg-blue-500",
  JavaScript: "bg-yellow-400",
  Python: "bg-emerald-500",
  Rust: "bg-orange-600",
  Go: "bg-cyan-400",
  C: "bg-slate-400",
  "C++": "bg-pink-500",
  Java: "bg-red-500",
  Shell: "bg-green-400",
  HTML: "bg-orange-400",
  CSS: "bg-blue-400",
  Ruby: "bg-red-600",
  Swift: "bg-orange-500",
  Kotlin: "bg-purple-500",
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

function RepoCard({
  repo,
  onTopicClick,
}: {
  repo: EcosystemRepo;
  onTopicClick: (topic: string) => void;
}) {
  const langColor = repo.language ? LANGUAGE_COLORS[repo.language] || "bg-slate-500" : null;
  const visibleTopics = repo.topics.slice(0, 4);

  return (
    <div
      className={cn(
        "group flex h-full flex-col rounded-lg border bg-[color:var(--surface-card)] p-3.5 transition",
        "hover:border-[color:var(--accent-soft)] hover:shadow-md",
        repo.is_pinned
          ? "border-amber-500/40"
          : "border-[color:var(--surface-border)]",
      )}
    >
      {/* Header: name + pin + external link */}
      <div className="mb-1.5 flex min-w-0 items-start gap-1.5">
        {repo.is_pinned ? (
          <span title="Pinned by VantageClaw" className="mt-0.5 shrink-0 text-amber-400">
            <Pin className="h-3.5 w-3.5" />
          </span>
        ) : null}
        <a
          href={repo.html_url}
          target="_blank"
          rel="noopener noreferrer"
          className="group/link inline-flex min-w-0 flex-1 items-baseline gap-1"
        >
          <span className="truncate text-sm font-semibold text-[color:var(--text)] group-hover/link:text-[color:var(--accent-strong)]">
            {repo.full_name}
          </span>
          <ExternalLink className="h-3 w-3 shrink-0 self-center text-[color:var(--text-muted)] opacity-0 transition group-hover/link:opacity-100" />
        </a>
      </div>

      {/* Description */}
      <p
        className="mb-3 line-clamp-2 text-xs leading-relaxed text-[color:var(--text-muted)]"
        title={repo.description ?? undefined}
      >
        {repo.description ?? "No description"}
      </p>

      {/* Topic chips */}
      {visibleTopics.length > 0 ? (
        <div className="mb-3 flex flex-wrap gap-1">
          {visibleTopics.map((t) => (
            <button
              type="button"
              key={t}
              onClick={() => onTopicClick(t)}
              className="rounded bg-[color:var(--surface-muted)] px-1.5 py-0.5 text-[10px] text-[color:var(--text-muted)] transition hover:bg-[color:var(--accent-soft)] hover:text-[color:var(--accent-strong)]"
              title={`Search for "${t}"`}
            >
              {t}
            </button>
          ))}
          {repo.topics.length > 4 ? (
            <span className="px-1.5 py-0.5 text-[10px] text-[color:var(--text-muted)]">
              +{repo.topics.length - 4}
            </span>
          ) : null}
        </div>
      ) : null}

      {/* Bottom metadata row */}
      <div className="mt-auto flex items-center justify-between gap-2 text-xs">
        <div className="flex min-w-0 items-center gap-2">
          {repo.language ? (
            <span className="flex items-center gap-1 text-[color:var(--text-muted)]">
              <span className={cn("h-2 w-2 rounded-full", langColor)} />
              <span className="truncate">{repo.language}</span>
            </span>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-2.5 tabular-nums">
          <span className="inline-flex items-center gap-0.5 text-[color:var(--text-muted)]">
            <Star className="h-3 w-3 text-amber-400" />
            {formatNumber(repo.stars)}
          </span>
          <span className="inline-flex items-center gap-0.5 text-[color:var(--text-muted)]">
            <GitFork className="h-3 w-3" />
            {formatNumber(repo.forks)}
          </span>
          {repo.growth_24h > 0 ? (
            <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 font-medium text-emerald-400">
              +{formatNumber(repo.growth_24h)}
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function CardGrid({
  repos,
  onTopicClick,
}: {
  repos: EcosystemRepo[];
  onTopicClick: (topic: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
      {repos.map((r) => (
        <RepoCard key={r.id} repo={r} onTopicClick={onTopicClick} />
      ))}
    </div>
  );
}

export default function EcosystemIntelPage() {
  const { isSignedIn } = useAuth();
  const [repos, setRepos] = useState<EcosystemRepo[]>([]);
  const [status, setStatus] = useState<EcosystemStatus | null>(null);
  const [category, setCategory] = useState<EcosystemCategory>("trending");
  const [sort, setSort] = useState<EcosystemSort>("growth_24h");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    try {
      setStatus(await getEcosystemStatus());
    } catch {
      setStatus(null);
    }
  }, []);

  const loadRepos = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      // For "all" tab we need higher limit since we're slicing per category
      const limit = category === "all" ? 500 : 250;
      setRepos(await listEcosystemRepos({ category, sort, limit }));
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

  // Auto-pick a smart default sort when category changes
  const handleCategoryChange = useCallback((next: EcosystemCategory) => {
    setCategory(next);
    if (next === "trending") {
      setSort("growth_24h");
    } else if (sort === "growth_24h") {
      setSort("stars");
    }
  }, [sort]);

  const handleTopicClick = useCallback((topic: string) => {
    setSearch(topic);
  }, []);

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

  // Group by section for "All" tab
  const sections = useMemo(() => {
    if (category !== "all") return null;
    if (search.trim()) return null; // searching — flatten
    return ALL_TAB_SECTIONS.map((section) => ({
      ...section,
      repos: filtered
        .filter((r) => r.category === section.category)
        .slice(0, section.cap),
    })).filter((s) => s.repos.length > 0);
  }, [category, filtered, search]);

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

  const visibleCount = sections
    ? sections.reduce((acc, s) => acc + s.repos.length, 0)
    : filtered.length;

  return (
    <FeatureGate flag="ecosystem_intel" label="Ecosystem Intel">
      <DashboardPageLayout
        signedOut={{
          message: "Sign in to view ecosystem intel.",
          forceRedirectUrl: "/ecosystem-intel",
          signUpForceRedirectUrl: "/ecosystem-intel",
        }}
        title="Ecosystem Intel"
        description="Trending repos in the Claude Code / agent ecosystem. Refreshes daily."
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

          {/* Controls: filter tabs + sort + search */}
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              {CATEGORY_TABS.map((tab) => (
                <button
                  type="button"
                  key={tab.key}
                  onClick={() => handleCategoryChange(tab.key)}
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
              <div className="relative w-full sm:w-80">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[color:var(--text-muted)]" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={`Search ${repos.length} repos…`}
                  className="w-full rounded-md border border-[color:var(--surface-border)] bg-[color:var(--surface-card)] py-1.5 pl-8 pr-8 text-sm placeholder:text-[color:var(--text-muted)] focus:border-[color:var(--accent)] focus:outline-none"
                />
                {search ? (
                  <button
                    type="button"
                    onClick={() => setSearch("")}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-[color:var(--text-muted)] hover:text-[color:var(--text)]"
                    title="Clear search"
                  >
                    ✕
                  </button>
                ) : null}
              </div>
            </div>
          </div>

          {/* Error banner */}
          {error ? (
            <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
              {error}
            </div>
          ) : null}

          {/* Body */}
          {loading ? (
            <div className="flex h-64 items-center justify-center text-[color:var(--text-muted)]">
              Loading…
            </div>
          ) : visibleCount === 0 ? (
            <div className="flex h-64 flex-col items-center justify-center gap-2 text-[color:var(--text-muted)]">
              <p>
                {repos.length === 0
                  ? "No repos yet. Click Refresh to fetch the first batch."
                  : "No repos match the current filter."}
              </p>
              {search ? (
                <button
                  type="button"
                  onClick={() => setSearch("")}
                  className="text-xs text-[color:var(--accent-strong)] hover:underline"
                >
                  Clear search
                </button>
              ) : null}
            </div>
          ) : sections ? (
            <div className="space-y-8">
              {sections.map((s) => (
                <section key={s.category}>
                  <div className="mb-3 flex items-center justify-between">
                    <h2 className="text-sm font-semibold uppercase tracking-wide text-[color:var(--text-muted)]">
                      {s.label}
                      <span className="ml-2 text-xs font-normal normal-case">
                        ({s.repos.length}
                        {s.repos.length === s.cap ? "+" : ""})
                      </span>
                    </h2>
                    <button
                      type="button"
                      onClick={() => {
                        // Map ai_ml_trending → ai_ml, swe_trending → swe, etc., for the filter
                        const filter = (
                          {
                            ai_ml_trending: "ai_ml",
                            swe_trending: "swe",
                          } as Record<string, string>
                        )[s.category] ?? s.category;
                        handleCategoryChange(filter as EcosystemCategory);
                      }}
                      className="text-xs text-[color:var(--accent-strong)] hover:underline"
                    >
                      View all in {s.label} →
                    </button>
                  </div>
                  <CardGrid repos={s.repos} onTopicClick={handleTopicClick} />
                </section>
              ))}
            </div>
          ) : (
            <CardGrid repos={filtered} onTopicClick={handleTopicClick} />
          )}

          <p className="text-xs text-[color:var(--text-muted)]">
            Data from GitHub Search API. Refresh runs automatically every 24 hours; admin can
            trigger manual refresh. Showing {visibleCount} of {repos.length} loaded
            {search ? ` matching "${search}"` : ""}. Click any topic chip to search for it.
          </p>
        </div>
      </DashboardPageLayout>
    </FeatureGate>
  );
}
