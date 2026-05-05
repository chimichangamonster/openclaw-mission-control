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
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

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
  };
});

import { loadCountrySnapshot } from "@/lib/regulatory-api";
import RegulatoryPage from "./page";

const mockedLoad = vi.mocked(loadCountrySnapshot);

const seededSnapshot = {
  country: { code: "CA", display_label: "Canada (Alberta Pilot)" },
  totals: { tasks: 3, completed: 1, percent: 33 },
  streams: [
    {
      slug: "navy",
      name: "Corporate Foundation",
      color_token: "navy",
      description: null,
      timeline_label: "Days 1-10",
      totals: { tasks: 3, completed: 1, percent: 33 },
      phases: [
        {
          name: "Incorporation",
          badge_kind: "corp",
          timing_label: "Days 1-3",
          default_open: true,
          priority_notes: [
            { body: "BLOCKING ITEM — articles must file first", severity: "critical" },
          ],
          tasks: [
            {
              body: "File articles of incorporation",
              completed: true,
              tags: [{ slug: "abca", label: "ABCA", color_token: "navy" }],
            },
            {
              body: "Open business bank account",
              completed: false,
              tags: [],
            },
            {
              body: "Register CRA business number",
              completed: false,
              tags: [{ slug: "cra", label: "CRA", color_token: "navy" }],
            },
          ],
        },
      ],
    },
  ],
};

describe("RegulatoryPage", () => {
  it("renders FeatureGate fallback when the regulatory flag is off", () => {
    flagsState.regulatory = false;
    membershipState.isAdmin = true;
    mockedLoad.mockResolvedValue(seededSnapshot);

    render(<RegulatoryPage />);

    expect(screen.getByText(/feature not enabled/i)).toBeInTheDocument();
    flagsState.regulatory = true; // restore for sibling tests
  });

  it("denies access to non-admin members even when the flag is on", async () => {
    flagsState.regulatory = true;
    membershipState.isAdmin = false;
    mockedLoad.mockResolvedValue(seededSnapshot);

    render(<RegulatoryPage />);

    expect(
      await screen.findByText(/admin access required/i),
    ).toBeInTheDocument();
    membershipState.isAdmin = true; // restore
  });

  it("renders streams, phases, tasks, and priority-notes for the seeded country", async () => {
    flagsState.regulatory = true;
    membershipState.isAdmin = true;
    mockedLoad.mockResolvedValue(seededSnapshot);

    render(<RegulatoryPage />);

    await waitFor(() =>
      expect(mockedLoad).toHaveBeenCalledWith("CA"),
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
    mockedLoad.mockResolvedValue(null);

    render(<RegulatoryPage />);

    expect(
      await screen.findByText(/not yet seeded/i),
    ).toBeInTheDocument();
  });
});
