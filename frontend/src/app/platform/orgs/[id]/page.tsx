"use client";

export const dynamic = "force-dynamic";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Boxes, FlaskConical, Sparkles } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/auth/clerk";
import { customFetch } from "@/api/mutator";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { usePlatformRole } from "@/lib/use-platform-role";
import {
  AgentsSection,
  Card,
  CronsSection,
  IntegrationsSection,
  SectionHeader,
  TemplateBadge,
  type CapabilityAgent,
  type CapabilityCron,
  type CapabilityIntegration,
  type CapabilityTemplate,
} from "@/components/organisms/capability-map/CapabilityMapSections";

type CapabilityMap = {
  org: { id: string; name: string; slug: string | null };
  agents: CapabilityAgent[];
  crons: { reachable: boolean; jobs: CapabilityCron[] };
  integrations: CapabilityIntegration[];
  industry_template: CapabilityTemplate;
  skills: {
    shared: string[];
    shared_count: number;
    org_specific: string[];
    org_specific_count: number;
    total: number;
  } | null;
  feature_flags: Record<string, boolean>;
};

export default function OrgCapabilityMapPage() {
  const params = useParams<{ id: string }>();
  const orgId = params?.id;
  const { isSignedIn } = useAuth();
  const { isPlatformOwner, isLoading: roleLoading } = usePlatformRole(isSignedIn);

  const mapQuery = useQuery<CapabilityMap>({
    queryKey: ["/api/v1/platform/orgs", orgId, "capability-map"],
    queryFn: async () => {
      const res = (await customFetch(`/api/v1/platform/orgs/${orgId}/capability-map`, {
        method: "GET",
      })) as { data?: CapabilityMap } | CapabilityMap;
      return ("data" in res ? res.data : res) as CapabilityMap;
    },
    enabled: Boolean(isSignedIn) && isPlatformOwner && Boolean(orgId),
    retry: false,
  });

  const data = mapQuery.data;
  const enabledFlags = data
    ? Object.entries(data.feature_flags)
        .filter(([, on]) => on)
        .map(([k]) => k)
        .sort()
    : [];

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to access platform owner tools.",
        forceRedirectUrl: "/platform",
      }}
      title={data ? `${data.org.name} — Capability Map` : "Capability Map"}
      description="Live deployment snapshot — agents, skills, schedules, connections, flags. Read-only; edit via each section's surface."
      isAdmin={!roleLoading ? isPlatformOwner : undefined}
      adminOnlyMessage="This page is only available to platform owners."
      headerActions={
        <Link
          href="/platform"
          className="flex items-center gap-1 text-sm text-[color:var(--text-muted)] hover:underline"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to fleet
        </Link>
      }
    >
      {mapQuery.isError ? (
        <Card className="text-sm text-rose-700">Failed to load the capability map for this org.</Card>
      ) : !data ? (
        <Card className="text-sm text-[color:var(--text-muted)]">Loading capability map…</Card>
      ) : (
        <div className="space-y-8">
          {data.industry_template ? (
            <div>
              <TemplateBadge template={data.industry_template} />
            </div>
          ) : null}

          <AgentsSection agents={data.agents} />

          <CronsSection crons={data.crons} href="/cron-jobs" />

          <IntegrationsSection integrations={data.integrations} href="/org-settings" showDetail />

          {/* Skills — owner-only; the first MC rendering of registry.yml assignment */}
          <section>
            <SectionHeader
              icon={Boxes}
              title="Skills"
              count={data.skills ? data.skills.total : undefined}
              href="/skills"
              linkLabel="Skill library"
            />
            {!data.skills ? (
              <Card className="text-sm text-[color:var(--text-muted)]">
                Skill registry unavailable in this environment.
              </Card>
            ) : (
              <div className="grid gap-3 lg:grid-cols-2">
                <Card>
                  <p className="mb-2 text-sm font-medium text-[color:var(--text)]">
                    Org-specific ({data.skills.org_specific_count})
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {data.skills.org_specific.length === 0 ? (
                      <span className="text-sm text-[color:var(--text-muted)]">None</span>
                    ) : (
                      data.skills.org_specific.map((s) => (
                        <code
                          key={s}
                          className="rounded bg-[color:var(--surface-muted)] px-1.5 py-0.5 text-xs text-[color:var(--text-muted)]"
                        >
                          {s}
                        </code>
                      ))
                    )}
                  </div>
                </Card>
                <Card>
                  <p className="mb-2 text-sm font-medium text-[color:var(--text)]">
                    Shared ({data.skills.shared_count})
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {data.skills.shared.map((s) => (
                      <code
                        key={s}
                        className="rounded bg-[color:var(--surface-muted)] px-1.5 py-0.5 text-xs text-[color:var(--text-muted)]"
                      >
                        {s}
                      </code>
                    ))}
                  </div>
                </Card>
              </div>
            )}
          </section>

          {/* Feature flags */}
          <section>
            <SectionHeader
              icon={FlaskConical}
              title="Feature flags"
              count={`${enabledFlags.length} on`}
              href="/org-settings"
              linkLabel="Edit flags"
            />
            <Card>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(data.feature_flags)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([flag, on]) => (
                    <span
                      key={flag}
                      className={
                        on
                          ? "rounded bg-emerald-50 px-1.5 py-0.5 text-xs text-emerald-700"
                          : "rounded bg-[color:var(--surface-muted)] px-1.5 py-0.5 text-xs text-[color:var(--text-quiet)] line-through"
                      }
                    >
                      {flag}
                    </span>
                  ))}
              </div>
            </Card>
          </section>

          <p className="flex items-center gap-1.5 text-xs text-[color:var(--text-muted)]">
            <Sparkles className="h-3.5 w-3.5" />
            All data is live (DB + gateway RPC + registry). Edits happen on each section&apos;s own
            page.
          </p>
        </div>
      )}
    </DashboardPageLayout>
  );
}
