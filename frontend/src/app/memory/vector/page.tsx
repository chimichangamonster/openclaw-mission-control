"use client";

export const dynamic = "force-dynamic";

/* eslint-disable @typescript-eslint/no-explicit-any */
import { useCallback, useEffect, useState } from "react";
import {
  Brain,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { FeatureGate } from "@/components/molecules/FeatureGate";
import { Button } from "@/components/ui/button";
import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";
import { cn } from "@/lib/utils";
import {
  listVectorMemories,
  searchVectorMemories,
  deleteVectorMemory,
  getVectorMemoryStats,
  type VectorMemory,
  type VectorMemorySearchResult,
  type VectorMemoryStats,
} from "@/lib/vector-memory-api";

const PAGE_SIZE = 25;

export default function VectorMemoryPage() {
  const { isSignedIn } = useAuth();

  // Data state
  const [memories, setMemories] = useState<VectorMemory[]>([]);
  const [searchResults, setSearchResults] = useState<
    VectorMemorySearchResult[]
  >([]);
  const [stats, setStats] = useState<VectorMemoryStats | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);

  // UI state
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Delete state
  const [deleteTarget, setDeleteTarget] = useState<{
    id: string;
    content: string;
  } | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const loadMemories = useCallback(
    async (newOffset = 0) => {
      try {
        setLoading(true);
        const res = await listVectorMemories({
          source: sourceFilter || undefined,
          limit: PAGE_SIZE,
          offset: newOffset,
        });
        setMemories(res.items);
        setTotal(res.total);
        setOffset(newOffset);
      } catch {
        setMemories([]);
        setTotal(0);
      } finally {
        setLoading(false);
      }
    },
    [sourceFilter],
  );

  const loadStats = useCallback(async () => {
    try {
      const data = await getVectorMemoryStats();
      setStats(data);
    } catch {
      setStats(null);
    }
  }, []);

  useEffect(() => {
    if (isSignedIn) {
      loadMemories();
      loadStats();
    }
  }, [isSignedIn, loadMemories, loadStats]);

  const handleSearch = async () => {
    const q = searchQuery.trim();
    if (!q) {
      setActiveSearch("");
      setSearchResults([]);
      return;
    }
    try {
      setSearching(true);
      const results = await searchVectorMemories(
        q,
        20,
        sourceFilter || undefined,
      );
      setSearchResults(results);
      setActiveSearch(q);
    } catch {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  };

  const clearSearch = () => {
    setSearchQuery("");
    setActiveSearch("");
    setSearchResults([]);
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteVectorMemory(deleteTarget.id);
      setDeleteTarget(null);
      if (activeSearch) {
        setSearchResults((prev) =>
          prev.filter((m) => m.id !== deleteTarget.id),
        );
      } else {
        await loadMemories(offset);
      }
      await loadStats();
    } catch (err: any) {
      setDeleteError(err?.message || "Failed to delete memory");
    } finally {
      setDeleting(false);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const isSearchMode = activeSearch.length > 0;

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffDays = Math.floor(diffMs / 86400000);
    if (diffDays === 0) {
      return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    }
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays}d ago`;
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  };

  const truncate = (text: string, max = 200) =>
    text.length > max ? text.slice(0, max) + "..." : text;

  return (
    <FeatureGate flag="agent_memory" label="Agent Memory">
      <DashboardPageLayout
        signedOut={{
          message: "Sign in to explore agent vector memory.",
          forceRedirectUrl: "/memory/vector",
          signUpForceRedirectUrl: "/memory/vector",
        }}
        title="Vector Memory"
        description="Browse and search agent semantic memories stored via pgvector."
        headerActions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              loadMemories();
              loadStats();
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
        {/* Stats row */}
        {stats && (
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] p-3">
              <p className="text-xs text-[color:var(--text-quiet)]">
                Total Memories
              </p>
              <p className="mt-1 text-2xl font-semibold text-[color:var(--text)]">
                {stats.total_memories}
              </p>
            </div>
            <div className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] p-3">
              <p className="text-xs text-[color:var(--text-quiet)]">Sources</p>
              <p className="mt-1 text-2xl font-semibold text-[color:var(--text)]">
                {stats.sources.length}
              </p>
            </div>
            {stats.sources.slice(0, 2).map((s) => (
              <div
                key={s.source}
                className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] p-3"
              >
                <p className="text-xs text-[color:var(--text-quiet)] truncate">
                  {s.source}
                </p>
                <p className="mt-1 text-2xl font-semibold text-[color:var(--text)]">
                  {s.count}
                </p>
              </div>
            ))}
          </div>
        )}

        {/* Search + filter bar */}
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[color:var(--text-quiet)]" />
            <input
              type="text"
              placeholder="Semantic search across memories..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              className="w-full rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] py-2 pl-9 pr-3 text-sm text-[color:var(--text)] placeholder:text-[color:var(--text-quiet)] focus:border-[color:var(--accent)] focus:outline-none focus:ring-1 focus:ring-[color:var(--accent)]"
            />
          </div>
          <select
            value={sourceFilter}
            onChange={(e) => {
              setSourceFilter(e.target.value);
              if (!activeSearch) {
                setOffset(0);
              }
            }}
            className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] px-3 py-2 text-sm text-[color:var(--text)]"
          >
            <option value="">All sources</option>
            {stats?.sources.map((s) => (
              <option key={s.source} value={s.source}>
                {s.source} ({s.count})
              </option>
            ))}
          </select>
          <div className="flex gap-2">
            <Button size="sm" onClick={handleSearch} disabled={searching}>
              {searching ? "Searching..." : "Search"}
            </Button>
            {isSearchMode && (
              <Button variant="outline" size="sm" onClick={clearSearch}>
                Clear
              </Button>
            )}
          </div>
        </div>

        {/* Search mode indicator */}
        {isSearchMode && (
          <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 text-sm text-blue-800 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-200">
            Showing {searchResults.length} semantic matches for &ldquo;
            {activeSearch}&rdquo;
          </div>
        )}

        {/* Memory list */}
        {loading && !isSearchMode ? (
          <div className="flex items-center justify-center py-16 text-[color:var(--text-quiet)]">
            <RefreshCw className="mr-2 h-5 w-5 animate-spin" />
            Loading memories...
          </div>
        ) : !isSearchMode && memories.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-[color:var(--text-quiet)]">
            <Brain className="mb-3 h-10 w-10 opacity-30" />
            <p>No vector memories stored yet</p>
            <p className="mt-1 text-xs">
              Agents will store semantic memories as they work.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {(isSearchMode ? searchResults : memories).map((m) => {
              const isExpanded = expandedId === m.id;
              const similarity =
                "similarity" in m ? (m as VectorMemorySearchResult).similarity : null;
              return (
                <div
                  key={m.id}
                  className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] transition hover:border-[color:var(--accent-soft)]"
                >
                  <button
                    onClick={() => setExpandedId(isExpanded ? null : m.id)}
                    className="w-full px-4 py-3 text-left"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-[color:var(--text)]">
                          {isExpanded ? m.content : truncate(m.content)}
                        </p>
                        <div className="mt-1.5 flex flex-wrap items-center gap-2">
                          <span className="inline-flex items-center rounded-full bg-[color:var(--accent-soft)] px-2 py-0.5 text-xs font-medium text-[color:var(--accent-strong)]">
                            {m.source}
                          </span>
                          {m.agent_id && (
                            <span className="text-xs text-[color:var(--text-quiet)]">
                              agent: {m.agent_id}
                            </span>
                          )}
                          {similarity !== null && (
                            <span className="text-xs text-[color:var(--text-quiet)]">
                              {(similarity * 100).toFixed(1)}% match
                            </span>
                          )}
                          <span className="text-xs text-[color:var(--text-quiet)]">
                            {formatDate(m.created_at)}
                          </span>
                        </div>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteTarget({
                            id: m.id,
                            content: truncate(m.content, 80),
                          });
                        }}
                        className="shrink-0 rounded p-1 text-[color:var(--text-quiet)] hover:bg-red-100 hover:text-red-600 dark:hover:bg-red-950"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {/* Pagination (list mode only) */}
        {!isSearchMode && totalPages > 1 && (
          <div className="mt-4 flex items-center justify-between">
            <p className="text-sm text-[color:var(--text-quiet)]">
              {total} memories total
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => loadMemories(offset - PAGE_SIZE)}
                disabled={offset === 0 || loading}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-sm text-[color:var(--text-quiet)]">
                {currentPage} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => loadMemories(offset + PAGE_SIZE)}
                disabled={offset + PAGE_SIZE >= total || loading}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        {/* Delete confirmation */}
        <ConfirmActionDialog
          open={!!deleteTarget}
          onOpenChange={(open) => {
            if (!open) setDeleteTarget(null);
          }}
          title="Delete memory?"
          description={
            <>
              This will permanently delete this vector memory. This cannot be
              undone.
              {deleteTarget && (
                <span className="mt-2 block text-xs text-[color:var(--text-quiet)]">
                  &ldquo;{deleteTarget.content}&rdquo;
                </span>
              )}
            </>
          }
          onConfirm={handleDelete}
          isConfirming={deleting}
          errorMessage={deleteError}
        />
      </DashboardPageLayout>
    </FeatureGate>
  );
}
