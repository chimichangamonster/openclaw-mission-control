"use client";

export const dynamic = "force-dynamic";

/**
 * Grants tracker page (item 107 v2 Phase 2).
 *
 * Mirrors `/regulatory` page architecture: FeatureGate + admin guard +
 * Tanstack Query reads. Phase 2 ships:
 *   - Stat strip (committed / drawn / upcoming deadlines / draws-to-claim)
 *   - Active grants table with countdown badge per row
 *   - Detail drawer (metadata + burn chart + deadline timeline + prerequisites)
 *
 * Phase 2b adds: create grant, edit grant, mark draw received, mark deadline
 * submitted, link/unlink prerequisites. Out-of-scope here.
 *
 * Determinism posture per `feedback_determinism_first_for_high_liability.md`:
 * zero LLM in path. All amounts/dates/statuses are operator-typed SQL.
 */

import { useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { FeatureGate } from "@/components/molecules/FeatureGate";
import { useOrganizationMembership } from "@/lib/use-organization-membership";
import {
  getGrantDetail,
  listGrants,
  type Grant,
  type GrantDeadline,
  type GrantDetail,
} from "@/lib/grants-api";

import { GrantsDetailDrawer } from "./grants-detail-drawer";
import styles from "./grants.module.css";

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

const fmtMoney = (n: number, currency = "CAD"): string =>
  new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(n);

const daysUntil = (isoDate: string): number => {
  const today = new Date();
  today.setUTCHours(12, 0, 0, 0);
  const target = new Date(`${isoDate}T12:00:00Z`);
  return Math.round(
    (target.getTime() - today.getTime()) / (1000 * 60 * 60 * 24),
  );
};

function earliestUpcomingDeadline(
  deadlines: GrantDeadline[],
): GrantDeadline | null {
  const upcoming = deadlines.filter((d) => d.status === "upcoming");
  if (upcoming.length === 0) return null;
  return upcoming.reduce((earliest, d) =>
    d.deadline_date < earliest.deadline_date ? d : earliest,
  );
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case "planned":
      return `${styles.statusBadge} ${styles.statusPlanned}`;
    case "drafting":
      return `${styles.statusBadge} ${styles.statusDrafting}`;
    case "submitted":
      return `${styles.statusBadge} ${styles.statusSubmitted}`;
    case "under_review":
      return `${styles.statusBadge} ${styles.statusUnderReview}`;
    case "awarded":
      return `${styles.statusBadge} ${styles.statusAwarded}`;
    case "declined":
      return `${styles.statusBadge} ${styles.statusDeclined}`;
    case "completed":
      return `${styles.statusBadge} ${styles.statusCompleted}`;
    case "withdrawn":
      return `${styles.statusBadge} ${styles.statusWithdrawn}`;
    default:
      return styles.statusBadge;
  }
}

interface DeadlineBadgeProps {
  grantId: string;
  detail: GrantDetail | undefined;
}

function DeadlineBadge({ grantId, detail }: DeadlineBadgeProps) {
  if (!detail) {
    return <span className={styles.deadlineNone}>—</span>;
  }
  const earliest = earliestUpcomingDeadline(detail.deadlines);
  if (!earliest) {
    return (
      <span
        className={styles.deadlineNone}
        data-testid={`deadline-badge-${grantId}`}
      >
        none
      </span>
    );
  }
  const days = daysUntil(earliest.deadline_date);
  let cls = styles.deadlineNormal;
  if (days < 14) cls = styles.deadlineRed;
  else if (days < 30) cls = styles.deadlineAmber;
  const text = days >= 0 ? `${days}d` : `${Math.abs(days)}d overdue`;
  return (
    <span
      className={`${styles.deadlineBadge} ${cls}`}
      data-testid={`deadline-badge-${grantId}`}
    >
      {text}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function GrantsPageInner() {
  const { isSignedIn } = useAuth();
  const { isAdmin } = useOrganizationMembership(isSignedIn);
  const [selectedGrantId, setSelectedGrantId] = useState<string | null>(null);

  const grantsQuery = useQuery({
    queryKey: ["grants", "list"],
    queryFn: listGrants,
    enabled: isAdmin,
  });

  const grants: Grant[] = useMemo(
    () => grantsQuery.data ?? [],
    [grantsQuery.data],
  );

  // Fetch detail for each grant in parallel — needed for stat-strip
  // aggregates (drawn-to-date, upcoming deadlines) + per-row countdown
  // badges. With Magnetik's 5 grants this is fine; if N grows past ~20,
  // add a list-aggregates endpoint instead.
  const detailQueries = useQueries({
    queries: grants.map((g) => ({
      queryKey: ["grants", "detail", g.id],
      queryFn: () => getGrantDetail(g.id),
      enabled: isAdmin && !!g.id,
    })),
  });

  const detailById = useMemo(() => {
    const map = new Map<string, GrantDetail>();
    for (let i = 0; i < grants.length; i++) {
      const d = detailQueries[i]?.data;
      if (d) map.set(grants[i].id, d);
    }
    return map;
  }, [grants, detailQueries]);

  const stats = useMemo(() => {
    let committed = 0;
    let drawn = 0;
    let upcomingNext30 = 0;
    let drawsToClaim = 0;
    const todayIso = new Date().toISOString().slice(0, 10);
    for (const grant of grants) {
      committed += Number(grant.awarded_amount || 0);
      const detail = detailById.get(grant.id);
      if (!detail) continue;
      for (const draw of detail.draws) {
        drawn += Number(draw.drawn_amount || 0);
        if (
          draw.status === "pending" &&
          draw.target_date &&
          draw.target_date <= todayIso
        ) {
          drawsToClaim += 1;
        }
      }
      for (const dl of detail.deadlines) {
        if (dl.status !== "upcoming") continue;
        const days = daysUntil(dl.deadline_date);
        if (days >= 0 && days <= 30) upcomingNext30 += 1;
      }
    }
    return { committed, drawn, upcomingNext30, drawsToClaim };
  }, [grants, detailById]);

  const selectedDetail = selectedGrantId
    ? detailById.get(selectedGrantId)
    : undefined;

  if (!isAdmin) {
    return (
      <DashboardPageLayout
        title="Grants Tracker"
        signedOut={{
          message: "Sign in to view the grants tracker.",
          forceRedirectUrl: "/grants",
          signUpForceRedirectUrl: "/grants",
        }}
      >
        <div className={styles.emptyState}>
          <p>
            <strong>Admin access required.</strong>
          </p>
          <p style={{ marginTop: "0.5rem" }}>
            The grants tracker is restricted to organization admins. Ask your
            admin to grant access if you need to manage grant programs and draw
            schedules.
          </p>
        </div>
      </DashboardPageLayout>
    );
  }

  const headerSubtitle =
    grants.length > 0
      ? `${grants.length} grant${grants.length === 1 ? "" : "s"} · ${fmtMoney(stats.committed)} committed`
      : undefined;

  return (
    <DashboardPageLayout
      title="Grants Tracker"
      description={headerSubtitle}
      signedOut={{
        message: "Sign in to view the grants tracker.",
        forceRedirectUrl: "/grants",
        signUpForceRedirectUrl: "/grants",
      }}
    >
      <div className={styles.root}>
        {/* Stat strip */}
        <div className={styles.statStrip}>
          <StatCard
            label="Total committed"
            value={fmtMoney(stats.committed)}
            sub="Sum of awarded across all grants"
          />
          <StatCard
            label="Drawn-to-date"
            value={fmtMoney(stats.drawn)}
            sub="Sum of drawn amounts across all draws"
          />
          <StatCard
            label="Upcoming deadlines"
            value={String(stats.upcomingNext30)}
            sub="Reporting deadlines within next 30 days"
          />
          <StatCard
            label="Draws to claim"
            value={String(stats.drawsToClaim)}
            sub="Pending draws past target date"
          />
        </div>

        {/* Active grants table */}
        {grantsQuery.isLoading && (
          <div className={styles.emptyState}>
            <p>Loading grants…</p>
          </div>
        )}
        {!grantsQuery.isLoading && grants.length === 0 && (
          <div className={styles.emptyState}>
            <p>
              <strong>No grants tracked yet for this org.</strong>
            </p>
            <p style={{ marginTop: "0.5rem" }}>
              Seed via{" "}
              <code>scripts/seed_magnetik_grants.py</code> or use{" "}
              <code>POST /api/v1/grants</code> directly.
            </p>
          </div>
        )}
        {grants.length > 0 && (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Program</th>
                  <th>Status</th>
                  <th>Awarded</th>
                  <th>Next deadline</th>
                </tr>
              </thead>
              <tbody>
                {grants.map((g) => (
                  <tr
                    key={g.id}
                    className={styles.tableRow}
                    onClick={() => setSelectedGrantId(g.id)}
                  >
                    <td>
                      <div className={styles.programName}>{g.program_name}</div>
                      <div className={styles.bodyName}>{g.granting_body}</div>
                    </td>
                    <td>
                      <span className={statusBadgeClass(g.application_status)}>
                        {g.application_status.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td>
                      {g.awarded_amount
                        ? fmtMoney(Number(g.awarded_amount), g.currency)
                        : "—"}
                    </td>
                    <td>
                      <DeadlineBadge
                        grantId={g.id}
                        detail={detailById.get(g.id)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedDetail && (
        <GrantsDetailDrawer
          grant={selectedDetail}
          onClose={() => setSelectedGrantId(null)}
        />
      )}
    </DashboardPageLayout>
  );
}

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className={styles.statCard}>
      <div className={styles.statLabel}>{label}</div>
      <div className={styles.statValue}>{value}</div>
      {sub && <div className={styles.statSub}>{sub}</div>}
    </div>
  );
}

export default function GrantsPage() {
  return (
    <FeatureGate flag="grants_tracker" label="Grants Tracker">
      <GrantsPageInner />
    </FeatureGate>
  );
}
