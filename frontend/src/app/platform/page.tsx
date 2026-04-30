"use client";

export const dynamic = "force-dynamic";

import Link from "next/link";
import { AlertTriangle, CheckCircle2, ExternalLink, RefreshCw } from "lucide-react";
import { useQueries, useQuery } from "@tanstack/react-query";

import { useAuth } from "@/auth/clerk";
import { customFetch } from "@/api/mutator";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Button } from "@/components/ui/button";
import { usePlatformRole } from "@/lib/use-platform-role";

type PlatformOrg = {
  id: string;
  name: string;
  slug: string | null;
  member_count: number;
  feature_flags: Record<string, boolean>;
  timezone: string | null;
  created_at: string | null;
};

type ReadinessCheck = {
  check: string;
  passed: boolean;
  detail: string;
};

type Readiness = {
  org: string;
  slug: string | null;
  passed: number;
  total: number;
  ready: boolean;
  checks: ReadinessCheck[];
};

type PlatformGateway = {
  id: string;
  url: string;
  name: string | null;
  connected: boolean;
};

type GatewayHealthResponse = {
  org: string;
  gateways: PlatformGateway[];
};

const READINESS_LABELS: Record<string, string> = {
  org_settings_exist: "Org settings exist",
  feature_flags_set: "Feature flags configured",
  llm_access: "LLM access configured",
  gateway_connected: "Gateway connected",
  members_exist: "Members exist",
  has_owner: "At least one owner",
  budget_configured: "Budget configured",
  industry_template: "Industry template applied",
  slug_set: "Slug set",
  timezone_set: "Timezone set",
};

export default function PlatformOwnerPage() {
  const { isSignedIn } = useAuth();
  const { isPlatformOwner, isLoading: isPlatformRoleLoading } =
    usePlatformRole(isSignedIn);

  const orgsQuery = useQuery<PlatformOrg[]>({
    queryKey: ["/api/v1/platform/orgs"],
    queryFn: async () => {
      const res = (await customFetch("/api/v1/platform/orgs", {
        method: "GET",
      })) as { data?: PlatformOrg[] } | PlatformOrg[];
      return Array.isArray(res) ? res : (res?.data ?? []);
    },
    enabled: Boolean(isSignedIn) && isPlatformOwner,
    refetchOnMount: "always",
    retry: false,
  });

  const orgs = orgsQuery.data ?? [];

  const readinessQueries = useQueries({
    queries: orgs.map((org) => ({
      queryKey: ["/api/v1/platform/orgs", org.id, "readiness"],
      queryFn: async () => {
        const res = (await customFetch(
          `/api/v1/platform/orgs/${org.id}/readiness`,
          { method: "GET" },
        )) as { data?: Readiness } | Readiness;
        return ("data" in res ? res.data : res) as Readiness;
      },
      enabled: Boolean(isSignedIn) && isPlatformOwner,
      refetchOnMount: "always" as const,
      retry: false,
    })),
  });

  const healthQueries = useQueries({
    queries: orgs.map((org) => ({
      queryKey: ["/api/v1/platform/orgs", org.id, "health"],
      queryFn: async () => {
        const res = (await customFetch(
          `/api/v1/platform/orgs/${org.id}/health`,
          { method: "GET" },
        )) as { data?: GatewayHealthResponse } | GatewayHealthResponse;
        return ("data" in res ? res.data : res) as GatewayHealthResponse;
      },
      enabled: Boolean(isSignedIn) && isPlatformOwner,
      refetchOnMount: "always" as const,
      retry: false,
    })),
  });

  const refetchAll = () => {
    void orgsQuery.refetch();
    readinessQueries.forEach((q) => void q.refetch());
    healthQueries.forEach((q) => void q.refetch());
  };

  const attentionRows = orgs
    .map((org, idx) => {
      const r = readinessQueries[idx]?.data;
      if (!r) return null;
      const failing = r.checks.filter((c) => !c.passed);
      if (failing.length === 0) return null;
      return { org, failing };
    })
    .filter((row): row is { org: PlatformOrg; failing: ReadinessCheck[] } =>
      Boolean(row),
    );

  const totalOrgs = orgs.length;
  const readyOrgs = readinessQueries.filter((q) => q.data?.ready).length;
  const attentionCount = attentionRows.length;
  const isLoading =
    isPlatformRoleLoading ||
    orgsQuery.isLoading ||
    readinessQueries.some((q) => q.isLoading);

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to access platform owner tools.",
        forceRedirectUrl: "/platform",
      }}
      title="Platform Owner"
      description="Cross-organization fleet view — orgs, readiness, gateway health, and audit."
      isAdmin={isPlatformOwner}
      adminOnlyMessage="This page is only available to platform owners."
      headerActions={
        <Button onClick={refetchAll} variant="outline" disabled={isLoading}>
          <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      }
    >
      <div className="space-y-8">
        {/* Stat strip */}
        <div className="grid gap-3 sm:grid-cols-3">
          <StatCard label="Organizations" value={String(totalOrgs)} />
          <StatCard
            label="Ready"
            value={`${readyOrgs} / ${totalOrgs || 0}`}
            tone={readyOrgs === totalOrgs ? "ok" : "warn"}
          />
          <StatCard
            label="Need attention"
            value={String(attentionCount)}
            tone={attentionCount === 0 ? "ok" : "warn"}
          />
        </div>

        {/* Needs attention panel */}
        <section>
          <div className="mb-3 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-500" />
            <h2 className="font-heading text-lg font-semibold text-[color:var(--text)]">
              Needs attention
            </h2>
          </div>
          {orgsQuery.isError ? (
            <ErrorPanel message="Failed to load organizations." />
          ) : attentionRows.length === 0 && !isLoading ? (
            <div className="rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] p-4 text-sm text-[color:var(--text-muted)]">
              All orgs pass their readiness checks.
            </div>
          ) : (
            <div className="space-y-3">
              {attentionRows.map(({ org, failing }) => (
                <div
                  key={org.id}
                  className="rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] p-4"
                >
                  <div className="mb-2 flex items-center justify-between">
                    <div className="font-semibold text-[color:var(--text)]">
                      {org.name}
                      {org.slug ? (
                        <span className="ml-2 text-xs text-[color:var(--text-muted)]">
                          {org.slug}
                        </span>
                      ) : null}
                    </div>
                    <span className="text-xs text-amber-700">
                      {failing.length} failing
                    </span>
                  </div>
                  <ul className="space-y-1 text-sm">
                    {failing.map((check) => (
                      <li
                        key={check.check}
                        className="flex items-start gap-2 text-[color:var(--text-muted)]"
                      >
                        <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                        <span>
                          <span className="font-medium text-[color:var(--text)]">
                            {READINESS_LABELS[check.check] ?? check.check}
                          </span>
                          {check.detail ? (
                            <span className="text-[color:var(--text-muted)]">
                              {" "}
                              — {check.detail}
                            </span>
                          ) : null}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Org table */}
        <section>
          <h2 className="mb-3 font-heading text-lg font-semibold text-[color:var(--text)]">
            All organizations
          </h2>
          <div className="overflow-x-auto rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)]">
            <table className="w-full text-sm">
              <thead className="border-b border-[color:var(--border)] text-left text-xs uppercase tracking-wider text-[color:var(--text-muted)]">
                <tr>
                  <th className="px-4 py-2 font-semibold">Name</th>
                  <th className="px-4 py-2 font-semibold">Slug</th>
                  <th className="px-4 py-2 font-semibold">Members</th>
                  <th className="px-4 py-2 font-semibold">Readiness</th>
                  <th className="px-4 py-2 font-semibold">Gateways</th>
                  <th className="px-4 py-2 font-semibold">Created</th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {orgs.map((org, idx) => {
                  const r = readinessQueries[idx]?.data;
                  const h = healthQueries[idx]?.data;
                  const gatewayCount = h?.gateways?.length ?? 0;
                  return (
                    <tr
                      key={org.id}
                      className="border-b border-[color:var(--border)] last:border-0"
                    >
                      <td className="px-4 py-3 font-medium text-[color:var(--text)]">
                        {org.name}
                      </td>
                      <td className="px-4 py-3 text-[color:var(--text-muted)]">
                        {org.slug ?? "—"}
                      </td>
                      <td className="px-4 py-3 text-[color:var(--text-muted)]">
                        {org.member_count}
                      </td>
                      <td className="px-4 py-3">
                        {r ? (
                          <span
                            className={
                              r.ready
                                ? "inline-flex items-center gap-1 text-emerald-700"
                                : "inline-flex items-center gap-1 text-amber-700"
                            }
                          >
                            {r.ready ? (
                              <CheckCircle2 className="h-3.5 w-3.5" />
                            ) : (
                              <AlertTriangle className="h-3.5 w-3.5" />
                            )}
                            {r.passed} / {r.total}
                          </span>
                        ) : (
                          <span className="text-[color:var(--text-muted)]">…</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-[color:var(--text-muted)]">
                        {gatewayCount}
                      </td>
                      <td className="px-4 py-3 text-[color:var(--text-muted)]">
                        {org.created_at
                          ? new Date(org.created_at).toLocaleDateString()
                          : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <Link
                          href={`/platform/orgs/${org.id}`}
                          className="inline-flex items-center gap-1 text-xs font-semibold text-[color:var(--accent-strong)] hover:underline"
                        >
                          Detail
                          <ExternalLink className="h-3 w-3" />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
                {orgs.length === 0 && !orgsQuery.isLoading ? (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-4 py-6 text-center text-[color:var(--text-muted)]"
                    >
                      No organizations.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>

        {/* Notes */}
        <section className="rounded-xl border border-dashed border-[color:var(--border)] bg-[color:var(--surface-muted)] p-4 text-sm text-[color:var(--text-muted)]">
          <p className="mb-2 font-semibold text-[color:var(--text)]">
            Coming next
          </p>
          <ul className="list-inside list-disc space-y-1">
            <li>Cross-org failed-cron rollup (last 24h)</li>
            <li>Cross-org audit feed (owner-only)</li>
            <li>Per-org budget burn and circuit-breaker status</li>
            <li>Backup health and Loki ingestion alerts</li>
          </ul>
        </section>
      </div>
    </DashboardPageLayout>
  );
}

function StatCard({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "ok" | "warn";
}) {
  const toneClass =
    tone === "ok"
      ? "text-emerald-700"
      : tone === "warn"
        ? "text-amber-700"
        : "text-[color:var(--text)]";
  return (
    <div className="rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] p-4">
      <div className="text-xs uppercase tracking-wider text-[color:var(--text-muted)]">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-semibold ${toneClass}`}>{value}</div>
    </div>
  );
}

function ErrorPanel({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-rose-300 bg-rose-50 p-4 text-sm text-rose-800">
      {message}
    </div>
  );
}
