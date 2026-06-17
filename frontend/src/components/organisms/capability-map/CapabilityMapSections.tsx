"use client";

import Link from "next/link";
import {
  ArrowUpRight,
  Bot,
  Clock,
  Plug,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";

// Shared types — the capability-map composite (items 144 + 145). The redacted
// (client) shape is a strict subset of the full (owner) shape.
export type CapabilityAgent = {
  name: string;
  role: string | null;
  status: string;
  is_lead: boolean;
};

export type CapabilityCron = {
  name: string;
  schedule: string | null;
  enabled: boolean;
  last_status?: string | null;
};

export type CapabilityIntegration = {
  type: string;
  provider: string;
  connected: boolean;
  address?: string;
  visibility?: string;
  agent_access?: string;
  label?: string;
};

export type CapabilityTemplate = { id: string; name: string } | null;

const INTEGRATION_LABELS: Record<string, string> = {
  email: "Email",
  microsoft_graph: "Microsoft 365",
  google_calendar: "Google Calendar",
  wecom: "WeCom / WeChat",
};

const PROVIDER_LABELS: Record<string, string> = {
  microsoft: "Microsoft",
  google: "Google",
  zoho: "Zoho",
  wecom: "WeCom",
};

export function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] p-4",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function SectionHeader({
  icon: Icon,
  title,
  count,
  href,
  linkLabel,
}: {
  icon: LucideIcon;
  title: string;
  count?: number | string;
  href?: string;
  linkLabel?: string;
}) {
  return (
    <div className="mb-3 flex items-end justify-between">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-[color:var(--text-muted)]" />
        <h2 className="font-heading text-lg font-semibold text-[color:var(--text)]">{title}</h2>
        {count !== undefined ? (
          <span className="rounded-full bg-[color:var(--surface-muted)] px-2 py-0.5 text-xs text-[color:var(--text-muted)]">
            {count}
          </span>
        ) : null}
      </div>
      {href ? (
        <Link
          href={href}
          className="flex items-center gap-1 text-sm text-[color:var(--accent-strong)] hover:underline"
        >
          {linkLabel ?? "Manage"}
          <ArrowUpRight className="h-3.5 w-3.5" />
        </Link>
      ) : null}
    </div>
  );
}

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      aria-hidden
      className={cn("inline-block h-2 w-2 rounded-full", ok ? "bg-emerald-500" : "bg-slate-400")}
    />
  );
}

export function AgentsSection({ agents }: { agents: CapabilityAgent[] }) {
  return (
    <section>
      <SectionHeader icon={Bot} title="Agents" count={agents.length} />
      {agents.length === 0 ? (
        <Card className="text-sm text-[color:var(--text-muted)]">No agents provisioned.</Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {agents.map((a) => (
            <Card key={a.name} className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate font-medium text-[color:var(--text)]">{a.name}</span>
                  {a.is_lead ? (
                    <span className="shrink-0 rounded-full bg-[color:var(--accent-soft)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[color:var(--accent-strong)]">
                      Lead
                    </span>
                  ) : null}
                </div>
                {a.role ? (
                  <p className="mt-0.5 text-sm text-[color:var(--text-muted)]">{a.role}</p>
                ) : null}
              </div>
              <span className="shrink-0 text-xs text-[color:var(--text-muted)]">{a.status}</span>
            </Card>
          ))}
        </div>
      )}
    </section>
  );
}

export function CronsSection({
  crons,
  href,
}: {
  crons: { reachable: boolean; jobs: CapabilityCron[] };
  href?: string;
}) {
  return (
    <section>
      <SectionHeader
        icon={Clock}
        title="Scheduled tasks"
        count={crons.reachable ? crons.jobs.length : undefined}
        href={href}
        linkLabel="Manage schedules"
      />
      {!crons.reachable ? (
        <Card className="text-sm text-[color:var(--text-muted)]">
          Schedule list is temporarily unavailable.
        </Card>
      ) : crons.jobs.length === 0 ? (
        <Card className="text-sm text-[color:var(--text-muted)]">Nothing scheduled.</Card>
      ) : (
        <Card className="divide-y divide-[color:var(--border)] p-0">
          {crons.jobs.map((job, i) => (
            <div key={`${job.name}-${i}`} className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="flex min-w-0 items-center gap-2">
                <StatusDot ok={job.enabled} />
                <span className="truncate text-sm text-[color:var(--text)]">{job.name}</span>
                {!job.enabled ? (
                  <span className="shrink-0 text-[10px] uppercase tracking-wide text-[color:var(--text-muted)]">
                    paused
                  </span>
                ) : null}
              </div>
              <div className="flex shrink-0 items-center gap-3">
                {job.schedule ? (
                  <code className="text-xs text-[color:var(--text-muted)]">{job.schedule}</code>
                ) : null}
                {job.last_status ? (
                  <span
                    className={cn(
                      "text-xs",
                      job.last_status === "error" || job.last_status === "failed"
                        ? "text-rose-600"
                        : "text-emerald-600",
                    )}
                  >
                    {job.last_status}
                  </span>
                ) : null}
              </div>
            </div>
          ))}
        </Card>
      )}
    </section>
  );
}

export function IntegrationsSection({
  integrations,
  href,
  showDetail,
}: {
  integrations: CapabilityIntegration[];
  href?: string;
  showDetail: boolean;
}) {
  return (
    <section>
      <SectionHeader
        icon={Plug}
        title="Connected services"
        count={integrations.length}
        href={href}
        linkLabel="Manage connections"
      />
      {integrations.length === 0 ? (
        <Card className="text-sm text-[color:var(--text-muted)]">No services connected.</Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {integrations.map((integ, i) => (
            <Card key={`${integ.type}-${i}`} className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <StatusDot ok={integ.connected} />
                  <span className="font-medium text-[color:var(--text)]">
                    {INTEGRATION_LABELS[integ.type] ?? integ.type}
                  </span>
                </div>
                <p className="mt-0.5 text-sm text-[color:var(--text-muted)]">
                  {PROVIDER_LABELS[integ.provider] ?? integ.provider}
                  {showDetail && integ.address ? ` · ${integ.address}` : ""}
                </p>
                {showDetail && integ.visibility ? (
                  <p className="mt-0.5 text-xs text-[color:var(--text-muted)]">
                    {integ.visibility}
                    {integ.agent_access ? ` · agent ${integ.agent_access}` : ""}
                  </p>
                ) : null}
              </div>
              <span className="shrink-0 text-xs text-[color:var(--text-muted)]">
                {integ.connected ? "Connected" : "Inactive"}
              </span>
            </Card>
          ))}
        </div>
      )}
    </section>
  );
}

export function TemplateBadge({ template }: { template: CapabilityTemplate }) {
  if (!template) return null;
  return (
    <span className="rounded-full border border-[color:var(--border)] bg-[color:var(--surface-muted)] px-3 py-1 text-sm text-[color:var(--text-muted)]">
      Industry template: <span className="text-[color:var(--text)]">{template.name}</span>
    </span>
  );
}
