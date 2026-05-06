/**
 * /grants page smoke tests (item 107 v2 Phase 2).
 *
 * Test-first per `feedback_test_before_deploy.md`. Cases written before
 * page.tsx + grants-detail-drawer.tsx + grants-api.ts ship.
 *
 * Aggregate strategy: backend `GET /grants` returns `list[GrantRead]` (no
 * aggregates). The page fetches `GET /grants/{id}` in parallel for each
 * grant to compute stat strip totals and per-grant next-deadline countdowns.
 * With N small (Magnetik: 5 programs, Vantage: future SR&ED ~1-2) this is
 * fine. If N grows, add a list-aggregates endpoint then.
 *
 * Coverage scope:
 * - Feature gate: page renders gate fallback when `grants_tracker` flag off.
 * - Admin guard: non-admin members see a denial banner.
 * - Stat strip: aggregates committed (sum of awarded_amount) vs drawn-to-date
 *   (sum of drawn_amount across draws) across multiple grants.
 * - Active grants table: row per grant with countdown badge — red <14d,
 *   amber <30d. Computed from earliest upcoming reporting deadline.
 * - Detail drawer: clicking a row opens drawer (uses already-fetched detail).
 * - Burn chart: aggregates target_amount vs drawn_amount across draws.
 * - Prerequisites section: lists task_body + completion + /regulatory link.
 *
 * Determinism posture per `feedback_determinism_first_for_high_liability.md`:
 * zero LLM. All amounts/dates/statuses operator-typed; rendering deterministic.
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

const flagsState = { grants_tracker: true };
vi.mock("@/lib/use-feature-flags", () => ({
  useFeatureFlags: () => ({
    flags: flagsState,
    isLoading: false,
    isFeatureEnabled: (f: string) =>
      Boolean(flagsState[f as keyof typeof flagsState]),
  }),
}));

const membershipState = { isAdmin: true };
vi.mock("@/lib/use-organization-membership", () => ({
  useOrganizationMembership: () => ({
    member: { role: "admin" },
    isAdmin: membershipState.isAdmin,
  }),
}));

vi.mock("@/lib/grants-api", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/grants-api")>("@/lib/grants-api");
  return {
    ...actual,
    listGrants: vi.fn(),
    getGrantDetail: vi.fn(),
  };
});

import { getGrantDetail, listGrants } from "@/lib/grants-api";
import GrantsPage from "./page";

const mockedList = vi.mocked(listGrants);
const mockedDetail = vi.mocked(getGrantDetail);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const TODAY_ISO = "2026-05-06";

const baseGrantEra = {
  id: "grant-era",
  organization_id: "org-magnetik",
  granting_body: "Emissions Reduction Alberta",
  program_name: "Industrial Transformation Challenge",
  application_template_slug: "era-industrial-transformation",
  application_status: "drafting",
  submitted_at: null,
  decision_at: null,
  awarded_amount: "750000.00",
  matched_funding_amount: null,
  total_project_value: null,
  currency: "CAD",
  project_start_date: null,
  project_end_date: null,
  incorporation_required_entity: "Magnetik Solutions Inc.",
  cash_coinvestment_required_pct: null,
  cash_coinvestment_source: null,
  contact_person: null,
  contact_email: null,
  owner_user_id: null,
  notes_md: null,
  created_at: "2026-05-04T00:00:00Z",
  updated_at: "2026-05-04T00:00:00Z",
};

const baseGrantAbi = {
  id: "grant-abi",
  organization_id: "org-magnetik",
  granting_body: "Alberta Innovates",
  program_name: "SME Grant",
  application_template_slug: "alberta-innovates",
  application_status: "drafting",
  submitted_at: null,
  decision_at: null,
  awarded_amount: "250000.00",
  matched_funding_amount: null,
  total_project_value: null,
  currency: "CAD",
  project_start_date: null,
  project_end_date: null,
  incorporation_required_entity: "Magnetik Solutions Inc.",
  cash_coinvestment_required_pct: "25.00",
  cash_coinvestment_source: "Steve cash $300K",
  contact_person: null,
  contact_email: null,
  owner_user_id: null,
  notes_md: null,
  created_at: "2026-05-04T00:00:00Z",
  updated_at: "2026-05-04T00:00:00Z",
};

const renderPage = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <GrantsPage />
    </QueryClientProvider>,
  );
};

afterEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe("GrantsPage", () => {
  it("renders FeatureGate fallback when grants_tracker flag is off", () => {
    flagsState.grants_tracker = false;
    membershipState.isAdmin = true;
    mockedList.mockResolvedValue([]);

    renderPage();

    expect(screen.getByText(/feature not enabled/i)).toBeInTheDocument();
    flagsState.grants_tracker = true;
  });

  it("denies access to non-admin members even when the flag is on", async () => {
    flagsState.grants_tracker = true;
    membershipState.isAdmin = false;
    mockedList.mockResolvedValue([]);

    renderPage();

    expect(
      await screen.findByText(/admin access required/i),
    ).toBeInTheDocument();
    membershipState.isAdmin = true;
  });

  it("aggregates committed (awarded) vs drawn-to-date across grants in the stat strip", async () => {
    // ERA: awarded $750K, drawn $200K (one draw). ABI: awarded $250K, drawn $0.
    // Expected committed = $1,000,000 ; drawn = $200,000.
    flagsState.grants_tracker = true;
    membershipState.isAdmin = true;
    mockedList.mockResolvedValue([baseGrantEra, baseGrantAbi]);
    mockedDetail.mockImplementation(async (id: string) => {
      if (id === "grant-era") {
        return {
          ...baseGrantEra,
          draws: [
            {
              id: "draw-era-1",
              grant_id: "grant-era",
              milestone_label: "Kickoff",
              target_date: "2026-06-01",
              target_amount: "200000.00",
              drawn_at: "2026-04-15",
              drawn_amount: "200000.00",
              status: "received",
              sort_order: 0,
              notes_md: null,
              created_at: "",
              updated_at: "",
            },
          ],
          deadlines: [],
          prerequisites: [],
        };
      }
      return {
        ...baseGrantAbi,
        draws: [],
        deadlines: [],
        prerequisites: [],
      };
    });

    renderPage();

    expect(
      await screen.findByText(/1[,.]000[,.]000/),
    ).toBeInTheDocument();
    expect(screen.getByText(/200[,.]000/)).toBeInTheDocument();
  });

  it("renders countdown badge red (<14d) for the earliest upcoming deadline of a grant", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(`${TODAY_ISO}T12:00:00Z`));

    flagsState.grants_tracker = true;
    membershipState.isAdmin = true;
    mockedList.mockResolvedValue([baseGrantEra]);
    mockedDetail.mockResolvedValue({
      ...baseGrantEra,
      draws: [],
      deadlines: [
        {
          id: "dl-era-1",
          grant_id: "grant-era",
          deadline_date: "2026-05-13", // 7 days from TODAY_ISO
          deadline_type: "interim_report",
          description: null,
          status: "upcoming",
          submitted_at: null,
          submitted_artifact_url: null,
          sort_order: 0,
          notes_md: null,
          created_at: "",
          updated_at: "",
        },
      ],
      prerequisites: [],
    });

    renderPage();

    const badge = await screen.findByTestId("deadline-badge-grant-era");
    expect(badge.className).toMatch(/red|critical|danger/i);
    expect(badge.textContent).toMatch(/7\s*d/);
  });

  it("renders countdown badge amber (<30d) for grants whose deadline is 14-29 days away", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date(`${TODAY_ISO}T12:00:00Z`));

    flagsState.grants_tracker = true;
    membershipState.isAdmin = true;
    mockedList.mockResolvedValue([baseGrantAbi]);
    mockedDetail.mockResolvedValue({
      ...baseGrantAbi,
      draws: [],
      deadlines: [
        {
          id: "dl-abi-1",
          grant_id: "grant-abi",
          deadline_date: "2026-05-26", // 20 days from TODAY_ISO
          deadline_type: "interim_report",
          description: null,
          status: "upcoming",
          submitted_at: null,
          submitted_artifact_url: null,
          sort_order: 0,
          notes_md: null,
          created_at: "",
          updated_at: "",
        },
      ],
      prerequisites: [],
    });

    renderPage();

    const badge = await screen.findByTestId("deadline-badge-grant-abi");
    expect(badge.className).toMatch(/amber|warn|warning/i);
    expect(badge.textContent).toMatch(/20\s*d/);
  });

  it("opens the detail drawer when a grant row is clicked", async () => {
    flagsState.grants_tracker = true;
    membershipState.isAdmin = true;
    mockedList.mockResolvedValue([baseGrantEra]);
    mockedDetail.mockResolvedValue({
      ...baseGrantEra,
      draws: [],
      deadlines: [],
      prerequisites: [],
    });

    renderPage();

    const row = await screen.findByText(/Industrial Transformation Challenge/i);
    fireEvent.click(row);

    await waitFor(() =>
      expect(mockedDetail).toHaveBeenCalledWith("grant-era"),
    );
    expect(
      await screen.findByRole("button", { name: /close/i }),
    ).toBeInTheDocument();
  });

  it("burn chart aggregates target vs drawn across draws of the selected grant", async () => {
    flagsState.grants_tracker = true;
    membershipState.isAdmin = true;
    mockedList.mockResolvedValue([baseGrantEra]);
    mockedDetail.mockResolvedValue({
      ...baseGrantEra,
      draws: [
        {
          id: "draw-1",
          grant_id: "grant-era",
          milestone_label: "Kickoff",
          target_date: "2026-06-01",
          target_amount: "150000.00",
          drawn_at: "2026-04-15",
          drawn_amount: "150000.00",
          status: "received",
          sort_order: 0,
          notes_md: null,
          created_at: "",
          updated_at: "",
        },
        {
          id: "draw-2",
          grant_id: "grant-era",
          milestone_label: "Milestone 1",
          target_date: "2026-09-01",
          target_amount: "300000.00",
          drawn_at: null,
          drawn_amount: null,
          status: "pending",
          sort_order: 1,
          notes_md: null,
          created_at: "",
          updated_at: "",
        },
      ],
      deadlines: [],
      prerequisites: [],
    });

    renderPage();
    fireEvent.click(
      await screen.findByText(/Industrial Transformation Challenge/i),
    );

    // Burn chart targets total $450K, drawn total $150K.
    await waitFor(() =>
      expect(mockedDetail).toHaveBeenCalledWith("grant-era"),
    );
    expect(await screen.findByText(/450[,.]000/)).toBeInTheDocument();
    // Drawn appears in stat strip + drawer; assert at least one occurrence.
    expect(screen.getAllByText(/150[,.]000/).length).toBeGreaterThan(0);
  });

  it("renders prerequisites section with task_body, completion status, and link back to /regulatory", async () => {
    flagsState.grants_tracker = true;
    membershipState.isAdmin = true;
    mockedList.mockResolvedValue([baseGrantEra]);
    mockedDetail.mockResolvedValue({
      ...baseGrantEra,
      draws: [],
      deadlines: [],
      prerequisites: [
        {
          grant_id: "grant-era",
          regulatory_task_id: "task-1",
          label_override: null,
          is_critical: true,
          created_at: "2026-05-04T00:00:00Z",
          task_body: "File articles of incorporation",
          task_completed: false,
        },
        {
          grant_id: "grant-era",
          regulatory_task_id: "task-2",
          label_override: null,
          is_critical: false,
          created_at: "2026-05-04T00:00:00Z",
          task_body: "Open business bank account",
          task_completed: true,
        },
      ],
    });

    renderPage();
    fireEvent.click(
      await screen.findByText(/Industrial Transformation Challenge/i),
    );

    expect(
      await screen.findByText(/File articles of incorporation/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Open business bank account/i)).toBeInTheDocument();

    const links = screen.getAllByRole("link");
    expect(
      links.some((a) => a.getAttribute("href")?.startsWith("/regulatory")),
    ).toBe(true);
  });

  // -------------------------------------------------------------------------
  // Item 118 sub-A — amount label semantics by application_status.
  //
  // The Grant model column is `awarded_amount` but the field holds different
  // semantics across the lifecycle:
  //   planned | drafting | submitted | under_review  →  "Requested"  (target)
  //   awarded | completed                            →  "Awarded"    (confirmed)
  //   declined | withdrawn                           →  "Was requested"
  //
  // Stat-strip "committed" sum is honest only when grants are post-award.
  // Pre-award, the page shows "Requested" both in the stat-strip card label
  // and in the table column header + drawer metadata cell.
  // -------------------------------------------------------------------------

  it("labels amount as 'Requested' (not 'Awarded') for grants in pre-award status", async () => {
    flagsState.grants_tracker = true;
    membershipState.isAdmin = true;
    mockedList.mockResolvedValue([
      { ...baseGrantEra, application_status: "drafting" },
    ]);
    mockedDetail.mockResolvedValue({
      ...baseGrantEra,
      application_status: "drafting",
      draws: [],
      deadlines: [],
      prerequisites: [],
    });

    renderPage();

    // Stat-strip card label flips to "Total requested" when no grants are
    // post-award yet.
    expect(
      await screen.findByText(/total requested/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/total committed/i)).toBeNull();

    // Table column header shows "Requested" (await render).
    expect(
      await screen.findByRole("columnheader", { name: /^requested$/i }),
    ).toBeInTheDocument();
  });

  it("labels amount as 'Awarded' for grants in post-award status (awarded | completed)", async () => {
    flagsState.grants_tracker = true;
    membershipState.isAdmin = true;
    mockedList.mockResolvedValue([
      { ...baseGrantEra, application_status: "awarded" },
    ]);
    mockedDetail.mockResolvedValue({
      ...baseGrantEra,
      application_status: "awarded",
      draws: [],
      deadlines: [],
      prerequisites: [],
    });

    renderPage();

    // Stat-strip card label is "Total awarded" when at least one grant is
    // post-award.
    expect(await screen.findByText(/total awarded/i)).toBeInTheDocument();
    expect(screen.queryByText(/total requested/i)).toBeNull();

    // Table column header shows "Awarded".
    expect(
      await screen.findByRole("columnheader", { name: /^awarded$/i }),
    ).toBeInTheDocument();
  });

  it("uses 'Total awarded' on stat strip when mixed pre-award + post-award grants exist", async () => {
    // Mix: ERA drafting ($750K requested) + ABI awarded ($250K confirmed).
    // Stat strip should label as "Total awarded" because at least one grant
    // is post-award. Sum stays $1M; the label shift is the visible change.
    flagsState.grants_tracker = true;
    membershipState.isAdmin = true;
    mockedList.mockResolvedValue([
      { ...baseGrantEra, application_status: "drafting" },
      { ...baseGrantAbi, application_status: "awarded" },
    ]);
    mockedDetail.mockImplementation(async (id: string) => {
      const base = id === "grant-era" ? baseGrantEra : baseGrantAbi;
      const status = id === "grant-era" ? "drafting" : "awarded";
      return {
        ...base,
        application_status: status,
        draws: [],
        deadlines: [],
        prerequisites: [],
      };
    });

    renderPage();

    expect(await screen.findByText(/total awarded/i)).toBeInTheDocument();
    expect(screen.queryByText(/total requested/i)).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Item 118 sub-C — program_url field renders as external-link affordance.
  //
  // Each grant program has a public landing page operators paste into emails,
  // RFPs, partner pitches. The Grant model has a `program_url` column; UI
  // surfaces it as a small external-link icon next to the program name in
  // the table row + drawer header. Null program_url renders no icon.
  // -------------------------------------------------------------------------

  it("renders external-link icon next to program name when program_url is set", async () => {
    flagsState.grants_tracker = true;
    membershipState.isAdmin = true;
    mockedList.mockResolvedValue([
      {
        ...baseGrantEra,
        program_url: "https://eralberta.ca/funding/industrial-transformation-challenge/",
      },
    ]);
    mockedDetail.mockResolvedValue({
      ...baseGrantEra,
      program_url: "https://eralberta.ca/funding/industrial-transformation-challenge/",
      draws: [],
      deadlines: [],
      prerequisites: [],
    });

    renderPage();

    // Table cell wraps the program name with an anchor pointing at program_url.
    const links = await screen.findAllByRole("link");
    const programLink = links.find(
      (a) =>
        a.getAttribute("href") ===
        "https://eralberta.ca/funding/industrial-transformation-challenge/",
    );
    expect(programLink).toBeDefined();
    expect(programLink?.getAttribute("target")).toBe("_blank");
    expect(programLink?.getAttribute("rel")).toMatch(/noopener/i);
  });

  it("renders no external-link icon when program_url is null", async () => {
    flagsState.grants_tracker = true;
    membershipState.isAdmin = true;
    mockedList.mockResolvedValue([{ ...baseGrantEra, program_url: null }]);
    mockedDetail.mockResolvedValue({
      ...baseGrantEra,
      program_url: null,
      draws: [],
      deadlines: [],
      prerequisites: [],
    });

    renderPage();

    await screen.findByText(/Industrial Transformation/i);

    // No external link should exist (only internal /regulatory anchor in
    // prereq map renders, and that's empty here).
    const links = screen.queryAllByRole("link");
    const externalLinks = links.filter((a) =>
      a.getAttribute("href")?.startsWith("http"),
    );
    expect(externalLinks.length).toBe(0);
  });

  it("renders external-link icon in drawer header when program_url is set", async () => {
    flagsState.grants_tracker = true;
    membershipState.isAdmin = true;
    mockedList.mockResolvedValue([
      {
        ...baseGrantEra,
        program_url: "https://eralberta.ca/funding/industrial-transformation-challenge/",
      },
    ]);
    mockedDetail.mockResolvedValue({
      ...baseGrantEra,
      program_url: "https://eralberta.ca/funding/industrial-transformation-challenge/",
      draws: [],
      deadlines: [],
      prerequisites: [],
    });

    renderPage();
    fireEvent.click(
      await screen.findByText(/Industrial Transformation Challenge/i),
    );

    // Drawer renders, header link present. May appear in both table + drawer.
    await waitFor(() =>
      expect(mockedDetail).toHaveBeenCalledWith("grant-era"),
    );

    const links = screen.getAllByRole("link");
    const programLinks = links.filter(
      (a) =>
        a.getAttribute("href") ===
        "https://eralberta.ca/funding/industrial-transformation-challenge/",
    );
    // At minimum 2 occurrences: one in table cell, one in drawer header.
    expect(programLinks.length).toBeGreaterThanOrEqual(2);
  });
});
