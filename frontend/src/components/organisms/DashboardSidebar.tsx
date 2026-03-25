"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  Radio,
  Bot,
  Boxes,
  CheckCircle2,
  FileText,
  Folder,
  Building2,
  Calendar,
  HelpCircle,
  LayoutGrid,
  Mail,
  MessageSquare,
  Moon,
  Network,
  Sun,
  TrendingUp,
  Settings,
  Shield,
  Store,
  Clock,
  Tags,
  Star,
} from "lucide-react";
import { useTheme } from "next-themes";

import { useAuth } from "@/auth/clerk";
import { ApiError } from "@/api/mutator";
import { useFeatureFlags } from "@/lib/use-feature-flags";
import { useOrganizationMembership } from "@/lib/use-organization-membership";
import {
  type healthzHealthzGetResponse,
  useHealthzHealthzGet,
} from "@/api/generated/default/default";
import { OrgSwitcher } from "@/components/organisms/OrgSwitcher";
import { cn } from "@/lib/utils";

export function DashboardSidebar() {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();
  const { isSignedIn } = useAuth();
  const { isAdmin } = useOrganizationMembership(isSignedIn);
  const { isFeatureEnabled } = useFeatureFlags(Boolean(isSignedIn));
  const healthQuery = useHealthzHealthzGet<healthzHealthzGetResponse, ApiError>(
    {
      query: {
        refetchInterval: 30_000,
        refetchOnMount: "always",
        retry: false,
      },
      request: { cache: "no-store" },
    },
  );

  const okValue = healthQuery.data?.data?.ok;
  const systemStatus: "unknown" | "operational" | "degraded" =
    okValue === true
      ? "operational"
      : okValue === false
        ? "degraded"
        : healthQuery.isError
          ? "degraded"
          : "unknown";
  const statusLabel =
    systemStatus === "operational"
      ? "All systems operational"
      : systemStatus === "unknown"
        ? "System status unavailable"
        : "System degraded";

  return (
    <aside className="fixed inset-y-0 left-0 z-40 flex w-[280px] -translate-x-full flex-col border-r border-[color:var(--border)] bg-[color:var(--surface)] pt-16 shadow-lg transition-transform duration-200 ease-in-out [[data-sidebar=open]_&]:translate-x-0 md:relative md:inset-auto md:z-auto md:w-[260px] md:translate-x-0 md:pt-0 md:shadow-none md:transition-none">
      {/* Org switcher — mobile only (desktop has it in header) */}
      <div className="border-b border-[color:var(--border)] px-4 py-3 md:hidden">
        <OrgSwitcher />
      </div>
      <div className="flex-1 px-3 py-4">
        <p className="px-3 text-xs font-semibold uppercase tracking-wider text-[color:var(--text-muted)]">
          Navigation
        </p>
        <nav className="mt-3 space-y-4 text-sm">
          <div>
            <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-[color:var(--text-quiet)]">
              Overview
            </p>
            <div className="mt-1 space-y-1">
              <Link
                href="/dashboard"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname === "/dashboard"
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <BarChart3 className="h-4 w-4" />
                Dashboard
              </Link>
              <Link
                href="/live"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/live")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <Radio className="h-4 w-4" />
                Agent Activity
              </Link>
              <Link
                href="/chat"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/chat")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <MessageSquare className="h-4 w-4" />
                Chat
              </Link>
              <Link
                href="/activity"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/activity")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <Activity className="h-4 w-4" />
                Activity Log
              </Link>
            </div>
          </div>

          {(isFeatureEnabled("paper_trading") || isFeatureEnabled("watchlist") || isFeatureEnabled("polymarket")) ? (
          <div>
            <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-[color:var(--text-quiet)]">
              Trading
            </p>
            <div className="mt-1 space-y-1">
              {isFeatureEnabled("paper_trading") ? (
              <Link
                href="/paper-trading"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/paper-trading")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <BarChart3 className="h-4 w-4" />
                Paper Trading
              </Link>
              ) : null}
              {isFeatureEnabled("watchlist") ? (
              <Link
                href="/watchlist"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/watchlist")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <Star className="h-4 w-4" />
                Watchlist
              </Link>
              ) : null}
              {isFeatureEnabled("polymarket") ? (
              <Link
                href="/trading"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/trading")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <TrendingUp className="h-4 w-4" />
                Prediction Markets
              </Link>
              ) : null}
            </div>
          </div>
          ) : null}

          <div>
            <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-[color:var(--text-quiet)]">
              Business
            </p>
            <div className="mt-1 space-y-1">
              {isFeatureEnabled("email") ? (
              <Link
                href="/email"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/email")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <Mail className="h-4 w-4" />
                Email
              </Link>
              ) : null}
              {isFeatureEnabled("google_calendar") ? (
              <Link
                href="/calendar"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/calendar")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <Calendar className="h-4 w-4" />
                Calendar
              </Link>
              ) : null}
              <Link
                href="/documents"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/documents")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <FileText className="h-4 w-4" />
                Documents
              </Link>
            </div>
          </div>

          <div>
            <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-[color:var(--text-quiet)]">
              System
            </p>
            <div className="mt-1 space-y-1">
              <Link
                href="/memory"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/memory")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <Folder className="h-4 w-4" />
                Memory
              </Link>
              {isFeatureEnabled("cron_jobs") ? (
              <Link
                href="/cron-jobs"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/cron-jobs")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <Clock className="h-4 w-4" />
                Scheduled Tasks
              </Link>
              ) : null}
              {isFeatureEnabled("cost_tracker") ? (
              <Link
                href="/costs"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/costs")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <Folder className="h-4 w-4" />
                Cost & Usage
              </Link>
              ) : null}
              <Link
                href="/audit"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/audit")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <Shield className="h-4 w-4" />
                Audit Log
              </Link>
              <Link
                href="/org-settings"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/org-settings")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <Building2 className="h-4 w-4" />
                Org Settings
              </Link>
            </div>
          </div>

          <div>
            <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-[color:var(--text-quiet)]">
              Boards
            </p>
            <div className="mt-1 space-y-1">
              <Link
                href="/board-groups"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/board-groups")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <Folder className="h-4 w-4" />
                Board groups
              </Link>
              <Link
                href="/boards"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/boards")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <LayoutGrid className="h-4 w-4" />
                Boards
              </Link>
              <Link
                href="/tags"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/tags")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <Tags className="h-4 w-4" />
                Tags
              </Link>
              {isFeatureEnabled("approvals") ? (
              <Link
                href="/approvals"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/approvals")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <CheckCircle2 className="h-4 w-4" />
                Approvals
              </Link>
              ) : null}
              {isAdmin ? (
                <Link
                  href="/custom-fields"
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                    pathname.startsWith("/custom-fields")
                      ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                      : "hover:bg-[color:var(--surface-muted)]",
                  )}
                >
                  <Settings className="h-4 w-4" />
                  Custom fields
                </Link>
              ) : null}
            </div>
          </div>

          <div>
            {isAdmin ? (
              <>
                <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-[color:var(--text-quiet)]">
                  Skills
                </p>
                <div className="mt-1 space-y-1">
                  <Link
                    href="/skills/marketplace"
                    className={cn(
                      "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                      pathname === "/skills" ||
                        pathname.startsWith("/skills/marketplace")
                        ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                        : "hover:bg-[color:var(--surface-muted)]",
                    )}
                  >
                    <Store className="h-4 w-4" />
                    Skill Library
                  </Link>
                  <Link
                    href="/skills/packs"
                    className={cn(
                      "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                      pathname.startsWith("/skills/packs")
                        ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                        : "hover:bg-[color:var(--surface-muted)]",
                    )}
                  >
                    <Boxes className="h-4 w-4" />
                    Packs
                  </Link>
                </div>
              </>
            ) : null}
          </div>

          <div>
            <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-[color:var(--text-quiet)]">
              Administration
            </p>
            <div className="mt-1 space-y-1">
              <Link
                href="/organization"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/organization")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <Building2 className="h-4 w-4" />
                Organization
              </Link>
              {isAdmin ? (
                <Link
                  href="/gateways"
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                    pathname.startsWith("/gateways")
                      ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                      : "hover:bg-[color:var(--surface-muted)]",
                  )}
                >
                  <Network className="h-4 w-4" />
                  Gateways
                </Link>
              ) : null}
              {isAdmin ? (
                <Link
                  href="/agents"
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                    pathname.startsWith("/agents")
                      ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                      : "hover:bg-[color:var(--surface-muted)]",
                  )}
                >
                  <Bot className="h-4 w-4" />
                  Agents
                </Link>
              ) : null}
            </div>
          </div>
          <div className="mt-2">
            <Link
              href="/help"
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                pathname.startsWith("/help")
                  ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                  : "hover:bg-[color:var(--surface-muted)]",
              )}
            >
              <HelpCircle className="h-4 w-4" />
              Help & Support
            </Link>
          </div>
        </nav>
      </div>
      <div className="border-t border-[color:var(--border)] p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-[color:var(--text-muted)]">
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                systemStatus === "operational" && "bg-emerald-500",
                systemStatus === "degraded" && "bg-rose-500",
                systemStatus === "unknown" && "bg-slate-300 dark:bg-slate-600",
              )}
            />
            {statusLabel}
          </div>
          <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="rounded-md p-1.5 text-[color:var(--text-quiet)] hover:bg-[color:var(--surface-muted)] hover:text-[color:var(--text)] transition"
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </aside>
  );
}
