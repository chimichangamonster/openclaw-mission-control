/**
 * Regulatory API helper tests (item 101 v2 Phase 2a).
 *
 * Locks the contract for `loadCountrySnapshot()` — the aggregator that
 * stitches streams + phases + tasks + tags + priority-notes into a single
 * nested shape. The shape MUST match `regulatory_public.py`'s public-snapshot
 * payload so Phase 3 marketing-site SSR can share types.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  addTaskTag,
  createPhase,
  createTask,
  createTaskNote,
  deleteTaskNote,
  importTrackerHtml,
  listTaskNotes,
  loadAuthoredSnapshot,
  loadCountrySnapshot,
  removeTaskTag,
  toggleTask,
  updateTask,
} from "./regulatory-api";

vi.mock("@/api/mutator", () => ({
  customFetch: vi.fn(),
}));

import { customFetch } from "@/api/mutator";

const mockedFetch = vi.mocked(customFetch);

afterEach(() => {
  mockedFetch.mockReset();
});

describe("loadCountrySnapshot", () => {
  it("returns null when the requested country is not seeded for the org", async () => {
    mockedFetch.mockImplementation(async (url: string) => {
      if (url.endsWith("/regulatory/countries")) {
        return { data: [] };
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    const result = await loadCountrySnapshot("CA");
    expect(result).toBeNull();
  });

  it("aggregates streams/phases/tasks/tags/priority-notes into the public-snapshot shape", async () => {
    const country = {
      id: "country-1",
      organization_id: "org-1",
      code: "CA",
      name: "Canada",
      status: "active",
      display_label: "Canada (Alberta Pilot)",
      sort_order: 0,
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-05-01T00:00:00Z",
    };
    const stream = {
      id: "stream-1",
      organization_id: "org-1",
      slug: "navy",
      name: "Corporate Foundation",
      description: "Corp setup",
      color_token: "navy",
      budget_estimate: null,
      regulator_label: null,
      timeline_label: "Days 1-10",
      sort_order: 0,
      archived: false,
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-05-01T00:00:00Z",
    };
    const phase = {
      id: "phase-1",
      stream_id: "stream-1",
      country_id: "country-1",
      name: "Incorporation",
      badge_kind: "corp",
      timing_label: "Days 1-3",
      sort_order: 0,
      default_open: true,
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-05-01T00:00:00Z",
    };
    const taskDone = {
      id: "task-1",
      phase_id: "phase-1",
      body: "File articles of incorporation",
      note: null,
      completed: true,
      completed_at: "2026-05-02T00:00:00Z",
      completed_by_user_id: "user-1",
      assignee_user_id: null,
      due_date: null,
      sort_order: 0,
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-05-02T00:00:00Z",
    };
    const taskTodo = {
      id: "task-2",
      phase_id: "phase-1",
      body: "Open business bank account",
      note: "TD or RBC",
      completed: false,
      completed_at: null,
      completed_by_user_id: null,
      assignee_user_id: null,
      due_date: null,
      sort_order: 1,
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-05-01T00:00:00Z",
    };
    const tag = {
      id: "tag-1",
      organization_id: "org-1",
      slug: "abca",
      label: "ABCA",
      color_token: "navy",
      kind: "corporate",
      created_at: "2026-05-01T00:00:00Z",
    };
    const priorityNote = {
      id: "pn-1",
      phase_id: "phase-1",
      body: "BLOCKING ITEM",
      severity: "critical",
      sort_order: 0,
      created_at: "2026-05-01T00:00:00Z",
    };

    mockedFetch.mockImplementation(async (url: string) => {
      if (url.endsWith("/regulatory/countries")) {
        return { data: [country] };
      }
      if (url.endsWith("/regulatory/streams")) {
        return { data: [stream] };
      }
      if (url.includes("/regulatory/phases?")) {
        return { data: [phase] };
      }
      if (url.includes("/regulatory/tasks?")) {
        return { data: [taskDone, taskTodo] };
      }
      if (url.endsWith(`/regulatory/tasks/${taskDone.id}/tags`)) {
        return { data: [tag] };
      }
      if (url.endsWith(`/regulatory/tasks/${taskTodo.id}/tags`)) {
        return { data: [] };
      }
      if (url.endsWith(`/regulatory/phases/${phase.id}/priority-notes`)) {
        return { data: [priorityNote] };
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    const snapshot = await loadCountrySnapshot("CA");

    expect(snapshot).not.toBeNull();
    expect(snapshot!.country.code).toBe("CA");
    expect(snapshot!.country.display_label).toBe("Canada (Alberta Pilot)");
    expect(snapshot!.totals).toEqual({ tasks: 2, completed: 1, percent: 50 });
    expect(snapshot!.streams).toHaveLength(1);

    const streamOut = snapshot!.streams[0];
    expect(streamOut.slug).toBe("navy");
    expect(streamOut.color_token).toBe("navy");
    expect(streamOut.totals).toEqual({ tasks: 2, completed: 1, percent: 50 });
    expect(streamOut.phases).toHaveLength(1);

    const phaseOut = streamOut.phases[0];
    expect(phaseOut.name).toBe("Incorporation");
    expect(phaseOut.badge_kind).toBe("corp");
    expect(phaseOut.default_open).toBe(true);
    expect(phaseOut.priority_notes).toEqual([
      { body: "BLOCKING ITEM", severity: "critical" },
    ]);
    expect(phaseOut.tasks).toHaveLength(2);

    const [t1, t2] = phaseOut.tasks;
    expect(t1.body).toBe("File articles of incorporation");
    expect(t1.completed).toBe(true);
    expect(t1.tags).toEqual([
      { slug: "abca", label: "ABCA", color_token: "navy" },
    ]);
    expect(t2.body).toBe("Open business bank account");
    expect(t2.completed).toBe(false);
    expect(t2.tags).toEqual([]);
  });

  it("computes 0% when a country has no tasks", async () => {
    const country = {
      id: "country-1",
      organization_id: "org-1",
      code: "CA",
      name: "Canada",
      status: "active",
      display_label: "Canada",
      sort_order: 0,
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-05-01T00:00:00Z",
    };

    mockedFetch.mockImplementation(async (url: string) => {
      if (url.endsWith("/regulatory/countries")) return { data: [country] };
      if (url.endsWith("/regulatory/streams")) return { data: [] };
      throw new Error(`unexpected fetch: ${url}`);
    });

    const snapshot = await loadCountrySnapshot("CA");
    expect(snapshot!.totals).toEqual({ tasks: 0, completed: 0, percent: 0 });
    expect(snapshot!.streams).toEqual([]);
  });

  it("filters phases by both stream_id and country_id (cross-country isolation)", async () => {
    const country = {
      id: "country-ca",
      organization_id: "org-1",
      code: "CA",
      name: "Canada",
      status: "active",
      display_label: "Canada",
      sort_order: 0,
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-05-01T00:00:00Z",
    };
    const stream = {
      id: "stream-1",
      organization_id: "org-1",
      slug: "navy",
      name: "Corporate",
      description: null,
      color_token: "navy",
      budget_estimate: null,
      regulator_label: null,
      timeline_label: null,
      sort_order: 0,
      archived: false,
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-05-01T00:00:00Z",
    };

    const fetchedUrls: string[] = [];
    mockedFetch.mockImplementation(async (url: string) => {
      fetchedUrls.push(url);
      if (url.endsWith("/regulatory/countries")) return { data: [country] };
      if (url.endsWith("/regulatory/streams")) return { data: [stream] };
      if (url.includes("/regulatory/phases?")) return { data: [] };
      throw new Error(`unexpected fetch: ${url}`);
    });

    await loadCountrySnapshot("CA");

    const phasesUrl = fetchedUrls.find((u) => u.includes("/regulatory/phases?"));
    expect(phasesUrl).toBeDefined();
    expect(phasesUrl).toContain("stream_id=stream-1");
    expect(phasesUrl).toContain("country_id=country-ca");
  });
});

// ---------------------------------------------------------------------------
// Phase 2b — authored (with-IDs) snapshot
// ---------------------------------------------------------------------------

describe("loadAuthoredSnapshot (item 115 — single-endpoint aggregator)", () => {
  it("calls /regulatory/snapshot/authored/{code} once and returns the response", async () => {
    // Item 115 contract: ONE round-trip, not the prior 100+ walker.
    // Backend stitches the tree; frontend trusts the shape.
    const aggregatedSnapshot = {
      country: { id: "country-1", code: "CA", display_label: "Canada" },
      totals: { tasks: 1, completed: 0, percent: 0 },
      streams: [
        {
          id: "stream-1",
          slug: "navy",
          name: "Corporate",
          color_token: "navy",
          description: null,
          timeline_label: null,
          totals: { tasks: 1, completed: 0, percent: 0 },
          phases: [
            {
              id: "phase-1",
              name: "Incorporation",
              badge_kind: "corp",
              timing_label: null,
              default_open: true,
              priority_notes: [
                { id: "pn-1", body: "BLOCKING", severity: "critical" },
              ],
              tasks: [
                {
                  id: "task-1",
                  body: "File articles",
                  note: null,
                  completed: false,
                  assignee_user_id: null,
                  due_date: null,
                  tags: [
                    {
                      id: "tag-1",
                      slug: "abca",
                      label: "ABCA",
                      color_token: "navy",
                    },
                  ],
                },
              ],
            },
          ],
        },
      ],
    };

    const seenUrls: string[] = [];
    mockedFetch.mockImplementation(async (url: string) => {
      seenUrls.push(url);
      if (url.includes("/regulatory/snapshot/authored/CA")) {
        return { data: aggregatedSnapshot, status: 200 };
      }
      throw new Error(`unexpected fetch: ${url}`);
    });

    const snapshot = await loadAuthoredSnapshot("CA");

    // Single round-trip — locks the contract that broke the prior 10s load.
    expect(seenUrls).toHaveLength(1);
    expect(seenUrls[0]).toContain("/regulatory/snapshot/authored/CA");

    // Shape preserves IDs at every level (admin edit affordances depend on them).
    expect(snapshot).not.toBeNull();
    expect(snapshot!.country.id).toBe("country-1");
    expect(snapshot!.streams[0].id).toBe("stream-1");
    expect(snapshot!.streams[0].phases[0].id).toBe("phase-1");
    const t = snapshot!.streams[0].phases[0].tasks[0];
    expect(t.id).toBe("task-1");
    expect(t.note).toBeNull();
    expect(t.assignee_user_id).toBeNull();
    expect(t.due_date).toBeNull();
    expect(t.tags[0].id).toBe("tag-1");
    const pn = snapshot!.streams[0].phases[0].priority_notes[0];
    expect(pn.id).toBe("pn-1");
  });

  it("returns null on 404 (country not seeded for the org)", async () => {
    mockedFetch.mockImplementation(async (url: string) => {
      if (url.includes("/regulatory/snapshot/authored/")) {
        return { data: null, status: 404 };
      }
      throw new Error(`unexpected fetch: ${url}`);
    });
    const snapshot = await loadAuthoredSnapshot("CA");
    expect(snapshot).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Phase 2b — mutation helpers
// ---------------------------------------------------------------------------

describe("toggleTask", () => {
  it("POSTs to /regulatory/tasks/{id}/toggle and returns the updated task", async () => {
    const updated = {
      id: "task-1",
      phase_id: "phase-1",
      body: "x",
      note: null,
      completed: true,
      completed_at: "2026-05-05T00:00:00Z",
      completed_by_user_id: "user-1",
      assignee_user_id: null,
      due_date: null,
      sort_order: 0,
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-05-05T00:00:00Z",
    };
    mockedFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      expect(url).toBe("/api/v1/regulatory/tasks/task-1/toggle");
      expect(init?.method).toBe("POST");
      return { data: updated };
    });
    const result = await toggleTask("task-1");
    expect(result.completed).toBe(true);
    expect(result.completed_by_user_id).toBe("user-1");
  });
});

describe("updateTask", () => {
  it("PATCHes /regulatory/tasks/{id} with only present fields", async () => {
    let bodySent: unknown = null;
    mockedFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      expect(url).toBe("/api/v1/regulatory/tasks/task-1");
      expect(init?.method).toBe("PATCH");
      bodySent = init?.body
        ? JSON.parse(init.body as string)
        : null;
      return { data: { id: "task-1" } };
    });
    await updateTask("task-1", {
      assignee_user_id: "user-2",
      due_date: "2026-06-01T00:00:00Z",
    });
    expect(bodySent).toEqual({
      assignee_user_id: "user-2",
      due_date: "2026-06-01T00:00:00Z",
    });
  });
});

describe("task notes helpers", () => {
  it("listTaskNotes GETs /regulatory/tasks/{id}/notes", async () => {
    const notes = [
      {
        id: "note-1",
        task_id: "task-1",
        body: "Spoke with Henry",
        author_user_id: "user-1",
        created_at: "2026-05-05T00:00:00Z",
      },
    ];
    mockedFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      expect(url).toBe("/api/v1/regulatory/tasks/task-1/notes");
      expect(init?.method).toBe("GET");
      return { data: notes };
    });
    const result = await listTaskNotes("task-1");
    expect(result).toHaveLength(1);
    expect(result[0].body).toBe("Spoke with Henry");
  });

  it("createTaskNote POSTs body to /regulatory/tasks/{id}/notes", async () => {
    let bodySent: unknown = null;
    mockedFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      expect(url).toBe("/api/v1/regulatory/tasks/task-1/notes");
      expect(init?.method).toBe("POST");
      bodySent = init?.body ? JSON.parse(init.body as string) : null;
      return {
        data: {
          id: "note-new",
          task_id: "task-1",
          body: "New note",
          author_user_id: "user-1",
          created_at: "2026-05-05T00:00:00Z",
        },
      };
    });
    const result = await createTaskNote("task-1", "New note");
    expect(bodySent).toEqual({ body: "New note" });
    expect(result.id).toBe("note-new");
  });

  it("deleteTaskNote DELETEs /regulatory/tasks/{taskId}/notes/{noteId}", async () => {
    mockedFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      expect(url).toBe("/api/v1/regulatory/tasks/task-1/notes/note-1");
      expect(init?.method).toBe("DELETE");
      return { data: null };
    });
    await deleteTaskNote("task-1", "note-1");
  });
});

describe("task tag mutations", () => {
  it("addTaskTag POSTs {task_id, tag_id} to /regulatory/task-tags", async () => {
    let bodySent: unknown = null;
    mockedFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      expect(url).toBe("/api/v1/regulatory/task-tags");
      expect(init?.method).toBe("POST");
      bodySent = init?.body ? JSON.parse(init.body as string) : null;
      return {
        data: {
          task_id: "task-1",
          tag_id: "tag-1",
          created_at: "2026-05-05T00:00:00Z",
        },
      };
    });
    await addTaskTag("task-1", "tag-1");
    expect(bodySent).toEqual({ task_id: "task-1", tag_id: "tag-1" });
  });

  it("removeTaskTag DELETEs /regulatory/task-tags/{taskId}/{tagId}", async () => {
    mockedFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      expect(url).toBe("/api/v1/regulatory/task-tags/task-1/tag-1");
      expect(init?.method).toBe("DELETE");
      return { data: null };
    });
    await removeTaskTag("task-1", "tag-1");
  });
});

describe("createPhase / createTask", () => {
  it("createPhase POSTs to /regulatory/phases", async () => {
    let bodySent: unknown = null;
    mockedFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      expect(url).toBe("/api/v1/regulatory/phases");
      expect(init?.method).toBe("POST");
      bodySent = init?.body ? JSON.parse(init.body as string) : null;
      return {
        data: {
          id: "phase-new",
          stream_id: "stream-1",
          country_id: "country-1",
          name: "New phase",
          badge_kind: "now",
          timing_label: null,
          sort_order: 0,
          default_open: false,
          created_at: "2026-05-05T00:00:00Z",
          updated_at: "2026-05-05T00:00:00Z",
        },
      };
    });
    const result = await createPhase({
      stream_id: "stream-1",
      country_id: "country-1",
      name: "New phase",
      badge_kind: "now",
      timing_label: null,
      sort_order: 0,
      default_open: false,
    });
    expect(bodySent).toMatchObject({
      stream_id: "stream-1",
      country_id: "country-1",
      name: "New phase",
      badge_kind: "now",
    });
    expect(result.id).toBe("phase-new");
  });

  it("createTask POSTs to /regulatory/tasks", async () => {
    let bodySent: unknown = null;
    mockedFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      expect(url).toBe("/api/v1/regulatory/tasks");
      expect(init?.method).toBe("POST");
      bodySent = init?.body ? JSON.parse(init.body as string) : null;
      return {
        data: {
          id: "task-new",
          phase_id: "phase-1",
          body: "Hi",
          note: null,
          completed: false,
          completed_at: null,
          completed_by_user_id: null,
          assignee_user_id: null,
          due_date: null,
          sort_order: 0,
          created_at: "2026-05-05T00:00:00Z",
          updated_at: "2026-05-05T00:00:00Z",
        },
      };
    });
    const result = await createTask({
      phase_id: "phase-1",
      body: "Hi",
      note: null,
      sort_order: 0,
    });
    expect(bodySent).toMatchObject({
      phase_id: "phase-1",
      body: "Hi",
    });
    expect(result.id).toBe("task-new");
  });
});

describe("importTrackerHtml", () => {
  it("POSTs multipart FormData with the file under 'file' field", async () => {
    let urlCalled = "";
    let methodCalled = "";
    let bodyCalled: unknown = null;
    mockedFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      urlCalled = url;
      methodCalled = init?.method ?? "";
      bodyCalled = init?.body ?? null;
      return {
        data: {
          countries_created: 1,
          streams_created: 4,
          streams_skipped_existing: 0,
          phases_created: 12,
          phases_skipped_existing: 0,
          tasks_created: 80,
          tasks_skipped_duplicate: 0,
          tags_created: 6,
          priority_notes_created: 3,
        },
      };
    });
    const file = new File(["<html></html>"], "tracker.html", {
      type: "text/html",
    });
    const summary = await importTrackerHtml(file);
    expect(urlCalled).toBe("/api/v1/regulatory/import-html");
    expect(methodCalled).toBe("POST");
    expect(bodyCalled).toBeInstanceOf(FormData);
    expect((bodyCalled as FormData).get("file")).toBe(file);
    expect(summary.tasks_created).toBe(80);
  });
});
