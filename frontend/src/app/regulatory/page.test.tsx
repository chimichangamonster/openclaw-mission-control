/**
 * /regulatory page smoke tests (item 101 v2 Phase 2a).
 *
 * Coverage scope:
 * - Feature gate: page renders gate fallback when `regulatory` flag is off.
 * - Admin guard: non-admin members see a denial banner.
 * - Happy path: admin + flag on + Canada seeded → renders streams, phases,
 *   tasks, priority notes, and per-stream + grand totals.
 *
 * Edit affordances are Phase 2b — this file does not exercise mutations.
 */

import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/auth/clerk", () => ({
  useAuth: () => ({ isSignedIn: true }),
}));

vi.mock("@/components/templates/DashboardPageLayout", () => ({
  DashboardPageLayout: ({
    children,
    title,
  }: {
    children: React.ReactNode;
    title?: string;
  }) => (
    <div data-testid="dashboard-shell">
      {title && <h1>{title}</h1>}
      {children}
    </div>
  ),
}));

const flagsState = { regulatory: true };
vi.mock("@/lib/use-feature-flags", () => ({
  useFeatureFlags: () => ({
    flags: flagsState,
    isLoading: false,
    isFeatureEnabled: (f: string) => Boolean(flagsState[f as keyof typeof flagsState]),
  }),
}));

const membershipState = { isAdmin: true };
vi.mock("@/lib/use-organization-membership", () => ({
  useOrganizationMembership: () => ({
    member: { role: "admin" },
    isAdmin: membershipState.isAdmin,
  }),
}));

vi.mock("@/lib/regulatory-api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/regulatory-api")>(
    "@/lib/regulatory-api",
  );
  return {
    ...actual,
    loadCountrySnapshot: vi.fn(),
    loadAuthoredSnapshot: vi.fn(),
    listTags: vi.fn(),
    listStreams: vi.fn(),
    listCountries: vi.fn(),
    toggleTask: vi.fn(),
    importTrackerHtml: vi.fn(),
    createPhase: vi.fn(),
    updatePhase: vi.fn(),
    createTask: vi.fn(),
    listTaskNotes: vi.fn(),
  };
});

vi.mock("@/lib/use-org-members", () => ({
  useOrgMembers: () => ({
    members: [
      { user_id: "user-1", name: "Henry", email: "henry@example.com" },
      { user_id: "user-2", name: "Samir", email: "samir@example.com" },
    ],
  }),
}));

import {
  createPhase,
  createTask,
  importTrackerHtml,
  listCountries,
  listStreams,
  listTags,
  listTaskNotes,
  loadAuthoredSnapshot,
  toggleTask,
  updatePhase,
} from "@/lib/regulatory-api";
import RegulatoryPage from "./page";

const mockedAuthored = vi.mocked(loadAuthoredSnapshot);
const mockedListTags = vi.mocked(listTags);
const mockedListStreams = vi.mocked(listStreams);
const mockedListCountries = vi.mocked(listCountries);
const mockedToggle = vi.mocked(toggleTask);
const mockedImport = vi.mocked(importTrackerHtml);
const mockedCreatePhase = vi.mocked(createPhase);
const mockedUpdatePhase = vi.mocked(updatePhase);
const mockedCreateTask = vi.mocked(createTask);
const mockedListNotes = vi.mocked(listTaskNotes);

const seededSnapshot = {
  country: {
    id: "country-1",
    code: "CA",
    display_label: "Canada (Alberta Pilot)",
  },
  totals: { tasks: 3, completed: 1, percent: 33 },
  streams: [
    {
      id: "stream-1",
      slug: "navy",
      name: "Corporate Foundation",
      color_token: "navy",
      description: null,
      timeline_label: "Days 1-10",
      totals: { tasks: 3, completed: 1, percent: 33 },
      phases: [
        {
          id: "phase-1",
          name: "Incorporation",
          badge_kind: "corp",
          timing_label: "Days 1-3",
          default_open: true,
          priority_notes: [
            {
              id: "pn-1",
              body: "BLOCKING ITEM — articles must file first",
              severity: "critical",
            },
          ],
          tasks: [
            {
              id: "task-1",
              body: "File articles of incorporation",
              note: null,
              completed: true,
              assignee_user_id: null,
              due_date: null,
              tags: [
                { id: "tag-1", slug: "abca", label: "ABCA", color_token: "navy" },
              ],
            },
            {
              id: "task-2",
              body: "Open business bank account",
              note: null,
              completed: false,
              assignee_user_id: null,
              due_date: null,
              tags: [],
            },
            {
              id: "task-3",
              body: "Register CRA business number",
              note: null,
              completed: false,
              assignee_user_id: null,
              due_date: null,
              tags: [
                { id: "tag-2", slug: "cra", label: "CRA", color_token: "navy" },
              ],
            },
          ],
        },
      ],
    },
  ],
};

// All renders wrap in a fresh QueryClientProvider — the page now uses
// useMutation for toggle/notes which requires the provider in context.
const renderPage = () => {
  // listTags is queried unconditionally for admins. Default it to [] so the
  // Phase 2a tests don't trip a "Query data cannot be undefined" warning.
  if (!mockedListTags.getMockImplementation()) {
    mockedListTags.mockResolvedValue([]);
  }
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <RegulatoryPage />
    </QueryClientProvider>,
  );
};

describe("RegulatoryPage", () => {
  it("renders FeatureGate fallback when the regulatory flag is off", () => {
    flagsState.regulatory = false;
    membershipState.isAdmin = true;
    mockedAuthored.mockResolvedValue(seededSnapshot);

    renderPage();

    expect(screen.getByText(/feature not enabled/i)).toBeInTheDocument();
    flagsState.regulatory = true; // restore for sibling tests
  });

  it("denies access to non-admin members even when the flag is on", async () => {
    flagsState.regulatory = true;
    membershipState.isAdmin = false;
    mockedAuthored.mockResolvedValue(seededSnapshot);

    renderPage();

    expect(
      await screen.findByText(/admin access required/i),
    ).toBeInTheDocument();
    membershipState.isAdmin = true; // restore
  });

  it("renders streams, phases, tasks, and priority-notes for the seeded country", async () => {
    flagsState.regulatory = true;
    membershipState.isAdmin = true;
    mockedAuthored.mockResolvedValue(seededSnapshot);

    renderPage();

    await waitFor(() =>
      expect(mockedAuthored).toHaveBeenCalledWith("CA"),
    );

    expect(
      await screen.findByText(/Corporate Foundation/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Incorporation/)).toBeInTheDocument();
    expect(
      screen.getByText(/File articles of incorporation/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Open business bank account/)).toBeInTheDocument();
    expect(
      screen.getByText(/BLOCKING ITEM — articles must file first/),
    ).toBeInTheDocument();
    // Stream-level + grand totals both surface "33%" — assert at least one shows.
    expect(screen.getAllByText(/33%/).length).toBeGreaterThan(0);
  });

  it("shows a 'not yet seeded' empty state when Canada has no data", async () => {
    flagsState.regulatory = true;
    membershipState.isAdmin = true;
    mockedAuthored.mockResolvedValue(null);

    renderPage();

    expect(
      await screen.findByText(/not yet seeded/i),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Phase 2b — edit affordances on /regulatory
//
// We render the page wrapped in QueryClientProvider so useMutation works.
// The page is expected to call `loadAuthoredSnapshot` (with IDs) instead of
// `loadCountrySnapshot` whenever it intends to mount edit affordances —
// keeping the public-snapshot contract pristine.
// ---------------------------------------------------------------------------

const authoredSnapshot = {
  country: {
    id: "country-1",
    code: "CA",
    display_label: "Canada (Alberta Pilot)",
  },
  totals: { tasks: 2, completed: 0, percent: 0 },
  streams: [
    {
      id: "stream-1",
      slug: "navy",
      name: "Corporate Foundation",
      color_token: "navy",
      description: null,
      timeline_label: "Days 1-10",
      totals: { tasks: 2, completed: 0, percent: 0 },
      phases: [
        {
          id: "phase-1",
          name: "Incorporation",
          badge_kind: "corp",
          timing_label: "Days 1-3",
          default_open: true,
          priority_notes: [],
          tasks: [
            {
              id: "task-1",
              body: "File articles of incorporation",
              note: null,
              completed: false,
              assignee_user_id: null,
              due_date: null,
              tags: [],
            },
            {
              id: "task-2",
              body: "Open business bank account",
              note: null,
              completed: false,
              assignee_user_id: null,
              due_date: null,
              tags: [],
            },
          ],
        },
      ],
    },
  ],
};

const renderPhase2b = () => {
  flagsState.regulatory = true;
  membershipState.isAdmin = true;
  mockedAuthored.mockResolvedValue(JSON.parse(JSON.stringify(authoredSnapshot)));
  mockedListTags.mockResolvedValue([
    { id: "tag-1", organization_id: "org-1", slug: "td", label: "TD", color_token: "navy", kind: "vendor", created_at: "" },
  ]);
  mockedListStreams.mockResolvedValue([
    {
      id: "stream-1",
      organization_id: "org-1",
      slug: "navy",
      name: "Corporate Foundation",
      description: null,
      color_token: "navy",
      budget_estimate: null,
      regulator_label: null,
      timeline_label: null,
      sort_order: 0,
      archived: false,
      created_at: "",
      updated_at: "",
    },
  ]);
  mockedListCountries.mockResolvedValue([
    {
      id: "country-1",
      organization_id: "org-1",
      code: "CA",
      name: "Canada",
      status: "active",
      display_label: "Canada (Alberta Pilot)",
      sort_order: 0,
      created_at: "",
      updated_at: "",
    },
  ]);
  mockedListNotes.mockResolvedValue([]);
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <RegulatoryPage />
    </QueryClientProvider>,
  );
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("RegulatoryPage — Phase 2b edit affordances", () => {
  it("calls toggleTask when a task checkbox is clicked", async () => {
    mockedToggle.mockResolvedValue({
      id: "task-1",
      phase_id: "phase-1",
      body: "File articles of incorporation",
      note: null,
      completed: true,
      completed_at: "2026-05-05T00:00:00Z",
      completed_by_user_id: "user-1",
      assignee_user_id: null,
      due_date: null,
      sort_order: 0,
      created_at: "",
      updated_at: "",
    });
    renderPhase2b();

    const checkbox = await screen.findByRole("checkbox", {
      name: /file articles of incorporation/i,
    });
    fireEvent.click(checkbox);

    await waitFor(() => expect(mockedToggle).toHaveBeenCalledWith("task-1"));
  });

  it("opens the detail panel when a task body is clicked", async () => {
    renderPhase2b();
    const taskBody = await screen.findByText(/Open business bank account/);
    fireEvent.click(taskBody);
    expect(
      await screen.findByRole("button", { name: /close panel/i }),
    ).toBeInTheDocument();
  });

  it("Expand All opens every collapsed phase block", async () => {
    renderPhase2b();
    await screen.findByText(/Corporate Foundation/);
    fireEvent.click(screen.getByRole("button", { name: /expand all/i }));
    // Both task bodies should be visible (they live inside the open phase block).
    expect(
      screen.getByText(/File articles of incorporation/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Open business bank account/)).toBeInTheDocument();
  });

  it("Import HTML button opens a modal that POSTs the file via importTrackerHtml", async () => {
    mockedImport.mockResolvedValue({
      countries_created: 0,
      streams_created: 0,
      streams_skipped_existing: 1,
      phases_created: 0,
      phases_skipped_existing: 1,
      tasks_created: 5,
      tasks_skipped_duplicate: 0,
      tags_created: 0,
      priority_notes_created: 0,
    });
    renderPhase2b();
    await screen.findByText(/Corporate Foundation/);

    fireEvent.click(screen.getByRole("button", { name: /import html/i }));
    const fileInput = (await screen.findByLabelText(
      /tracker html file/i,
    )) as HTMLInputElement;
    const file = new File(["<html></html>"], "tracker.html", {
      type: "text/html",
    });
    fireEvent.change(fileInput, { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: /^import$/i }));

    await waitFor(() => expect(mockedImport).toHaveBeenCalledTimes(1));
    expect(mockedImport.mock.calls[0][0]).toBe(file);
  });

  it("Add Phase form submits createPhase with the entered fields", async () => {
    mockedCreatePhase.mockResolvedValue({
      id: "phase-new",
      stream_id: "stream-1",
      country_id: "country-1",
      name: "Bank Setup",
      badge_kind: "now",
      timing_label: null,
      sort_order: 0,
      default_open: false,
      created_at: "",
      updated_at: "",
    });
    renderPhase2b();
    await screen.findByText(/Corporate Foundation/);

    fireEvent.click(screen.getByRole("button", { name: /add phase/i }));
    const nameField = await screen.findByLabelText(/phase name/i);
    fireEvent.change(nameField, { target: { value: "Bank Setup" } });
    fireEvent.click(screen.getByRole("button", { name: /^create phase$/i }));

    await waitFor(() =>
      expect(mockedCreatePhase).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Bank Setup", country_id: "country-1" }),
      ),
    );
  });

  it("Add Task form submits createTask with the entered fields", async () => {
    mockedCreateTask.mockResolvedValue({
      id: "task-new",
      phase_id: "phase-1",
      body: "Send AOI to bank",
      note: null,
      completed: false,
      completed_at: null,
      completed_by_user_id: null,
      assignee_user_id: null,
      due_date: null,
      sort_order: 0,
      created_at: "",
      updated_at: "",
    });
    renderPhase2b();
    await screen.findByText(/Corporate Foundation/);

    // Add Task buttons are scoped to each phase; use the first one.
    fireEvent.click(screen.getAllByRole("button", { name: /add task/i })[0]);
    const bodyField = await screen.findByLabelText(/task body/i);
    fireEvent.change(bodyField, { target: { value: "Send AOI to bank" } });
    fireEvent.click(screen.getByRole("button", { name: /^create task$/i }));

    await waitFor(() =>
      expect(mockedCreateTask).toHaveBeenCalledWith(
        expect.objectContaining({
          phase_id: "phase-1",
          body: "Send AOI to bank",
        }),
      ),
    );
  });

  // -------------------------------------------------------------------------
  // Item 114 — inline edit of phase name
  // -------------------------------------------------------------------------

  it("clicking the phase-name edit button reveals an input pre-filled with the current name", async () => {
    renderPhase2b();
    await screen.findByText(/Incorporation/);

    fireEvent.click(
      screen.getByRole("button", { name: /^rename incorporation$/i }),
    );

    const nameInput = (await screen.findByLabelText(
      /rename phase/i,
    )) as HTMLInputElement;
    expect(nameInput.value).toBe("Incorporation");
  });

  it("blurring the phase-name input persists the new name via updatePhase", async () => {
    mockedUpdatePhase.mockResolvedValue({
      id: "phase-1",
      stream_id: "stream-1",
      country_id: "country-1",
      name: "Incorporation Filing",
      badge_kind: "corp",
      timing_label: "Days 1-3",
      sort_order: 0,
      default_open: true,
      created_at: "",
      updated_at: "",
    });
    renderPhase2b();
    await screen.findByText(/Incorporation/);

    fireEvent.click(
      screen.getByRole("button", { name: /^rename incorporation$/i }),
    );
    const nameInput = (await screen.findByLabelText(
      /rename phase/i,
    )) as HTMLInputElement;
    fireEvent.change(nameInput, { target: { value: "Incorporation Filing" } });
    fireEvent.blur(nameInput);

    await waitFor(() =>
      expect(mockedUpdatePhase).toHaveBeenCalledWith("phase-1", {
        name: "Incorporation Filing",
      }),
    );
  });
});
