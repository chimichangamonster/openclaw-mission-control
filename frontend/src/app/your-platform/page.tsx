"use client";

export const dynamic = "force-dynamic";

import { CheckCircle2, ShieldCheck, Sparkles, Lock } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/auth/clerk";
import { customFetch } from "@/api/mutator";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
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

type CapabilityOverview = {
  org: { id: string; name: string; slug: string | null };
  agents: CapabilityAgent[];
  crons: { reachable: boolean; jobs: CapabilityCron[] };
  integrations: CapabilityIntegration[];
  industry_template: CapabilityTemplate;
  capabilities: { label: string; description: string }[];
  trust_posture: {
    human_approval: string[];
    boundaries: string[];
    data_protection: string[];
  };
};

function TrustGroup({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="mb-2 text-sm font-semibold text-[color:var(--text)]">{title}</p>
      <ul className="space-y-1.5">
        {items.map((line) => (
          <li key={line} className="flex items-start gap-2 text-sm text-[color:var(--text-muted)]">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
            <span>{line}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function YourPlatformPage() {
  const { isSignedIn } = useAuth();

  const query = useQuery<CapabilityOverview>({
    queryKey: ["/api/v1/organizations/me/capability-overview"],
    queryFn: async () => {
      const res = (await customFetch("/api/v1/organizations/me/capability-overview", {
        method: "GET",
      })) as { data?: CapabilityOverview } | CapabilityOverview;
      return ("data" in res ? res.data : res) as CapabilityOverview;
    },
    enabled: Boolean(isSignedIn),
    retry: false,
  });

  const data = query.data;

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to view your platform overview.",
        forceRedirectUrl: "/your-platform",
      }}
      title="Your Platform"
      description="A read-only overview of what your AI assistant can do for your organization — and the safeguards around it."
    >
      {query.isError ? (
        <Card className="text-sm text-rose-700">Failed to load your platform overview.</Card>
      ) : !data ? (
        <Card className="text-sm text-[color:var(--text-muted)]">Loading…</Card>
      ) : (
        <div className="space-y-8">
          {data.industry_template ? (
            <div>
              <TemplateBadge template={data.industry_template} />
            </div>
          ) : null}

          {/* Capabilities — friendly, flag-derived */}
          <section>
            <SectionHeader icon={Sparkles} title="What your platform can do" count={data.capabilities.length} />
            {data.capabilities.length === 0 ? (
              <Card className="text-sm text-[color:var(--text-muted)]">
                No capabilities enabled yet.
              </Card>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {data.capabilities.map((cap) => (
                  <Card key={cap.label}>
                    <p className="font-medium text-[color:var(--text)]">{cap.label}</p>
                    <p className="mt-0.5 text-sm text-[color:var(--text-muted)]">{cap.description}</p>
                  </Card>
                ))}
              </div>
            )}
          </section>

          <AgentsSection agents={data.agents} />

          <CronsSection crons={data.crons} />

          <IntegrationsSection integrations={data.integrations} showDetail={false} />

          {/* Trust posture — the trust-engineered constraints made visible */}
          <section>
            <div className="mb-3 flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-emerald-600" />
              <h2 className="font-heading text-lg font-semibold text-[color:var(--text)]">
                What your AI can and cannot do
              </h2>
            </div>
            <Card className="space-y-5">
              <TrustGroup title="Human stays in control" items={data.trust_posture.human_approval} />
              <TrustGroup title="Hard boundaries" items={data.trust_posture.boundaries} />
              <TrustGroup title="Your data is protected" items={data.trust_posture.data_protection} />
            </Card>
          </section>

          <p className="flex items-center gap-1.5 text-xs text-[color:var(--text-muted)]">
            <Lock className="h-3.5 w-3.5" />
            This page is read-only. Configuration is managed by your platform administrator.
          </p>
        </div>
      )}
    </DashboardPageLayout>
  );
}
