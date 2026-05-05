"use client";

export const dynamic = "force-dynamic";

import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { FeatureGate } from "@/components/molecules/FeatureGate";
import { useOrganizationMembership } from "@/lib/use-organization-membership";
import {
  loadCountrySnapshot,
  type CountrySnapshot,
  type SnapshotPhase,
  type SnapshotPriorityNote,
  type SnapshotStream,
  type SnapshotTask,
  type SnapshotTaskTag,
} from "@/lib/regulatory-api";

import styles from "./regulatory.module.css";

const COUNTRY_TABS: { code: string; label: string; enabled: boolean }[] = [
  { code: "CA", label: "Canada", enabled: true },
  { code: "IN", label: "India", enabled: false },
  { code: "KE", label: "Kenya", enabled: false },
];

// ---------------------------------------------------------------------------
// Pure helpers — visual mapping from data fields to CSS-module class names.
// Kept as functions (not maps) so the lint hook doesn't yell about unused
// keys when a new badge_kind / severity / color_token surfaces upstream.
// ---------------------------------------------------------------------------

function badgeClass(badgeKind: string): string {
  switch (badgeKind) {
    case "now":
      return styles.badgeNow;
    case "pre":
      return styles.badgePre;
    case "arrive":
      return styles.badgeArrive;
    case "post":
      return styles.badgePost;
    case "concurrent":
      return styles.badgeConcurrent;
    case "corp":
      return styles.badgeCorp;
    case "insurance":
      return styles.badgeInsurance;
    default:
      return styles.badgeNow;
  }
}

function priorityNoteClass(severity: string): string {
  switch (severity) {
    case "critical":
      return `${styles.priorityNote} ${styles.priorityNoteCritical}`;
    case "warn":
      return `${styles.priorityNote} ${styles.priorityNoteWarn}`;
    case "navy-note":
      return `${styles.priorityNote} ${styles.priorityNoteNavy}`;
    case "info":
    default:
      return `${styles.priorityNote} ${styles.priorityNoteInfo}`;
  }
}

function progressFillClass(colorToken: string): string {
  switch (colorToken) {
    case "navy":
      return styles.progressBarFillNavy;
    case "green":
      return styles.progressBarFillGreen;
    case "orange":
      return styles.progressBarFillOrange;
    case "purple":
      return styles.progressBarFillPurple;
    default:
      return styles.progressBarFillNavy;
  }
}

function tagPillClass(colorToken: string): string {
  switch (colorToken) {
    case "navy":
      return `${styles.tagPill} ${styles.tagPillNavy}`;
    case "green":
      return `${styles.tagPill} ${styles.tagPillGreen}`;
    case "orange":
      return `${styles.tagPill} ${styles.tagPillOrange}`;
    default:
      return styles.tagPill;
  }
}

// ---------------------------------------------------------------------------
// Render pieces
// ---------------------------------------------------------------------------

function TagPills({ tags }: { tags: SnapshotTaskTag[] }) {
  if (tags.length === 0) return null;
  return (
    <span className={styles.tagPills}>
      {tags.map((t) => (
        <span key={t.slug} className={tagPillClass(t.color_token)}>
          {t.label}
        </span>
      ))}
    </span>
  );
}

function TaskRow({ task }: { task: SnapshotTask }) {
  return (
    <li
      className={`${styles.taskItem} ${task.completed ? styles.taskItemDone : ""}`}
    >
      <input type="checkbox" checked={task.completed} disabled readOnly />
      <span className={styles.taskBody}>
        {task.body}
        {/* Snapshot shape doesn't carry note (sanitized in public payload). */}
      </span>
      <TagPills tags={task.tags} />
    </li>
  );
}

function PriorityNoteBanner({ note }: { note: SnapshotPriorityNote }) {
  return <div className={priorityNoteClass(note.severity)}>{note.body}</div>;
}

function PhaseBlock({ phase }: { phase: SnapshotPhase }) {
  const [open, setOpen] = useState(phase.default_open);
  return (
    <div className={styles.phaseBlock}>
      <div
        className={styles.phaseHeader}
        onClick={() => setOpen((v) => !v)}
        role="button"
        aria-expanded={open}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setOpen((v) => !v);
          }
        }}
      >
        <span className={`${styles.badge} ${badgeClass(phase.badge_kind)}`}>
          {phase.badge_kind}
        </span>
        <span>{phase.name}</span>
        {phase.timing_label && (
          <span className={styles.phaseTiming}>{phase.timing_label}</span>
        )}
      </div>
      {open && (
        <>
          {phase.priority_notes.map((n, idx) => (
            <PriorityNoteBanner key={idx} note={n} />
          ))}
          <ul className={styles.taskList}>
            {phase.tasks.map((t, idx) => (
              <TaskRow key={idx} task={t} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function StreamBlock({ stream }: { stream: SnapshotStream }) {
  return (
    <section className={styles.streamCard}>
      <div className={styles.streamHeader}>
        <div>
          <div className={styles.streamTitle}>{stream.name}</div>
          {stream.timeline_label && (
            <div className={styles.streamMeta}>{stream.timeline_label}</div>
          )}
        </div>
        <div className={styles.streamMeta}>
          {stream.totals.completed} / {stream.totals.tasks} ·{" "}
          {stream.totals.percent}%
        </div>
      </div>
      <div className={styles.progressBarTrack}>
        <div
          className={`${styles.progressBarFill} ${progressFillClass(stream.color_token)}`}
          style={{ width: `${stream.totals.percent}%` }}
        />
      </div>
      <div style={{ marginTop: "0.75rem" }}>
        {stream.phases.map((p, idx) => (
          <PhaseBlock key={idx} phase={p} />
        ))}
      </div>
    </section>
  );
}

function StatBar({
  snapshot,
}: {
  snapshot: CountrySnapshot;
}) {
  const phaseCount = snapshot.streams.reduce(
    (acc, s) => acc + s.phases.length,
    0,
  );
  return (
    <div className={styles.statBar}>
      <span>
        Phases: <strong>{phaseCount}</strong>
      </span>
      <span>
        Tasks: <strong>{snapshot.totals.tasks}</strong>
      </span>
      <span>
        Completed: <strong>{snapshot.totals.completed}</strong>
      </span>
      <span>
        Progress: <strong>{snapshot.totals.percent}%</strong>
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function RegulatoryPageInner() {
  const { isSignedIn } = useAuth();
  const { isAdmin } = useOrganizationMembership(isSignedIn);

  const [countryCode, setCountryCode] = useState("CA");
  const [snapshot, setSnapshot] = useState<CountrySnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!isAdmin) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setLoaded(false);
      try {
        const result = await loadCountrySnapshot(countryCode);
        if (!cancelled) {
          setSnapshot(result);
          setLoaded(true);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [countryCode, isAdmin]);

  const headerSubtitle = useMemo(() => {
    if (!snapshot) return undefined;
    return `${snapshot.country.display_label} — ${snapshot.totals.completed}/${snapshot.totals.tasks} tasks complete (${snapshot.totals.percent}%)`;
  }, [snapshot]);

  if (!isAdmin) {
    return (
      <DashboardPageLayout
        title="Regulatory Tracker"
        signedOut={{
          message: "Sign in to view the regulatory tracker.",
          forceRedirectUrl: "/regulatory",
          signUpForceRedirectUrl: "/regulatory",
        }}
      >
        <div className={styles.emptyState}>
          <p>
            <strong>Admin access required.</strong>
          </p>
          <p style={{ marginTop: "0.5rem" }}>
            The regulatory tracker is restricted to organization admins. Ask
            your admin to grant access if you need to manage approval timelines.
          </p>
        </div>
      </DashboardPageLayout>
    );
  }

  return (
    <DashboardPageLayout
      title="Regulatory Tracker"
      description={headerSubtitle}
      signedOut={{
        message: "Sign in to view the regulatory tracker.",
        forceRedirectUrl: "/regulatory",
        signUpForceRedirectUrl: "/regulatory",
      }}
    >
      <div className={styles.root}>
        <nav className={styles.countryTabs} aria-label="Country">
          {COUNTRY_TABS.map((tab) => {
            const active = tab.code === countryCode;
            const className = [
              styles.countryTab,
              active ? styles.countryTabActive : "",
              !tab.enabled ? styles.countryTabDisabled : "",
            ]
              .filter(Boolean)
              .join(" ");
            return (
              <button
                key={tab.code}
                type="button"
                className={className}
                disabled={!tab.enabled}
                aria-current={active ? "page" : undefined}
                onClick={() => tab.enabled && setCountryCode(tab.code)}
                title={
                  tab.enabled
                    ? tab.label
                    : "Pipeline — not yet seeded for this org"
                }
              >
                {tab.label}
                {!tab.enabled && (
                  <span style={{ marginLeft: "0.4rem", fontSize: "0.7rem" }}>
                    (pipeline)
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {loading && !loaded && (
          <div className={styles.emptyState}>
            <p>Loading regulatory tracker…</p>
          </div>
        )}

        {loaded && snapshot === null && (
          <div className={styles.emptyState}>
            <p>
              <strong>Not yet seeded for this org.</strong>
            </p>
            <p style={{ marginTop: "0.5rem" }}>
              Use <code>POST /api/v1/regulatory/import-html</code> with your
              equipment-tracker.html to populate this country, or add streams
              and phases manually via the API. Edit affordances ship in Phase
              2b.
            </p>
          </div>
        )}

        {loaded && snapshot !== null && (
          <>
            {snapshot.streams.length === 0 ? (
              <div className={styles.emptyState}>
                <p>
                  <strong>No streams yet for {snapshot.country.display_label}.</strong>
                </p>
              </div>
            ) : (
              snapshot.streams.map((s) => (
                <StreamBlock key={s.slug} stream={s} />
              ))
            )}
            <StatBar snapshot={snapshot} />
          </>
        )}
      </div>
    </DashboardPageLayout>
  );
}

export default function RegulatoryPage() {
  return (
    <FeatureGate flag="regulatory" label="Regulatory Tracker">
      <RegulatoryPageInner />
    </FeatureGate>
  );
}
