/**
 * Regulatory API helper tests (item 101 v2 Phase 2a).
 *
 * Locks the contract for `loadCountrySnapshot()` — the aggregator that
 * stitches streams + phases + tasks + tags + priority-notes into a single
 * nested shape. The shape MUST match `regulatory_public.py`'s public-snapshot
 * payload so Phase 3 marketing-site SSR can share types.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { loadCountrySnapshot } from "./regulatory-api";

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
