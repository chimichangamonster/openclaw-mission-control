"use client";

export const dynamic = "force-dynamic";

import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  RefreshCw,
  XCircle,
} from "lucide-react";
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

type CronFailure = {
  cron_id: string;
  cron_name: string;
  run_id: string;
  started_at: string | null;
  duration_ms: number | null;
  error_summary: string;
};

type CronFailuresOrg = {
  org_id: string;
  org_name: string;
  slug: string | null;
  failure_count: number;
  failures: CronFailure[];
};

type CronFailuresRollup = {
  hours: number;
  since: string;
  total_failures: number;
  orgs_with_failures: number;
  orgs_with_rpc_error: number;
  by_org: CronFailuresOrg[];
};

type SkillDriftSource = {
  path: string | null;
  available: boolean;
};

type SkillDriftResponse = {
  available: boolean;
  total_drift: number;
  total_orphan: number;
  sources: {
    registry: SkillDriftSource & { shared_skill_count: number; org_count: number };
    shared_skills_dir: SkillDriftSource & { skill_count: number };
    workspaces_dir: SkillDriftSource & { gateway_count: number };
  };
};

type InfraStatus = "healthy" | "stale" | "amber" | "missing" | "red" | "error";

type BackupHealth = {
  status: InfraStatus;
  newest_backup?: string;
  newest_backup_at?: string;
  age_hours?: number;
  size_bytes?: number;
  has_checksum?: boolean;
  backup_count?: number;
  message?: string;
  backup_dir?: string;
};

type LokiHealth = {
  status: InfraStatus;
  last_event_at: string | null;
  last_event_age_seconds: number | null;
  events_24h: number;
  message?: string;
};

type ClickHouseTable = {
  database: string;
  table: string;
  bytes: number;
  rows: number;
};

type ClickHouseHealth = {
  status: InfraStatus;
  total_bytes: number;
  table_count?: number;
  tables: ClickHouseTable[];
  reason?: string | null;
  message?: string;
};

type InfraHealthResponse = {
  overall_status: InfraStatus;
  backup: BackupHealth;
  loki: LokiHealth;
  clickhouse: ClickHouseHealth;
  checked_at: string;
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

  const cronFailuresQuery = useQuery<CronFailuresRollup>({
    queryKey: ["/api/v1/platform/cron-failures", { hours: 24 }],
    queryFn: async () => {
      const res = (await customFetch("/api/v1/platform/cron-failures?hours=24", {
        method: "GET",
      })) as { data?: CronFailuresRollup } | CronFailuresRollup;
      return ("data" in res ? res.data : res) as CronFailuresRollup;
    },
    enabled: Boolean(isSignedIn) && isPlatformOwner,
    refetchOnMount: "always",
    retry: false,
  });

  const skillDriftQuery = useQuery<SkillDriftResponse>({
    queryKey: ["/api/v1/platform/skill-drift"],
    queryFn: async () => {
      const res = (await customFetch("/api/v1/platform/skill-drift", {
        method: "GET",
      })) as { data?: SkillDriftResponse } | SkillDriftResponse;
      return ("data" in res ? res.data : res) as SkillDriftResponse;
    },
    enabled: Boolean(isSignedIn) && isPlatformOwner,
    refetchOnMount: "always",
    retry: false,
  });

  const infraHealthQuery = useQuery<InfraHealthResponse>({
    queryKey: ["/api/v1/platform/infra-health"],
    queryFn: async () => {
      const res = (await customFetch("/api/v1/platform/infra-health", {
        method: "GET",
      })) as { data?: InfraHealthResponse } | InfraHealthResponse;
      return ("data" in res ? res.data : res) as InfraHealthResponse;
    },
    enabled: Boolean(isSignedIn) && isPlatformOwner,
    refetchOnMount: "always",
    retry: false,
  });

  const refetchAll = () => {
    void orgsQuery.refetch();
    readinessQueries.forEach((q) => void q.refetch());
    healthQueries.forEach((q) => void q.refetch());
    void cronFailuresQuery.refetch();
    void skillDriftQuery.refetch();
    void infraHealthQuery.refetch();
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
  const cronFailures = cronFailuresQuery.data;
  const totalCronFailures = cronFailures?.total_failures ?? 0;
  const skillDrift = skillDriftQuery.data;
  const skillDriftIssues =
    (skillDrift?.total_drift ?? 0) + (skillDrift?.total_orphan ?? 0);
  const skillDriftAvailable = skillDrift?.available ?? false;
  const isLoading =
    isPlatformRoleLoading ||
    orgsQuery.isLoading ||
    readinessQueries.some((q) => q.isLoading) ||
    cronFailuresQuery.isLoading;

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
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
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
          <StatCard
            label="Failed crons (24h)"
            value={String(totalCronFailures)}
            tone={totalCronFailures === 0 ? "ok" : "warn"}
          />
          <StatCard
            label="Skill drift"
            value={
              skillDriftAvailable
                ? `${skillDrift?.total_drift ?? 0} / ${skillDrift?.total_orphan ?? 0}`
                : "—"
            }
            tone={
              !skillDriftAvailable
                ? "neutral"
                : skillDriftIssues === 0
                  ? "ok"
                  : "warn"
            }
            sublabel={skillDriftAvailable ? "drift / orphan" : "audit unavailable"}
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

        {/* Failed crons (24h) panel */}
        <section>
          <div className="mb-3 flex items-center gap-2">
            <XCircle className="h-4 w-4 text-rose-500" />
            <h2 className="font-heading text-lg font-semibold text-[color:var(--text)]">
              Failed crons (last 24h)
            </h2>
            {cronFailures && cronFailures.orgs_with_rpc_error > 0 ? (
              <span className="text-xs text-amber-700">
                {cronFailures.orgs_with_rpc_error} org(s) unreachable —
                results may be incomplete
              </span>
            ) : null}
          </div>
          {cronFailuresQuery.isError ? (
            <ErrorPanel message="Failed to load cron failures." />
          ) : !cronFailures && cronFailuresQuery.isLoading ? (
            <div className="rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] p-4 text-sm text-[color:var(--text-muted)]">
              Loading…
            </div>
          ) : !cronFailures || cronFailures.by_org.length === 0 ? (
            <div className="rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] p-4 text-sm text-emerald-700">
              No cron failures in the last 24 hours.
            </div>
          ) : (
            <div className="space-y-3">
              {cronFailures.by_org.map((orgFailures) => (
                <div
                  key={orgFailures.org_id}
                  className="rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] p-4"
                >
                  <div className="mb-2 flex items-center justify-between">
                    <div className="font-semibold text-[color:var(--text)]">
                      {orgFailures.org_name}
                      {orgFailures.slug ? (
                        <span className="ml-2 text-xs text-[color:var(--text-muted)]">
                          {orgFailures.slug}
                        </span>
                      ) : null}
                    </div>
                    <span className="text-xs text-rose-700">
                      {orgFailures.failure_count} failure
                      {orgFailures.failure_count === 1 ? "" : "s"}
                    </span>
                  </div>
                  <ul className="space-y-1.5 text-sm">
                    {orgFailures.failures.slice(0, 5).map((failure) => (
                      <li
                        key={failure.run_id || `${failure.cron_id}-${failure.started_at}`}
                        className="flex flex-wrap items-baseline gap-2"
                      >
                        <span className="h-1.5 w-1.5 shrink-0 self-center rounded-full bg-rose-500" />
                        <span className="font-medium text-[color:var(--text)]">
                          {failure.cron_name || failure.cron_id}
                        </span>
                        <span className="text-xs text-[color:var(--text-muted)]">
                          {failure.started_at
                            ? new Date(failure.started_at).toLocaleString()
                            : "—"}
                        </span>
                        {failure.error_summary ? (
                          <span className="min-w-0 flex-1 truncate text-xs text-rose-600">
                            {failure.error_summary}
                          </span>
                        ) : null}
                      </li>
                    ))}
                    {orgFailures.failures.length > 5 ? (
                      <li className="pl-3.5 text-xs text-[color:var(--text-muted)]">
                        +{orgFailures.failures.length - 5} older failure
                        {orgFailures.failures.length - 5 === 1 ? "" : "s"}
                      </li>
                    ) : null}
                  </ul>
                  {orgFailures.slug ? (
                    <Link
                      href={`/cron-jobs?org_slug=${orgFailures.slug}`}
                      className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-[color:var(--accent-strong)] hover:underline"
                    >
                      View cron jobs
                      <ExternalLink className="h-3 w-3" />
                    </Link>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Infrastructure health (item 123) */}
        <section>
          <div className="mb-3 flex items-center gap-2">
            <CheckCircle2
              className={`h-4 w-4 ${infraToneIcon(infraHealthQuery.data?.overall_status)}`}
            />
            <h2 className="font-heading text-lg font-semibold text-[color:var(--text)]">
              Infrastructure health
            </h2>
            {infraHealthQuery.data ? (
              <span className="text-xs text-[color:var(--text-muted)]">
                checked{" "}
                {new Date(infraHealthQuery.data.checked_at).toLocaleTimeString()}
              </span>
            ) : null}
          </div>
          {infraHealthQuery.isError ? (
            <ErrorPanel message="Failed to load infrastructure health." />
          ) : !infraHealthQuery.data && infraHealthQuery.isLoading ? (
            <div className="rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] p-4 text-sm text-[color:var(--text-muted)]">
              Loading…
            </div>
          ) : infraHealthQuery.data ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <InfraCard
                title="Backup"
                status={infraHealthQuery.data.backup.status}
                primary={
                  infraHealthQuery.data.backup.age_hours !== undefined
                    ? `${infraHealthQuery.data.backup.age_hours}h ago`
                    : infraHealthQuery.data.backup.message ?? "—"
                }
                detail={
                  infraHealthQuery.data.backup.newest_backup
                    ? `${infraHealthQuery.data.backup.newest_backup} • ${formatBytes(
                        infraHealthQuery.data.backup.size_bytes ?? 0,
                      )}${
                        infraHealthQuery.data.backup.has_checksum === false
                          ? " • no checksum"
                          : ""
                      }`
                    : undefined
                }
              />
              <InfraCard
                title="Loki ingestion"
                status={infraHealthQuery.data.loki.status}
                primary={
                  infraHealthQuery.data.loki.last_event_age_seconds !== null
                    ? `${formatAge(
                        infraHealthQuery.data.loki.last_event_age_seconds,
                      )} ago`
                    : infraHealthQuery.data.loki.message ?? "no events"
                }
                detail={`${infraHealthQuery.data.loki.events_24h.toLocaleString()} events / 24h`}
              />
              <InfraCard
                title="ClickHouse storage"
                status={infraHealthQuery.data.clickhouse.status}
                primary={formatBytes(infraHealthQuery.data.clickhouse.total_bytes)}
                detail={
                  infraHealthQuery.data.clickhouse.reason ??
                  (infraHealthQuery.data.clickhouse.tables[0]
                    ? `largest: ${infraHealthQuery.data.clickhouse.tables[0].database}.${infraHealthQuery.data.clickhouse.tables[0].table} (${formatBytes(
                        infraHealthQuery.data.clickhouse.tables[0].bytes,
                      )})`
                    : "no active parts")
                }
              />
            </div>
          ) : null}
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
            <li>Skill-drift detail page (item 120 Tier 2 — Tier 1 stat card shipped)</li>
            <li>Per-org budget burn and circuit-breaker status (item 122)</li>
            <li>Cross-org audit feed (owner-only, item 124 — gated on 2nd platform-admin user)</li>
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
  sublabel,
}: {
  label: string;
  value: string;
  tone?: "neutral" | "ok" | "warn";
  sublabel?: string;
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
      {sublabel ? (
        <div className="mt-0.5 text-[10px] uppercase tracking-wider text-[color:var(--text-muted)]">
          {sublabel}
        </div>
      ) : null}
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

function InfraCard({
  title,
  status,
  primary,
  detail,
}: {
  title: string;
  status: InfraStatus;
  primary: string;
  detail?: string;
}) {
  const accent =
    status === "healthy"
      ? "border-emerald-300"
      : status === "stale" || status === "amber"
        ? "border-amber-300"
        : status === "missing" || status === "red" || status === "error"
          ? "border-rose-300"
          : "border-[color:var(--border)]";
  const tone =
    status === "healthy"
      ? "text-emerald-700"
      : status === "stale" || status === "amber"
        ? "text-amber-700"
        : status === "missing" || status === "red" || status === "error"
          ? "text-rose-700"
          : "text-[color:var(--text)]";
  return (
    <div
      className={`rounded-xl border ${accent} bg-[color:var(--surface)] p-4`}
    >
      <div className="flex items-baseline justify-between">
        <div className="text-xs uppercase tracking-wider text-[color:var(--text-muted)]">
          {title}
        </div>
        <div className={`text-xs font-semibold uppercase ${tone}`}>{status}</div>
      </div>
      <div className={`mt-1 text-xl font-semibold ${tone}`}>{primary}</div>
      {detail ? (
        <div className="mt-1 text-xs text-[color:var(--text-muted)]">
          {detail}
        </div>
      ) : null}
    </div>
  );
}

function infraToneIcon(status: InfraStatus | undefined): string {
  if (!status) return "text-[color:var(--text-muted)]";
  if (status === "healthy") return "text-emerald-500";
  if (status === "stale" || status === "amber") return "text-amber-500";
  return "text-rose-500";
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  const idx = Math.min(
    units.length - 1,
    Math.floor(Math.log(bytes) / Math.log(1024)),
  );
  return `${(bytes / Math.pow(1024, idx)).toFixed(idx === 0 ? 0 : 2)} ${units[idx]}`;
}

function formatAge(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
  return `${(seconds / 86400).toFixed(1)}d`;
}
