/**
 * Regulatory tracker API helpers (item 101 v2 Phase 2a).
 *
 * Backend gates: `regulatory` feature flag (NOT `regulatory_tracker` — see
 * `app/api/regulatory.py:90`). Read endpoints require member+; mutations
 * require operator+ (phases/tasks/notes) or admin+ (streams/countries/tags).
 *
 * `loadCountrySnapshot()` produces the same nested shape as the public
 * snapshot endpoint (`app/api/regulatory_public.py`) so Phase 3 marketing-site
 * SSR can share types. The contract is locked by `regulatory-api.test.ts`.
 */

import { customFetch } from "@/api/mutator";

const V1 = "/api/v1";

// ---------------------------------------------------------------------------
// Types — mirror app/schemas/regulatory.py
// ---------------------------------------------------------------------------

export interface RegulatoryStream {
  id: string;
  organization_id: string;
  slug: string;
  name: string;
  description: string | null;
  color_token: string;
  budget_estimate: string | null;
  regulator_label: string | null;
  timeline_label: string | null;
  sort_order: number;
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface RegulatoryCountry {
  id: string;
  organization_id: string;
  code: string;
  name: string;
  status: "active" | "pipeline" | "archived";
  display_label: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface RegulatoryTag {
  id: string;
  organization_id: string;
  slug: string;
  label: string;
  color_token: string;
  kind: string;
  created_at: string;
}

export interface RegulatoryPhase {
  id: string;
  stream_id: string;
  country_id: string;
  name: string;
  badge_kind: string;
  timing_label: string | null;
  sort_order: number;
  default_open: boolean;
  created_at: string;
  updated_at: string;
}

export interface RegulatoryTask {
  id: string;
  phase_id: string;
  body: string;
  note: string | null;
  completed: boolean;
  completed_at: string | null;
  completed_by_user_id: string | null;
  assignee_user_id: string | null;
  due_date: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface RegulatoryPriorityNote {
  id: string;
  phase_id: string;
  body: string;
  severity: "critical" | "info" | "warn" | "navy-note";
  sort_order: number;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Snapshot shape — matches `regulatory_public.py` payload exactly
// ---------------------------------------------------------------------------

export interface SnapshotTotals {
  tasks: number;
  completed: number;
  percent: number;
}

export interface SnapshotTaskTag {
  slug: string;
  label: string;
  color_token: string;
}

export interface SnapshotTask {
  body: string;
  completed: boolean;
  tags: SnapshotTaskTag[];
}

export interface SnapshotPriorityNote {
  body: string;
  severity: string;
}

export interface SnapshotPhase {
  name: string;
  badge_kind: string;
  timing_label: string | null;
  default_open: boolean;
  priority_notes: SnapshotPriorityNote[];
  tasks: SnapshotTask[];
}

export interface SnapshotStream {
  slug: string;
  name: string;
  color_token: string;
  description: string | null;
  timeline_label: string | null;
  totals: SnapshotTotals;
  phases: SnapshotPhase[];
}

export interface CountrySnapshot {
  country: { code: string; display_label: string };
  totals: SnapshotTotals;
  streams: SnapshotStream[];
}

// ---------------------------------------------------------------------------
// Internal — unwrap customFetch's {data, status, headers} envelope
// ---------------------------------------------------------------------------

const unwrap = <T,>(res: unknown): T => {
  if (res && typeof res === "object" && "data" in (res as Record<string, unknown>)) {
    return (res as { data: T }).data;
  }
  return res as T;
};

// ---------------------------------------------------------------------------
// Read helpers (member+)
// ---------------------------------------------------------------------------

export async function listStreams(includeArchived = false): Promise<RegulatoryStream[]> {
  const qs = includeArchived ? "?include_archived=true" : "";
  const res = await customFetch(`${V1}/regulatory/streams${qs}`, { method: "GET" });
  return unwrap<RegulatoryStream[]>(res);
}

export async function listCountries(): Promise<RegulatoryCountry[]> {
  const res = await customFetch(`${V1}/regulatory/countries`, { method: "GET" });
  return unwrap<RegulatoryCountry[]>(res);
}

export async function listTags(): Promise<RegulatoryTag[]> {
  const res = await customFetch(`${V1}/regulatory/tags`, { method: "GET" });
  return unwrap<RegulatoryTag[]>(res);
}

export async function listPhases(params: {
  streamId: string;
  countryId: string;
}): Promise<RegulatoryPhase[]> {
  const qs = `?stream_id=${encodeURIComponent(params.streamId)}&country_id=${encodeURIComponent(params.countryId)}`;
  const res = await customFetch(`${V1}/regulatory/phases${qs}`, { method: "GET" });
  return unwrap<RegulatoryPhase[]>(res);
}

export async function listTasks(phaseId: string): Promise<RegulatoryTask[]> {
  const qs = `?phase_id=${encodeURIComponent(phaseId)}`;
  const res = await customFetch(`${V1}/regulatory/tasks${qs}`, { method: "GET" });
  return unwrap<RegulatoryTask[]>(res);
}

export async function listTaskTags(taskId: string): Promise<RegulatoryTag[]> {
  const res = await customFetch(`${V1}/regulatory/tasks/${taskId}/tags`, { method: "GET" });
  return unwrap<RegulatoryTag[]>(res);
}

export async function listPriorityNotes(phaseId: string): Promise<RegulatoryPriorityNote[]> {
  const res = await customFetch(`${V1}/regulatory/phases/${phaseId}/priority-notes`, {
    method: "GET",
  });
  return unwrap<RegulatoryPriorityNote[]>(res);
}

// ---------------------------------------------------------------------------
// Phase 2b — task-note helpers
// ---------------------------------------------------------------------------

export interface RegulatoryTaskNote {
  id: string;
  task_id: string;
  body: string;
  author_user_id: string;
  created_at: string;
}

export async function listTaskNotes(taskId: string): Promise<RegulatoryTaskNote[]> {
  const res = await customFetch(`${V1}/regulatory/tasks/${taskId}/notes`, {
    method: "GET",
  });
  return unwrap<RegulatoryTaskNote[]>(res);
}

export async function createTaskNote(
  taskId: string,
  body: string,
): Promise<RegulatoryTaskNote> {
  const res = await customFetch(`${V1}/regulatory/tasks/${taskId}/notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body }),
  });
  return unwrap<RegulatoryTaskNote>(res);
}

export async function deleteTaskNote(
  taskId: string,
  noteId: string,
): Promise<void> {
  await customFetch(`${V1}/regulatory/tasks/${taskId}/notes/${noteId}`, {
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// Phase 2b — task mutations
// ---------------------------------------------------------------------------

export async function toggleTask(taskId: string): Promise<RegulatoryTask> {
  const res = await customFetch(`${V1}/regulatory/tasks/${taskId}/toggle`, {
    method: "POST",
  });
  return unwrap<RegulatoryTask>(res);
}

export interface RegulatoryTaskUpdate {
  body?: string;
  note?: string | null;
  assignee_user_id?: string | null;
  due_date?: string | null;
  sort_order?: number;
}

export async function updateTask(
  taskId: string,
  payload: RegulatoryTaskUpdate,
): Promise<RegulatoryTask> {
  const res = await customFetch(`${V1}/regulatory/tasks/${taskId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return unwrap<RegulatoryTask>(res);
}

// ---------------------------------------------------------------------------
// Phase 2b — task-tag mutations
// ---------------------------------------------------------------------------

export interface RegulatoryTaskTagLink {
  task_id: string;
  tag_id: string;
  created_at: string;
}

export async function addTaskTag(
  taskId: string,
  tagId: string,
): Promise<RegulatoryTaskTagLink> {
  const res = await customFetch(`${V1}/regulatory/task-tags`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_id: taskId, tag_id: tagId }),
  });
  return unwrap<RegulatoryTaskTagLink>(res);
}

export async function removeTaskTag(
  taskId: string,
  tagId: string,
): Promise<void> {
  await customFetch(`${V1}/regulatory/task-tags/${taskId}/${tagId}`, {
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// Phase 2b — phase / task creation
// ---------------------------------------------------------------------------

export interface RegulatoryPhaseCreate {
  stream_id: string;
  country_id: string;
  name: string;
  badge_kind: string;
  timing_label?: string | null;
  sort_order?: number;
  default_open?: boolean;
}

export async function createPhase(
  payload: RegulatoryPhaseCreate,
): Promise<RegulatoryPhase> {
  const res = await customFetch(`${V1}/regulatory/phases`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return unwrap<RegulatoryPhase>(res);
}

export interface RegulatoryTaskCreate {
  phase_id: string;
  body: string;
  note?: string | null;
  assignee_user_id?: string | null;
  due_date?: string | null;
  sort_order?: number;
}

export async function createTask(
  payload: RegulatoryTaskCreate,
): Promise<RegulatoryTask> {
  const res = await customFetch(`${V1}/regulatory/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return unwrap<RegulatoryTask>(res);
}

// ---------------------------------------------------------------------------
// Phase 2b — Import HTML (admin)
// ---------------------------------------------------------------------------

export interface ImportHtmlSummary {
  countries_created: number;
  streams_created: number;
  streams_skipped_existing: number;
  phases_created: number;
  phases_skipped_existing: number;
  tasks_created: number;
  tasks_skipped_duplicate: number;
  tags_created: number;
  priority_notes_created: number;
}

export async function importTrackerHtml(
  file: File,
): Promise<ImportHtmlSummary> {
  const form = new FormData();
  form.append("file", file);
  // NOTE: do NOT set Content-Type — the browser sets it with the multipart
  // boundary parameter automatically when the body is a FormData instance.
  const res = await customFetch(`${V1}/regulatory/import-html`, {
    method: "POST",
    body: form,
  });
  return unwrap<ImportHtmlSummary>(res);
}

// ---------------------------------------------------------------------------
// Phase 2b — Authored snapshot (Path A: keeps IDs threaded through every
// level so mutation handlers in the page have something to point at). The
// public-snapshot contract (`loadCountrySnapshot` / `regulatory_public.py`)
// is deliberately untouched — Phase 3 marketing-site SSR keeps using it.
// ---------------------------------------------------------------------------

export interface AuthoredSnapshotTaskTag {
  id: string;
  slug: string;
  label: string;
  color_token: string;
}

export interface AuthoredSnapshotTask {
  id: string;
  body: string;
  note: string | null;
  completed: boolean;
  assignee_user_id: string | null;
  due_date: string | null;
  tags: AuthoredSnapshotTaskTag[];
}

export interface AuthoredSnapshotPriorityNote {
  id: string;
  body: string;
  severity: string;
}

export interface AuthoredSnapshotPhase {
  id: string;
  name: string;
  badge_kind: string;
  timing_label: string | null;
  default_open: boolean;
  priority_notes: AuthoredSnapshotPriorityNote[];
  tasks: AuthoredSnapshotTask[];
}

export interface AuthoredSnapshotStream {
  id: string;
  slug: string;
  name: string;
  color_token: string;
  description: string | null;
  timeline_label: string | null;
  totals: SnapshotTotals;
  phases: AuthoredSnapshotPhase[];
}

export interface AuthoredSnapshot {
  country: { id: string; code: string; display_label: string };
  totals: SnapshotTotals;
  streams: AuthoredSnapshotStream[];
}

export async function loadAuthoredSnapshot(
  countryCode: string,
): Promise<AuthoredSnapshot | null> {
  const countries = await listCountries();
  const country = countries.find((c) => c.code === countryCode);
  if (!country) return null;

  const streams = await listStreams(false);

  const snapshotStreams: AuthoredSnapshotStream[] = [];
  let grandTotal = 0;
  let grandDone = 0;

  for (const stream of streams) {
    const phases = await listPhases({
      streamId: stream.id,
      countryId: country.id,
    });

    const snapshotPhases: AuthoredSnapshotPhase[] = [];
    let streamTotal = 0;
    let streamDone = 0;

    for (const phase of phases) {
      const [tasks, priorityNotes] = await Promise.all([
        listTasks(phase.id),
        listPriorityNotes(phase.id),
      ]);

      const snapshotTasks: AuthoredSnapshotTask[] = [];
      for (const task of tasks) {
        const tags = await listTaskTags(task.id);
        snapshotTasks.push({
          id: task.id,
          body: task.body,
          note: task.note,
          completed: task.completed,
          assignee_user_id: task.assignee_user_id,
          due_date: task.due_date,
          tags: tags.map((t) => ({
            id: t.id,
            slug: t.slug,
            label: t.label,
            color_token: t.color_token,
          })),
        });
      }

      streamTotal += tasks.length;
      streamDone += tasks.filter((t) => t.completed).length;

      snapshotPhases.push({
        id: phase.id,
        name: phase.name,
        badge_kind: phase.badge_kind,
        timing_label: phase.timing_label,
        default_open: phase.default_open,
        priority_notes: priorityNotes.map((n) => ({
          id: n.id,
          body: n.body,
          severity: n.severity,
        })),
        tasks: snapshotTasks,
      });
    }

    grandTotal += streamTotal;
    grandDone += streamDone;

    snapshotStreams.push({
      id: stream.id,
      slug: stream.slug,
      name: stream.name,
      color_token: stream.color_token,
      description: stream.description,
      timeline_label: stream.timeline_label,
      totals: {
        tasks: streamTotal,
        completed: streamDone,
        percent: percent(streamDone, streamTotal),
      },
      phases: snapshotPhases,
    });
  }

  return {
    country: {
      id: country.id,
      code: country.code,
      display_label: country.display_label,
    },
    totals: {
      tasks: grandTotal,
      completed: grandDone,
      percent: percent(grandDone, grandTotal),
    },
    streams: snapshotStreams,
  };
}

// ---------------------------------------------------------------------------
// Aggregator — produces the public-snapshot shape from authenticated reads
// ---------------------------------------------------------------------------

const percent = (done: number, total: number): number =>
  total === 0 ? 0 : Math.round((done * 100) / total);

/**
 * Stitch streams + phases (filtered by country) + tasks + tags + priority
 * notes into a single nested payload identical to the public-snapshot
 * endpoint. Returns null when the requested country is not seeded for the
 * caller's org.
 *
 * Sequential per-stream/per-phase fetching is deliberate at v2 — keeps the
 * request graph readable and the row counts here are small (single-digit
 * streams, single-digit phases per stream). Promise.all per-stream is a
 * trivial follow-up if it ever feels slow.
 */
export async function loadCountrySnapshot(
  countryCode: string,
): Promise<CountrySnapshot | null> {
  const countries = await listCountries();
  const country = countries.find((c) => c.code === countryCode);
  if (!country) return null;

  const streams = await listStreams(false);

  const snapshotStreams: SnapshotStream[] = [];
  let grandTotal = 0;
  let grandDone = 0;

  for (const stream of streams) {
    const phases = await listPhases({
      streamId: stream.id,
      countryId: country.id,
    });

    const snapshotPhases: SnapshotPhase[] = [];
    let streamTotal = 0;
    let streamDone = 0;

    for (const phase of phases) {
      const [tasks, priorityNotes] = await Promise.all([
        listTasks(phase.id),
        listPriorityNotes(phase.id),
      ]);

      const snapshotTasks: SnapshotTask[] = [];
      for (const task of tasks) {
        const tags = await listTaskTags(task.id);
        snapshotTasks.push({
          body: task.body,
          completed: task.completed,
          tags: tags.map((t) => ({
            slug: t.slug,
            label: t.label,
            color_token: t.color_token,
          })),
        });
      }

      streamTotal += tasks.length;
      streamDone += tasks.filter((t) => t.completed).length;

      snapshotPhases.push({
        name: phase.name,
        badge_kind: phase.badge_kind,
        timing_label: phase.timing_label,
        default_open: phase.default_open,
        priority_notes: priorityNotes.map((n) => ({
          body: n.body,
          severity: n.severity,
        })),
        tasks: snapshotTasks,
      });
    }

    grandTotal += streamTotal;
    grandDone += streamDone;

    snapshotStreams.push({
      slug: stream.slug,
      name: stream.name,
      color_token: stream.color_token,
      description: stream.description,
      timeline_label: stream.timeline_label,
      totals: {
        tasks: streamTotal,
        completed: streamDone,
        percent: percent(streamDone, streamTotal),
      },
      phases: snapshotPhases,
    });
  }

  return {
    country: { code: country.code, display_label: country.display_label },
    totals: {
      tasks: grandTotal,
      completed: grandDone,
      percent: percent(grandDone, grandTotal),
    },
    streams: snapshotStreams,
  };
}
