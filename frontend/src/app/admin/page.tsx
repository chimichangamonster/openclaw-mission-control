"use client";

export const dynamic = "force-dynamic";

import Link from "next/link";
import {
  Activity,
  BarChart3,
  Bot,
  BookOpen,
  Boxes,
  Brain,
  Building2,
  Clock,
  FileBarChart,
  Network,
  Settings,
  Shield,
  Sparkles,
  Store,
} from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { useFeatureFlags } from "@/lib/use-feature-flags";
import { useOrganizationMembership } from "@/lib/use-organization-membership";
import { usePlatformRole } from "@/lib/use-platform-role";

type AdminLink = {
  href: string;
  label: string;
  description: string;
  icon: typeof Settings;
  flag?: string;
};

type AdminGroup = {
  title: string;
  description: string;
  links: AdminLink[];
};

export default function AdminHubPage() {
  const { isSignedIn } = useAuth();
  const { isAdmin } = useOrganizationMembership(isSignedIn);
  const { isFeatureEnabled } = useFeatureFlags(Boolean(isSignedIn));
  const { isPlatformOwner } = usePlatformRole(isSignedIn);

  const groups: AdminGroup[] = [
    {
      title: "Organization",
      description: "Settings, branding, members, and access policies for this org.",
      links: [
        {
          href: "/org-settings",
          label: "Org Settings",
          description: "API keys, feature flags, branding, data policy, model pins.",
          icon: Building2,
        },
        {
          href: "/custom-fields",
          label: "Custom Fields",
          description: "Custom fields shown on boards and tasks.",
          icon: Settings,
        },
      ],
    },
    {
      title: "Agents & Skills",
      description: "Configure the agents and skills running for this org.",
      links: [
        {
          href: "/agents",
          label: "Agents",
          description: "Agent identities, sessions, and assignments.",
          icon: Bot,
        },
        {
          href: "/gateways",
          label: "Gateways",
          description: "Gateway containers and workspace state.",
          icon: Network,
        },
        {
          href: "/skills/marketplace",
          label: "Skill Library",
          description: "Browse and install platform-curated skills.",
          icon: Store,
        },
        {
          href: "/skills/packs",
          label: "Skill Packs",
          description: "Bundles of related skills (legacy installer).",
          icon: Boxes,
        },
      ],
    },
    {
      title: "Memory & Data",
      description: "What the agents read and remember.",
      links: [
        {
          href: "/memory/vector",
          label: "Vector Memory",
          description: "Browse and search semantic memories (pgvector).",
          icon: Brain,
          flag: "agent_memory",
        },
        {
          href: "/org-context",
          label: "Org Context",
          description: "Upload reference files agents can ground on.",
          icon: BookOpen,
          flag: "org_context",
        },
      ],
    },
    {
      title: "Operations",
      description: "Schedules, costs, and traces for this org.",
      links: [
        {
          href: "/cron-jobs",
          label: "Scheduled Tasks",
          description: "Cron jobs, run history, and manual triggers.",
          icon: Clock,
          flag: "cron_jobs",
        },
        {
          href: "/costs",
          label: "Cost & Usage",
          description: "Spend by agent, model, and skill.",
          icon: BarChart3,
          flag: "cost_tracker",
        },
        {
          href: "/observability",
          label: "Observability",
          description: "Langfuse traces, error counts, quality scores.",
          icon: Activity,
          flag: "observability",
        },
        {
          href: "/audit",
          label: "Audit Log",
          description: "Admin actions taken in this org.",
          icon: Shield,
        },
      ],
    },
  ];

  if (isPlatformOwner) {
    groups.push({
      title: "Platform Owner",
      description: "Cross-org views — visible only to platform owners.",
      links: [
        {
          href: "/platform",
          label: "Platform Overview",
          description: "Org list, fleet health, failed crons, cross-org audit.",
          icon: Sparkles,
        },
        {
          href: "/platform/reports",
          label: "Cross-Org Reports",
          description: "Coming soon — fleet-wide diagnostics and export.",
          icon: FileBarChart,
        },
      ],
    });
  }

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to access admin tools.",
        forceRedirectUrl: "/admin",
      }}
      title="Admin"
      description="Configuration and operational surfaces for this organization."
      isAdmin={isAdmin}
      adminOnlyMessage="The admin hub is only available to organization admins and owners."
    >
      <div className="space-y-8">
        {groups.map((group) => {
          const visibleLinks = group.links.filter(
            (link) => !link.flag || isFeatureEnabled(link.flag),
          );
          if (visibleLinks.length === 0) return null;
          return (
            <section key={group.title}>
              <div className="mb-3">
                <h2 className="font-heading text-lg font-semibold text-[color:var(--text)]">
                  {group.title}
                </h2>
                <p className="mt-1 text-sm text-[color:var(--text-muted)]">
                  {group.description}
                </p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {visibleLinks.map((link) => (
                  <Link
                    key={link.href}
                    href={link.href}
                    className="group rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] p-4 transition hover:border-[color:var(--accent-strong)] hover:shadow-sm"
                  >
                    <div className="flex items-start gap-3">
                      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[color:var(--surface-muted)] text-[color:var(--text-muted)] group-hover:text-[color:var(--accent-strong)]">
                        <link.icon className="h-4 w-4" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="font-semibold text-[color:var(--text)]">
                          {link.label}
                        </div>
                        <div className="mt-0.5 text-xs text-[color:var(--text-muted)]">
                          {link.description}
                        </div>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </DashboardPageLayout>
  );
}
