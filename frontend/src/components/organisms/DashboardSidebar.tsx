"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  Radio,
  CheckCircle2,
  Eye,
  FileText,
  Folder,
  Building2,
  Calendar,
  HelpCircle,
  LayoutGrid,
  Mail,
  MapPin,
  MessageSquare,
  Moon,
  Network,
  Sun,
  TrendingUp,
  Shield,
  Tags,
  Star,
  BookOpen,
} from "lucide-react";
import { useTheme } from "next-themes";

import { useAuth } from "@/auth/clerk";
import { customFetch } from "@/api/mutator";
import { useFeatureFlags } from "@/lib/use-feature-flags";
import { useNotifications } from "@/components/providers/NotificationProvider";
import { useQuery } from "@tanstack/react-query";
import { OrgSwitcher } from "@/components/organisms/OrgSwitcher";
import { cn } from "@/lib/utils";

export function DashboardSidebar() {
  const pathname = usePathname();
  const { theme, setTheme } = useTheme();
  const { isSignedIn } = useAuth();
  const { isFeatureEnabled } = useFeatureFlags(Boolean(isSignedIn));
  const { unreadReportsCount } = useNotifications();
  const healthQuery = useQuery<{ status?: string } | undefined>({
    queryKey: ["/api/v1/system/health"],
    queryFn: async () => {
      const res = (await customFetch("/api/v1/system/health", { method: "GET" })) as {
        data?: { status?: string };
        status?: string;
      };
      return (res?.data ?? res) as { status?: string } | undefined;
    },
    refetchInterval: 30_000,
    refetchOnMount: "always" as const,
    retry: false,
  });

  const healthData = healthQuery.data;
  const okValue = healthData?.status === "healthy"
    ? true
    : healthData?.status === "degraded" || healthData?.status === "down"
      ? false
      : undefined;
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
    <aside className="fixed inset-y-0 left-0 z-40 flex w-[280px] min-h-0 -translate-x-full flex-col border-r border-[color:var(--border)] bg-[color:var(--surface)] pt-16 shadow-lg transition-transform duration-200 ease-in-out [[data-sidebar=open]_&]:translate-x-0 md:relative md:inset-auto md:z-auto md:w-[260px] md:translate-x-0 md:pt-0 md:shadow-none md:transition-none">
      {/* Org switcher — mobile only (desktop has it in header) */}
      <div className="border-b border-[color:var(--border)] px-4 py-3 md:hidden">
        <OrgSwitcher />
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto px-3 py-4">
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
              {isFeatureEnabled("personal_bookkeeping") ? (
              <Link
                href="/bookkeeping"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/bookkeeping")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <BookOpen className="h-4 w-4" />
                Bookkeeping
              </Link>
              ) : null}
            </div>
          </div>

          <div>
            <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-[color:var(--text-quiet)]">
              System
            </p>
            <div className="mt-1 space-y-1">
              <Link
                href={
                  unreadReportsCount > 0 ? "/memory?tab=reports" : "/memory"
                }
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname === "/memory"
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <Folder className="h-4 w-4" />
                <span className="flex-1">Memory</span>
                {unreadReportsCount > 0 ? (
                  <span
                    aria-label={`${unreadReportsCount} unread report${unreadReportsCount === 1 ? "" : "s"}`}
                    className="ml-auto inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-rose-500 px-1.5 text-[10px] font-semibold leading-5 text-white"
                  >
                    {unreadReportsCount > 99 ? "99+" : unreadReportsCount}
                  </span>
                ) : null}
              </Link>
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
            </div>
          </div>

          {isFeatureEnabled("pentest") ? (
          <div>
            <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-[color:var(--text-quiet)]">
              Security
            </p>
            <div className="mt-1 space-y-1">
              <Link
                href="/pentest"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname === "/pentest"
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <Shield className="h-4 w-4" />
                Command Center
              </Link>
              <Link
                href="/pentest/sdr"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/pentest/sdr")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <Radio className="h-4 w-4" />
                SDR Workspace
              </Link>
              <Link
                href="/pentest/wardrive"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/pentest/wardrive")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <MapPin className="h-4 w-4" />
                Wardriving
              </Link>
              <Link
                href="/pentest/network"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/pentest/network")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <Network className="h-4 w-4" />
                Network Map
              </Link>
              <Link
                href="/pentest/tscm"
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[color:var(--text)] transition",
                  pathname.startsWith("/pentest/tscm")
                    ? "bg-[color:var(--accent-soft)] text-[color:var(--accent-strong)] font-medium"
                    : "hover:bg-[color:var(--surface-muted)]",
                )}
              >
                <Eye className="h-4 w-4" />
                TSCM Workspace
              </Link>
            </div>
          </div>
          ) : null}

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
            </div>
          </div>

          <div>
            <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-[color:var(--text-quiet)]">
              Organization
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
                systemStatus === "degraded" && "bg-amber-500",
                systemStatus === "unknown" && "bg-rose-500",
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
