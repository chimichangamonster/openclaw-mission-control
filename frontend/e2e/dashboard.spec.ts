import { test, expect } from "./fixtures";
import type { Route } from "@playwright/test";

const API = "**/api/v1";

const emptySeries = {
  primary: { range: "7d", bucket: "day", points: [] },
  comparison: { range: "7d", bucket: "day", points: [] },
};

const dashboardMetrics = {
  generated_at: new Date().toISOString(),
  range: "7d",
  kpis: {
    inbox_tasks: 3,
    in_progress_tasks: 2,
    review_tasks: 1,
    done_tasks: 10,
    tasks_in_progress: 2,
    active_agents: 4,
    error_rate_pct: 1.5,
    median_cycle_time_hours_7d: 12.3,
  },
  throughput: emptySeries,
  cycle_time: emptySeries,
  error_rate: emptySeries,
  wip: emptySeries,
  pending_approvals: { items: [], total: 0 },
};

async function stubDashboardApis(page: import("@playwright/test").Page) {
  await page.route(`${API}/metrics/dashboard*`, (r: Route) =>
    r.fulfill({ json: dashboardMetrics }),
  );
  await page.route(`${API}/boards*`, (r: Route) =>
    r.fulfill({ json: { items: [], total: 0 } }),
  );
  await page.route(`${API}/agents*`, (r: Route) =>
    r.fulfill({ json: { items: [], total: 0 } }),
  );
  await page.route(`${API}/activity*`, (r: Route) =>
    r.fulfill({ json: { items: [], total: 0 } }),
  );
  await page.route(`${API}/gateways/status*`, (r: Route) =>
    r.fulfill({ json: { gateways: [] } }),
  );
  await page.route(`${API}/board-groups*`, (r: Route) =>
    r.fulfill({ json: { items: [], total: 0 } }),
  );
}

// ---------------------------------------------------------------------------
// Dashboard widget stubs
// ---------------------------------------------------------------------------

function stubBudgetWidget(page: import("@playwright/test").Page) {
  // customFetch wraps as {data: <body>}, widget does raw?.data ?? raw
  return page.route(`${API}/cost-tracker/budget*`, (r: Route) =>
    r.fulfill({
      json: {
        config: { monthly_budget: 100 },
        status: {
          monthly_total: 42.5,
          monthly_pct: 42.5,
          remaining: 57.5,
          projected_month_end: 85,
          daily_avg: 1.42,
        },
        agent_today: [{ agent: "The Claw", cost: 12.3 }],
      },
    }),
  );
}

function stubCronWidget(page: import("@playwright/test").Page) {
  // Widget does raw?.data ?? raw then Array.isArray — return raw array
  return page.route(`${API}/cron-jobs`, (r: Route) => {
    if (r.request().method() === "GET") {
      return r.fulfill({
        json: [
          {
            id: "cron1",
            name: "morning-scan",
            enabled: true,
            agent_id: "stock-analyst",
            schedule_expr: "0 8 * * 1-5",
            next_run: new Date(Date.now() + 3_600_000).toISOString(),
            last_run: new Date().toISOString(),
            last_status: "success",
          },
          {
            id: "cron2",
            name: "competitor-scan",
            enabled: true,
            agent_id: "the-claw",
            schedule_expr: "0 9 * * 1",
            next_run: new Date(Date.now() + 86_400_000).toISOString(),
            last_run: new Date().toISOString(),
            last_status: "success",
          },
        ],
      });
    }
    return r.continue();
  });
}

function stubInvoicesWidget(page: import("@playwright/test").Page) {
  // Widget does raw?.data ?? raw then Array.isArray — return raw array
  return page.route(`${API}/invoices*`, (r: Route) =>
    r.fulfill({
      json: [
        { id: "inv1", status: "sent", total: 1500, currency: "CAD", due_date: null },
        { id: "inv2", status: "paid", total: 2000, currency: "CAD", due_date: null },
        { id: "inv3", status: "draft", total: 750, currency: "CAD", due_date: null },
      ],
    }),
  );
}

function stubCalendarWidget(page: import("@playwright/test").Page) {
  // Status widget does raw?.data ?? raw — return raw shape
  // Events widget does raw?.data ?? raw then data?.events ?? data
  return Promise.all([
    page.route(`${API}/google-calendar/status*`, (r: Route) =>
      r.fulfill({ json: { connected: true } }),
    ),
    page.route(`${API}/google-calendar/events*`, (r: Route) =>
      r.fulfill({
        json: [
          {
            id: "evt1",
            summary: "Team standup",
            start: new Date(Date.now() + 3_600_000).toISOString(),
            end: new Date(Date.now() + 5_400_000).toISOString(),
            location: "Zoom",
          },
          {
            id: "evt2",
            summary: "Client call",
            start: new Date(Date.now() + 86_400_000).toISOString(),
            end: new Date(Date.now() + 90_000_000).toISOString(),
            location: null,
          },
        ],
      }),
    ),
  ]);
}

// ===========================================================================
// Tests
// ===========================================================================

test.describe("Dashboard — core metrics", () => {
  test("renders top metric cards", async ({ authedPage: page }) => {
    await stubDashboardApis(page);
    await page.goto("/dashboard");

    await expect(page.getByText("Online Agents", { exact: true })).toBeVisible();
    await expect(page.getByText("Tasks In Progress", { exact: true })).toBeVisible();
    await expect(page.getByText("Error Rate", { exact: true })).toBeVisible();
    await expect(page.getByText("Completion Speed", { exact: true })).toBeVisible();
  });

  test("renders dashboard sections", async ({ authedPage: page }) => {
    await stubDashboardApis(page);
    await page.goto("/dashboard");

    await expect(page.getByRole("heading", { name: "Workload" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Throughput" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Gateway Health" })).toBeVisible();
  });
});

test.describe("Dashboard — feature-gated widgets", () => {
  test("budget widget renders spend data", async ({ authedPage: page }) => {
    await stubDashboardApis(page);
    await stubBudgetWidget(page);
    await page.goto("/dashboard");

    await expect(page.getByRole("heading", { name: /budget/i })).toBeVisible();
    await expect(page.getByText(/remaining/i)).toBeVisible();
  });

  test("cron widget shows active jobs", async ({ authedPage: page }) => {
    await stubDashboardApis(page);
    await stubCronWidget(page);
    await page.goto("/dashboard");

    await expect(page.getByText("CRON JOBS")).toBeVisible();
    await expect(page.getByText(/active job/i)).toBeVisible();
  });

  test("invoices widget shows outstanding count", async ({
    authedPage: page,
  }) => {
    await stubDashboardApis(page);
    await stubInvoicesWidget(page);
    await page.goto("/dashboard");

    await expect(page.getByRole("heading", { name: /invoices/i })).toBeVisible();
    await expect(page.getByText("outstanding invoices")).toBeVisible();
  });

  test("calendar widget shows upcoming events", async ({
    authedPage: page,
  }) => {
    await stubDashboardApis(page);
    await stubCalendarWidget(page);
    await page.goto("/dashboard");

    await expect(page.getByText("UPCOMING EVENTS")).toBeVisible();
    await expect(page.getByText("Team standup")).toBeVisible();
    await expect(page.getByText("Client call")).toBeVisible();
  });

  test("calendar widget shows 'no calendar connected' when disconnected", async ({
    page,
    stubApis,
  }) => {
    await stubApis({ featureFlags: { google_calendar: true } });
    await stubDashboardApis(page);
    await page.route(`${API}/google-calendar/status*`, (r: Route) =>
      r.fulfill({ json: { connected: false } }),
    );
    await page.goto("/dashboard");

    await expect(page.getByText(/no calendar connected/i)).toBeVisible();
  });
});

test.describe("Dashboard — sidebar", () => {
  test("desktop: sidebar visible, hamburger hidden", async ({
    authedPage: page,
  }) => {
    if ((page.viewportSize()?.width ?? 1280) < 768) {
      test.skip();
      return;
    }
    await stubDashboardApis(page);
    await page.goto("/dashboard");

    await expect(page.locator("aside")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Toggle navigation" }),
    ).toBeHidden();
  });

  test("mobile: sidebar hidden, hamburger visible", async ({
    authedPage: page,
  }) => {
    await stubDashboardApis(page);
    await page.goto("/dashboard");

    // Mobile projects (Pixel 7, iPhone 14) already set small viewport
    if ((page.viewportSize()?.width ?? 1280) < 768) {
      await expect(
        page.getByRole("button", { name: "Toggle navigation" }),
      ).toBeVisible();
      // Sidebar uses CSS translate, check data attribute instead
      await expect(page.locator("[data-sidebar]")).toHaveAttribute(
        "data-sidebar",
        "closed",
      );
    }
  });
});

test.describe("Dashboard — mobile layout", () => {
  test("no horizontal overflow", async ({ authedPage: page }) => {
    await stubDashboardApis(page);
    await page.goto("/dashboard");

    if ((page.viewportSize()?.width ?? 1280) < 768) {
      const overflow = await page.evaluate(() => {
        return document.body.scrollWidth <= document.body.clientWidth + 1;
      });
      expect(overflow).toBe(true);
    }
  });

  test("metric cards visible on mobile", async ({ authedPage: page }) => {
    await stubDashboardApis(page);
    await page.goto("/dashboard");

    if ((page.viewportSize()?.width ?? 1280) < 768) {
      await expect(page.getByText("Online Agents")).toBeVisible();
      await expect(page.getByText("Tasks In Progress")).toBeVisible();
    }
  });
});
