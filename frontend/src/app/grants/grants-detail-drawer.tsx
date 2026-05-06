"use client";

/**
 * Grants detail drawer (item 107 v2 Phase 2).
 *
 * Read-only Phase 2 surface — operator-grade edit affordances (mark draw
 * received, mark deadline submitted, link/unlink prerequisites) are Phase 2b
 * follow-up. Phase 2 ships viewing + drawer plumbing first; mutations follow
 * once dogfood confirms the layout.
 *
 * Determinism posture per `feedback_determinism_first_for_high_liability.md`:
 * zero LLM in any aggregation. Burn chart, prerequisite counts, deadline
 * countdowns are all deterministic JS.
 */

import Link from "next/link";
import { ExternalLink } from "lucide-react";

import type {
  GrantDeadline,
  GrantDetail,
  GrantDraw,
  GrantPrerequisite,
} from "@/lib/grants-api";

import { amountLabel } from "./page";
import styles from "./grants.module.css";

const fmtMoney = (raw: string | null | undefined, currency = "CAD"): string => {
  if (raw == null) return `${currency} —`;
  const n = Number(raw);
  if (!Number.isFinite(n)) return `${currency} —`;
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(n);
};

const fmtDate = (raw: string | null | undefined): string => {
  if (!raw) return "—";
  // Backend returns YYYY-MM-DD for dates; render verbatim to avoid timezone
  // shifts (a Date parse on a date-only string falls back to UTC midnight,
  // then renders as previous day in MT).
  return raw;
};

const sumAmount = (rows: { drawn_amount?: string | null }[]): number =>
  rows.reduce((acc, r) => acc + (r.drawn_amount ? Number(r.drawn_amount) : 0), 0);

const sumTarget = (rows: { target_amount: string }[]): number =>
  rows.reduce((acc, r) => acc + Number(r.target_amount || 0), 0);

const daysUntil = (isoDate: string): number => {
  // Use UTC noon to avoid DST/edge-of-day skew.
  const today = new Date();
  today.setUTCHours(12, 0, 0, 0);
  const target = new Date(`${isoDate}T12:00:00Z`);
  return Math.round(
    (target.getTime() - today.getTime()) / (1000 * 60 * 60 * 24),
  );
};

interface Props {
  grant: GrantDetail;
  onClose: () => void;
}

export function GrantsDetailDrawer({ grant, onClose }: Props) {
  const totalTarget = sumTarget(grant.draws);
  const totalDrawn = sumAmount(grant.draws);
  const burnPercent = totalTarget > 0 ? Math.round((totalDrawn / totalTarget) * 100) : 0;

  return (
    <div
      className={styles.drawerBackdrop}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <aside className={styles.drawer} role="dialog" aria-label={grant.program_name}>
        <header className={styles.drawerHeader}>
          <div>
            <div className={styles.drawerTitle}>
              {grant.program_name}
              {grant.program_url && (
                <a
                  href={grant.program_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={styles.programLink}
                  aria-label={`Open ${grant.program_name} program page in new tab`}
                >
                  <ExternalLink size={16} aria-hidden="true" />
                </a>
              )}
            </div>
            <div className={styles.drawerSubtitle}>{grant.granting_body}</div>
          </div>
          <button
            type="button"
            className={styles.drawerCloseBtn}
            onClick={onClose}
            aria-label="Close"
          >
            Close
          </button>
        </header>

        <div className={styles.drawerBody}>
          {/* Metadata */}
          <section className={styles.drawerSection}>
            <div className={styles.drawerSectionTitle}>Grant metadata</div>
            <div className={styles.metaGrid}>
              <MetaCell label="Status" value={grant.application_status} />
              <MetaCell
                label={amountLabel(grant.application_status)}
                value={fmtMoney(grant.awarded_amount, grant.currency)}
              />
              <MetaCell
                label="Matched funding"
                value={fmtMoney(grant.matched_funding_amount, grant.currency)}
              />
              <MetaCell
                label="Co-investment %"
                value={
                  grant.cash_coinvestment_required_pct
                    ? `${grant.cash_coinvestment_required_pct}%`
                    : "—"
                }
              />
              <MetaCell
                label="Project start"
                value={fmtDate(grant.project_start_date)}
              />
              <MetaCell
                label="Project end"
                value={fmtDate(grant.project_end_date)}
              />
              <MetaCell
                label="Required entity"
                value={grant.incorporation_required_entity || "—"}
              />
              <MetaCell label="Submitted" value={fmtDate(grant.submitted_at)} />
              <MetaCell label="Decision" value={fmtDate(grant.decision_at)} />
            </div>
          </section>

          {/* Burn chart */}
          <section className={styles.drawerSection}>
            <div className={styles.drawerSectionTitle}>Draw schedule</div>
            <div className={styles.burnSummary}>
              <span className={styles.burnSummaryStrong}>
                {fmtMoney(String(totalDrawn), grant.currency)}
              </span>
              <span>drawn of</span>
              <span className={styles.burnSummaryStrong}>
                {fmtMoney(String(totalTarget), grant.currency)}
              </span>
              <span>· {burnPercent}%</span>
            </div>
            <div
              className={styles.burnTrack}
              role="progressbar"
              aria-valuenow={burnPercent}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className={styles.burnFill}
                style={{ width: `${Math.min(burnPercent, 100)}%` }}
              />
            </div>
            <div className={styles.drawList}>
              {grant.draws.length === 0 && (
                <span className={styles.prereqEmpty}>No draws scheduled.</span>
              )}
              {grant.draws.map((d) => (
                <DrawRow key={d.id} draw={d} currency={grant.currency} />
              ))}
            </div>
          </section>

          {/* Reporting deadlines */}
          <section className={styles.drawerSection}>
            <div className={styles.drawerSectionTitle}>Reporting deadlines</div>
            <div className={styles.deadlineList}>
              {grant.deadlines.length === 0 && (
                <span className={styles.prereqEmpty}>No deadlines tracked.</span>
              )}
              {grant.deadlines.map((dl) => (
                <DeadlineRow key={dl.id} deadline={dl} />
              ))}
            </div>
          </section>

          {/* Prerequisites */}
          <section className={styles.drawerSection}>
            <div className={styles.drawerSectionTitle}>
              Prerequisites (regulatory tasks)
            </div>
            <div className={styles.prereqList}>
              {grant.prerequisites.length === 0 && (
                <span className={styles.prereqEmpty}>
                  No prerequisites linked.
                </span>
              )}
              {grant.prerequisites.map((p) => (
                <PrerequisiteRow key={p.regulatory_task_id} prereq={p} />
              ))}
            </div>
          </section>

          {grant.notes_md && (
            <section className={styles.drawerSection}>
              <div className={styles.drawerSectionTitle}>Notes</div>
              <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", margin: 0 }}>
                {grant.notes_md}
              </pre>
            </section>
          )}
        </div>
      </aside>
    </div>
  );
}

function MetaCell({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.metaCell}>
      <div className={styles.metaLabel}>{label}</div>
      <div className={styles.metaValue}>{value}</div>
    </div>
  );
}

function DrawRow({ draw, currency }: { draw: GrantDraw; currency: string }) {
  const drawn = draw.drawn_amount
    ? fmtMoney(draw.drawn_amount, currency)
    : "—";
  return (
    <div className={styles.drawRow}>
      <div>
        <div className={styles.drawLabel}>{draw.milestone_label}</div>
        <div className={styles.drawAmounts}>
          {fmtDate(draw.target_date)} · target {fmtMoney(draw.target_amount, currency)} ·
          drawn {drawn} · {draw.status}
        </div>
      </div>
    </div>
  );
}

function DeadlineRow({ deadline }: { deadline: GrantDeadline }) {
  const days = daysUntil(deadline.deadline_date);
  let cls = styles.deadlineNormal;
  if (deadline.status === "upcoming" && days >= 0) {
    if (days < 14) cls = styles.deadlineRed;
    else if (days < 30) cls = styles.deadlineAmber;
  }
  const countdownText =
    deadline.status === "upcoming"
      ? days >= 0
        ? `${days}d`
        : `${Math.abs(days)}d overdue`
      : deadline.status;
  return (
    <div className={styles.deadlineRow}>
      <div>
        <div className={styles.deadlineDate}>{fmtDate(deadline.deadline_date)}</div>
        <div className={styles.drawAmounts}>
          {deadline.deadline_type}
          {deadline.description ? ` — ${deadline.description}` : ""}
        </div>
      </div>
      <span className={`${styles.deadlineBadge} ${cls}`}>{countdownText}</span>
    </div>
  );
}

function PrerequisiteRow({ prereq }: { prereq: GrantPrerequisite }) {
  const label = prereq.label_override || prereq.task_body || "(missing task)";
  const done = Boolean(prereq.task_completed);
  return (
    <div className={styles.prereqRow}>
      {prereq.is_critical && !done && <span className={styles.prereqCriticalDot} />}
      <span className={done ? styles.prereqDone : ""}>
        {done ? "✓ " : "○ "}
        {label}
      </span>
      <Link
        href="/regulatory"
        className={styles.prereqLink}
        aria-label="Open regulatory tracker"
      >
        Open in /regulatory →
      </Link>
    </div>
  );
}
