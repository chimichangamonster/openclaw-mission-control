"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Filter,
  Key,
  RefreshCw,
  Shield,
  Settings,
  UserPlus,
  Image,
  FileText,
} from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { customFetch } from "@/api/mutator";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { getApiBaseUrl } from "@/lib/api-base";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type AuditEntry = {
  id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: Record<string, unknown>;
  user_id: string | null;
  user_name: string | null;
  ip_address: string | null;
  created_at: string;
};

type AuditResponse = {
  entries: AuditEntry[];
  total: number;
  limit: number;
  offset: number;
};

// ---------------------------------------------------------------------------
// Action formatting
// ---------------------------------------------------------------------------

const ACTION_ICONS: Record<string, typeof Key> = {
  "key.set": Key,
  "key.remove": Key,
  "settings.update": Settings,
  "member.add": UserPlus,
  "member.remove": UserPlus,
  "branding.logo_uploaded": Image,
  "branding.logo_removed": Image,
  "template.applied": FileText,
};

const ACTION_COLORS: Record<string, string> = {
  "key.set": "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  "key.remove": "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
  "settings.update": "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300",
  "member.add": "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300",
  "member.remove": "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
  "branding.logo_uploaded": "bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300",
  "branding.logo_removed": "bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300",
  "template.applied": "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300",
};

function formatAction(action: string): string {
  return action.replace(/\./g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDetails(details: Record<string, unknown>): string {
  const parts: string[] = [];
  if (details.key_type) parts.push(`Key: ${details.key_type}`);
  if (details.changed_fields) parts.push(`Fields: ${(details.changed_fields as string[]).join(", ")}`);
  if (details.filename) parts.push(`File: ${details.filename}`);
  if (details.endpoint_name) parts.push(`Endpoint: ${details.endpoint_name}`);
  if (details.template_id) parts.push(`Template: ${details.template_id}`);
  return parts.join(" | ") || JSON.stringify(details);
}

function timeAgo(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diff = now - then;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const PAGE_SIZE = 25;

export default function AuditPage() {
  const { isSignedIn } = useAuth();
  const [data, setData] = useState<AuditResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [actionFilter, setActionFilter] = useState("");
  const [availableActions, setAvailableActions] = useState<string[]>([]);

  const loadAudit = useCallback(
    async (newOffset = 0) => {
      setLoading(true);
      const baseUrl = getApiBaseUrl();
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(newOffset),
      });
      if (actionFilter) params.set("action", actionFilter);

      try {
        const res = await customFetch<{ status: number; data: AuditResponse }>(
          `${baseUrl}/api/v1/organization-settings/audit-log?${params}`,
          { method: "GET" },
        );
        const d = res.data ?? (res as unknown as AuditResponse);
        setData(d);
        setOffset(newOffset);

        // Collect unique actions for filter dropdown
        if (newOffset === 0 && !actionFilter) {
          const actions = [...new Set((d.entries || []).map((e: AuditEntry) => e.action))];
          if (actions.length > 0) setAvailableActions(actions);
        }
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    },
    [actionFilter],
  );

  useEffect(() => {
    if (isSignedIn) loadAudit(0);
  }, [isSignedIn, loadAudit]);

  const entries = data?.entries ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to view the audit log.",
        forceRedirectUrl: "/audit",
        signUpForceRedirectUrl: "/audit",
      }}
      title="Audit Log"
      description="Security events and configuration changes"
      headerActions={
        <button
          onClick={() => loadAudit(offset)}
          className="flex items-center gap-2 rounded-lg border border-[color:var(--border)] px-3 py-1.5 text-sm text-[color:var(--text-muted)] hover:bg-[color:var(--surface-muted)] transition"
          disabled={loading}
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      }
    >
      <div className="mx-auto max-w-4xl space-y-4 p-6">
        {/* Filters */}
        <div className="flex items-center gap-3">
          <Filter className="h-4 w-4 text-[color:var(--text-muted)]" />
          <select
            value={actionFilter}
            onChange={(e) => {
              setActionFilter(e.target.value);
            }}
            className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface)] px-3 py-1.5 text-sm text-[color:var(--text)]"
          >
            <option value="">All actions</option>
            {availableActions.map((a) => (
              <option key={a} value={a}>
                {formatAction(a)}
              </option>
            ))}
          </select>
          <span className="ml-auto text-xs text-[color:var(--text-muted)]">
            {total} event{total !== 1 ? "s" : ""}
          </span>
        </div>

        {/* Table */}
        <div className="rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] overflow-hidden">
          {loading && entries.length === 0 ? (
            <div className="p-8 text-center text-sm text-[color:var(--text-muted)]">
              Loading...
            </div>
          ) : entries.length === 0 ? (
            <div className="p-8 text-center text-sm text-[color:var(--text-muted)]">
              <Shield className="h-8 w-8 mx-auto mb-2 opacity-30" />
              No audit events yet
            </div>
          ) : (
            <div className="divide-y divide-[color:var(--border)]">
              {entries.map((entry) => {
                const Icon = ACTION_ICONS[entry.action] ?? Shield;
                const colorClass =
                  ACTION_COLORS[entry.action] ??
                  "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300";
                const hasDetails =
                  entry.details && Object.keys(entry.details).length > 0;

                return (
                  <div
                    key={entry.id}
                    className="flex items-start gap-4 px-5 py-4 hover:bg-[color:var(--surface-muted)] transition"
                  >
                    <div
                      className={`mt-0.5 rounded-lg p-2 ${colorClass}`}
                    >
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-[color:var(--text)]">
                          {formatAction(entry.action)}
                        </span>
                        {entry.resource_type && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-[color:var(--surface-muted)] text-[color:var(--text-muted)]">
                            {entry.resource_type}
                          </span>
                        )}
                      </div>
                      {hasDetails && (
                        <p className="text-xs text-[color:var(--text-muted)] mt-1">
                          {formatDetails(entry.details)}
                        </p>
                      )}
                      <div className="flex items-center gap-3 mt-1.5 text-[11px] text-[color:var(--text-quiet)]">
                        {entry.user_name && (
                          <span>{entry.user_name}</span>
                        )}
                        <span>{timeAgo(entry.created_at)}</span>
                        <span
                          className="hidden sm:inline"
                          title={new Date(entry.created_at).toLocaleString()}
                        >
                          {new Date(entry.created_at).toLocaleString()}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between">
            <button
              onClick={() => loadAudit(offset - PAGE_SIZE)}
              disabled={offset === 0 || loading}
              className="flex items-center gap-1 rounded-lg border border-[color:var(--border)] px-3 py-1.5 text-sm text-[color:var(--text-muted)] hover:bg-[color:var(--surface-muted)] disabled:opacity-40 transition"
            >
              <ChevronLeft className="h-4 w-4" /> Previous
            </button>
            <span className="text-xs text-[color:var(--text-muted)]">
              Page {currentPage} of {totalPages}
            </span>
            <button
              onClick={() => loadAudit(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= total || loading}
              className="flex items-center gap-1 rounded-lg border border-[color:var(--border)] px-3 py-1.5 text-sm text-[color:var(--text-muted)] hover:bg-[color:var(--surface-muted)] disabled:opacity-40 transition"
            >
              Next <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
    </DashboardPageLayout>
  );
}
