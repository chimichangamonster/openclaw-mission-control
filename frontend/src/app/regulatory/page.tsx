"use client";

export const dynamic = "force-dynamic";

import { useMemo, useState } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { FeatureGate } from "@/components/molecules/FeatureGate";
import { useOrgMembers } from "@/lib/use-org-members";
import {
  listTags,
  loadAuthoredSnapshot,
  toggleTask,
  updatePhase,
  type AuthoredSnapshot,
  type AuthoredSnapshotPhase,
  type AuthoredSnapshotPriorityNote,
  type AuthoredSnapshotStream,
  type AuthoredSnapshotTask,
  type AuthoredSnapshotTaskTag,
  type RegulatoryTag,
} from "@/lib/regulatory-api";
import { RegulatoryDetailPanel } from "./regulatory-detail-panel";
import {
  AddPhaseModal,
  AddTaskModal,
  ImportHtmlModal,
} from "./regulatory-modals";

import styles from "./regulatory.module.css";

const COUNTRY_TABS: { code: string; label: string; enabled: boolean }[] = [
  { code: "CA", label: "Canada", enabled: true },
  { code: "IN", label: "India", enabled: false },
  { code: "KE", label: "Kenya", enabled: false },
];

// ---------------------------------------------------------------------------
// Pure helpers — visual mapping from data fields to CSS-module class names.
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

function TagPills({ tags }: { tags: AuthoredSnapshotTaskTag[] }) {
  if (tags.length === 0) return null;
  return (
    <span className={styles.tagPills}>
      {tags.map((t) => (
        <span key={t.id} className={tagPillClass(t.color_token)}>
          {t.label}
        </span>
      ))}
    </span>
  );
}

function TaskRow({
  task,
  onToggle,
  onSelect,
}: {
  task: AuthoredSnapshotTask;
  onToggle: (taskId: string) => void;
  onSelect: (task: AuthoredSnapshotTask) => void;
}) {
  return (
    <li
      className={`${styles.taskItem} ${task.completed ? styles.taskItemDone : ""}`}
    >
      <input
        type="checkbox"
        checked={task.completed}
        aria-label={task.body}
        onChange={() => onToggle(task.id)}
      />
      <button
        type="button"
        className={`${styles.taskBody} ${styles.taskBodyButton}`}
        onClick={() => onSelect(task)}
      >
        {task.body}
      </button>
      <TagPills tags={task.tags} />
    </li>
  );
}

function PriorityNoteBanner({ note }: { note: AuthoredSnapshotPriorityNote }) {
  return <div className={priorityNoteClass(note.severity)}>{note.body}</div>;
}

function PhaseBlock({
  phase,
  forceOpen,
  onToggleTask,
  onSelectTask,
  onAddTaskClick,
  onRenamePhase,
}: {
  phase: AuthoredSnapshotPhase;
  forceOpen: boolean | null;
  onToggleTask: (taskId: string) => void;
  onSelectTask: (task: AuthoredSnapshotTask) => void;
  onAddTaskClick: (phaseId: string) => void;
  onRenamePhase: (phaseId: string, name: string) => void;
}) {
  const [localOpen, setLocalOpen] = useState(phase.default_open);
  const open = forceOpen === null ? localOpen : forceOpen;
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState(phase.name);

  const startEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    setNameDraft(phase.name);
    setEditingName(true);
  };
  const commitName = () => {
    const next = nameDraft.trim();
    setEditingName(false);
    if (next && next !== phase.name) {
      onRenamePhase(phase.id, next);
    } else {
      setNameDraft(phase.name);
    }
  };
  const cancelName = () => {
    setNameDraft(phase.name);
    setEditingName(false);
  };

  return (
    <div className={styles.phaseBlock}>
      <div
        className={styles.phaseHeader}
        onClick={() => {
          if (!editingName) setLocalOpen((v) => !v);
        }}
        role="button"
        aria-expanded={open}
        tabIndex={0}
        onKeyDown={(e) => {
          if (editingName) return;
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setLocalOpen((v) => !v);
          }
        }}
      >
        <span className={`${styles.badge} ${badgeClass(phase.badge_kind)}`}>
          {phase.badge_kind}
        </span>
        {editingName ? (
          <input
            type="text"
            aria-label="Rename phase"
            className={styles.phaseNameInput}
            autoFocus
            value={nameDraft}
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => setNameDraft(e.target.value)}
            onBlur={commitName}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                e.stopPropagation();
                cancelName();
              } else if (e.key === "Enter") {
                e.preventDefault();
                e.stopPropagation();
                e.currentTarget.blur();
              }
            }}
          />
        ) : (
          <>
            <span>{phase.name}</span>
            <button
              type="button"
              aria-label={`Rename ${phase.name}`}
              className={styles.phaseNameEditBtn}
              onClick={startEdit}
            >
              ✎
            </button>
          </>
        )}
        {phase.timing_label && !editingName && (
          <span className={styles.phaseTiming}>{phase.timing_label}</span>
        )}
      </div>
      {open && (
        <>
          {phase.priority_notes.map((n) => (
            <PriorityNoteBanner key={n.id} note={n} />
          ))}
          <ul className={styles.taskList}>
            {phase.tasks.map((t) => (
              <TaskRow
                key={t.id}
                task={t}
                onToggle={onToggleTask}
                onSelect={onSelectTask}
              />
            ))}
          </ul>
          <button
            type="button"
            className={styles.toolbarBtn}
            onClick={(e) => {
              e.stopPropagation();
              onAddTaskClick(phase.id);
            }}
          >
            + Add task
          </button>
        </>
      )}
    </div>
  );
}

function StreamBlock({
  stream,
  forceOpen,
  onToggleTask,
  onSelectTask,
  onAddTaskClick,
  onAddPhaseClick,
  onRenamePhase,
}: {
  stream: AuthoredSnapshotStream;
  forceOpen: boolean | null;
  onToggleTask: (taskId: string) => void;
  onSelectTask: (task: AuthoredSnapshotTask) => void;
  onAddTaskClick: (phaseId: string) => void;
  onAddPhaseClick: (streamId: string) => void;
  onRenamePhase: (phaseId: string, name: string) => void;
}) {
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
        {stream.phases.map((p) => (
          <PhaseBlock
            key={p.id}
            phase={p}
            forceOpen={forceOpen}
            onToggleTask={onToggleTask}
            onSelectTask={onSelectTask}
            onAddTaskClick={onAddTaskClick}
            onRenamePhase={onRenamePhase}
          />
        ))}
        <button
          type="button"
          className={styles.toolbarBtn}
          onClick={() => onAddPhaseClick(stream.id)}
        >
          + Add phase
        </button>
      </div>
    </section>
  );
}

function StatBar({ snapshot }: { snapshot: AuthoredSnapshot }) {
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
  const { members: orgMembers } = useOrgMembers();
  const queryClient = useQueryClient();

  const [countryCode, setCountryCode] = useState("CA");
  // Toolbar Expand/Collapse override, scoped per country so switching country
  // implicitly clears it without a setState-in-effect cascade.
  const [forceOpenState, setForceOpenState] = useState<{
    country: string;
    value: boolean;
  } | null>(null);
  const forceOpen =
    forceOpenState && forceOpenState.country === countryCode
      ? forceOpenState.value
      : null;
  const [selectedTask, setSelectedTask] =
    useState<AuthoredSnapshotTask | null>(null);
  const [showImport, setShowImport] = useState(false);
  const [addPhaseStreamId, setAddPhaseStreamId] = useState<string | null>(
    null,
  );
  const [addTaskPhaseId, setAddTaskPhaseId] = useState<string | null>(null);

  const snapshotQuery = useQuery({
    queryKey: ["regulatory", "snapshot", countryCode],
    queryFn: () => loadAuthoredSnapshot(countryCode),
    enabled: Boolean(isSignedIn),
  });

  const tagsQuery = useQuery({
    queryKey: ["regulatory", "tags"],
    queryFn: () => listTags(),
    enabled: Boolean(isSignedIn),
  });

  const snapshot = snapshotQuery.data ?? null;
  const loading = snapshotQuery.isLoading;
  const loaded = snapshotQuery.isFetched && !snapshotQuery.isLoading;

  // Toggle mutation with optimistic checkbox flip on the cached snapshot.
  const toggleMutation = useMutation({
    mutationFn: (taskId: string) => toggleTask(taskId),
    onMutate: async (taskId) => {
      await queryClient.cancelQueries({
        queryKey: ["regulatory", "snapshot", countryCode],
      });
      const previous = queryClient.getQueryData<AuthoredSnapshot | null>([
        "regulatory",
        "snapshot",
        countryCode,
      ]);
      if (previous) {
        queryClient.setQueryData<AuthoredSnapshot | null>(
          ["regulatory", "snapshot", countryCode],
          {
            ...previous,
            streams: previous.streams.map((s) => ({
              ...s,
              phases: s.phases.map((ph) => ({
                ...ph,
                tasks: ph.tasks.map((t) =>
                  t.id === taskId ? { ...t, completed: !t.completed } : t,
                ),
              })),
            })),
          },
        );
      }
      return { previous };
    },
    onError: (_err, _taskId, context) => {
      if (context?.previous !== undefined) {
        queryClient.setQueryData(
          ["regulatory", "snapshot", countryCode],
          context.previous,
        );
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({
        queryKey: ["regulatory", "snapshot", countryCode],
      });
    },
  });

  // Phase-name rename (item 114). Optimistic update on the cached snapshot
  // so the new name is visible immediately; authoritative refetch on settle.
  const renamePhaseMutation = useMutation({
    mutationFn: ({ phaseId, name }: { phaseId: string; name: string }) =>
      updatePhase(phaseId, { name }),
    onMutate: async ({ phaseId, name }) => {
      await queryClient.cancelQueries({
        queryKey: ["regulatory", "snapshot", countryCode],
      });
      const previous = queryClient.getQueryData<AuthoredSnapshot | null>([
        "regulatory",
        "snapshot",
        countryCode,
      ]);
      if (previous) {
        queryClient.setQueryData<AuthoredSnapshot | null>(
          ["regulatory", "snapshot", countryCode],
          {
            ...previous,
            streams: previous.streams.map((s) => ({
              ...s,
              phases: s.phases.map((ph) =>
                ph.id === phaseId ? { ...ph, name } : ph,
              ),
            })),
          },
        );
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous !== undefined) {
        queryClient.setQueryData(
          ["regulatory", "snapshot", countryCode],
          context.previous,
        );
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({
        queryKey: ["regulatory", "snapshot", countryCode],
      });
    },
  });

  const headerSubtitle = useMemo(() => {
    if (!snapshot) return undefined;
    return `${snapshot.country.display_label} — ${snapshot.totals.completed}/${snapshot.totals.tasks} tasks complete (${snapshot.totals.percent}%)`;
  }, [snapshot]);

  // When the snapshot refetches, find the latest version of the selected task
  // so the detail panel sees authoritative values (notes saved, tags added).
  const selectedTaskFresh = useMemo(() => {
    if (!selectedTask || !snapshot) return selectedTask;
    for (const s of snapshot.streams) {
      for (const ph of s.phases) {
        const t = ph.tasks.find((tk) => tk.id === selectedTask.id);
        if (t) return t;
      }
    }
    return selectedTask;
  }, [selectedTask, snapshot]);

  const allTags: AuthoredSnapshotTaskTag[] = useMemo(() => {
    const raw: RegulatoryTag[] = tagsQuery.data ?? [];
    return raw.map((t) => ({
      id: t.id,
      slug: t.slug,
      label: t.label,
      color_token: t.color_token,
    }));
  }, [tagsQuery.data]);

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

        <div className={styles.toolbar}>
          <button
            type="button"
            className={styles.toolbarBtn}
            onClick={() =>
              setForceOpenState({ country: countryCode, value: true })
            }
          >
            Expand all
          </button>
          <button
            type="button"
            className={styles.toolbarBtn}
            onClick={() =>
              setForceOpenState({ country: countryCode, value: false })
            }
          >
            Collapse all
          </button>
          <button
            type="button"
            className={styles.toolbarBtn}
            onClick={() => window.print()}
          >
            Print
          </button>
          <div className={styles.toolbarSpacer} />
          <button
            type="button"
            className={styles.toolbarBtn}
            onClick={() => setShowImport(true)}
          >
            Import HTML
          </button>
        </div>

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
              equipment-tracker.html to populate this country, or click{" "}
              <strong>Import HTML</strong> above.
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
                <StreamBlock
                  key={s.id}
                  stream={s}
                  forceOpen={forceOpen}
                  onToggleTask={(id) => toggleMutation.mutate(id)}
                  onSelectTask={(t) => setSelectedTask(t)}
                  onAddTaskClick={(phaseId) => setAddTaskPhaseId(phaseId)}
                  onAddPhaseClick={(streamId) => setAddPhaseStreamId(streamId)}
                  onRenamePhase={(phaseId, name) =>
                    renamePhaseMutation.mutate({ phaseId, name })
                  }
                />
              ))
            )}
            <StatBar snapshot={snapshot} />
          </>
        )}
      </div>

      {selectedTaskFresh && (
        <RegulatoryDetailPanel
          key={selectedTaskFresh.id}
          task={selectedTaskFresh}
          allTags={allTags}
          orgMembers={orgMembers}
          onClose={() => setSelectedTask(null)}
        />
      )}

      {showImport && <ImportHtmlModal onClose={() => setShowImport(false)} />}

      {addPhaseStreamId && snapshot && (
        <AddPhaseModal
          streamId={addPhaseStreamId}
          countryId={snapshot.country.id}
          onClose={() => setAddPhaseStreamId(null)}
        />
      )}

      {addTaskPhaseId && (
        <AddTaskModal
          phaseId={addTaskPhaseId}
          onClose={() => setAddTaskPhaseId(null)}
        />
      )}
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
