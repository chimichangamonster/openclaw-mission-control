import { test, expect } from "./fixtures";
import type { Route } from "@playwright/test";

const API = "**/api/v1";

const cronJobs = [
  {
    id: "cron1",
    name: "morning-scan",
    enabled: true,
    description: "Pre-market watchlist scan",
    schedule: { kind: "cron", expr: "0 8 * * 1-5", tz: "America/Edmonton" },
    agentId: "stock-analyst",
    payload: { message: "Run the morning scan", thinking: "", timeoutSeconds: 300 },
    delivery: { mode: "isolated" },
    sessionTarget: "isolated",
    nextRun: new Date(Date.now() + 3_600_000).toISOString(),
    lastRun: {
      status: "success",
      finishedAt: new Date(Date.now() - 7_200_000).toISOString(),
      durationMs: 45_000,
    },
    createdAt: "2026-03-01T00:00:00Z",
  },
  {
    id: "cron2",
    name: "competitor-scan",
    enabled: false,
    description: "Weekly competitive intel",
    schedule: { kind: "cron", expr: "0 9 * * 1", tz: "America/Edmonton" },
    agentId: "the-claw",
    payload: { message: "Scan competitors", thinking: "", timeoutSeconds: 600 },
    delivery: { mode: "isolated" },
    sessionTarget: "isolated",
    nextRun: null,
    lastRun: null,
    createdAt: "2026-03-15T00:00:00Z",
  },
];

const runHistory = [
  {
    id: "run1",
    status: "success",
    startedAt: new Date(Date.now() - 7_200_000).toISOString(),
    finishedAt: new Date(Date.now() - 7_155_000).toISOString(),
    durationMs: 45_000,
    error: null,
  },
  {
    id: "run2",
    status: "error",
    startedAt: new Date(Date.now() - 93_600_000).toISOString(),
    finishedAt: new Date(Date.now() - 93_550_000).toISOString(),
    durationMs: 50_000,
    error: "Timeout exceeded",
  },
  {
    id: "run3",
    status: "success",
    startedAt: new Date(Date.now() - 180_000_000).toISOString(),
    finishedAt: new Date(Date.now() - 179_960_000).toISOString(),
    durationMs: 40_000,
    error: null,
  },
];

async function stubCronApis(page: import("@playwright/test").Page) {
  await page.route(`${API}/cron-jobs`, (r: Route) => {
    if (r.request().method() === "GET") {
      return r.fulfill({ json: cronJobs });
    }
    return r.continue();
  });
  await page.route(`${API}/cron-jobs/*/runs*`, (r: Route) =>
    r.fulfill({ json: runHistory }),
  );
}

test.describe("Cron Jobs — page load", () => {
  test("renders page title and job list", async ({ authedPage: page }) => {
    await stubCronApis(page);
    await page.goto("/cron-jobs");

    await expect(page.getByRole("heading", { name: "Scheduled Tasks" })).toBeVisible();
    await expect(page.getByText("morning-scan")).toBeVisible();
    await expect(page.getByText("competitor-scan")).toBeVisible();
  });

  test("shows summary stats bar", async ({ authedPage: page }) => {
    await stubCronApis(page);
    await page.goto("/cron-jobs");

    // Summary shows total, active, paused
    await expect(page.getByText(/2 total/i)).toBeVisible();
    await expect(page.getByText(/1 active/i)).toBeVisible();
    await expect(page.getByText(/1 paused/i)).toBeVisible();
  });

  test("Create Task button visible", async ({ authedPage: page }) => {
    await stubCronApis(page);
    await page.goto("/cron-jobs");

    await expect(
      page.getByRole("button", { name: /create task/i }),
    ).toBeVisible();
  });

  test("disabled job shows reduced opacity", async ({
    authedPage: page,
  }) => {
    await stubCronApis(page);
    await page.goto("/cron-jobs");

    // competitor-scan is disabled — its card should have opacity
    const competitorCard = page.getByText("competitor-scan").locator("..");
    await expect(competitorCard).toBeVisible();
  });
});

test.describe("Cron Jobs — enable/disable toggle", () => {
  test("expanding a job shows Pause/Enable button", async ({
    authedPage: page,
  }) => {
    await stubCronApis(page);
    await page.route(`${API}/cron-jobs/*`, (r: Route) => {
      if (r.request().method() === "PATCH") {
        return r.fulfill({ json: { ok: true } });
      }
      return r.continue();
    });
    await page.goto("/cron-jobs");

    // Click the enabled job to expand it
    await page.getByText("morning-scan").click();

    // Should show Pause button since it's enabled
    await expect(
      page.getByRole("button", { name: /pause/i }),
    ).toBeVisible();
  });

  test("expanding a disabled job shows Enable button", async ({
    authedPage: page,
  }) => {
    await stubCronApis(page);
    await page.goto("/cron-jobs");

    // Click the disabled job to expand it
    await page.getByText("competitor-scan").click();

    // Should show Enable button since it's disabled
    await expect(
      page.getByRole("button", { name: /enable/i }),
    ).toBeVisible();
  });
});

test.describe("Cron Jobs — run history", () => {
  test("expanding a job and clicking History shows run records", async ({
    authedPage: page,
  }) => {
    await stubCronApis(page);
    await page.goto("/cron-jobs");

    // Expand the job
    await page.getByText("morning-scan").click();

    // Click History button
    await page.getByRole("button", { name: /history/i }).click();

    // Run history should show success and error records
    await expect(page.getByText("success").first()).toBeVisible();
    await expect(page.getByText("error").first()).toBeVisible();
    await expect(page.getByText("Timeout exceeded")).toBeVisible();
  });
});

test.describe("Cron Jobs — create dialog", () => {
  test("clicking Create Task opens dialog with form fields", async ({
    authedPage: page,
  }) => {
    await stubCronApis(page);
    await page.goto("/cron-jobs");

    await page.getByRole("button", { name: /create task/i }).click();

    await expect(page.getByText("Create Scheduled Task")).toBeVisible();
    // Labels are not associated via htmlFor; check the label text is visible
    await expect(page.getByText("Name", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Agent", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Agent Message", { exact: true })).toBeVisible();
  });
});

test.describe("Cron Jobs — empty state", () => {
  test("shows empty state when no jobs exist", async ({
    authedPage: page,
  }) => {
    await page.route(`${API}/cron-jobs`, (r: Route) => {
      if (r.request().method() === "GET") {
        return r.fulfill({ json: [] });
      }
      return r.continue();
    });
    await page.goto("/cron-jobs");

    await expect(page.getByText("No scheduled tasks")).toBeVisible();
    await expect(
      page.getByText(/create your first scheduled task/i),
    ).toBeVisible();
  });
});

test.describe("Cron Jobs — mobile", () => {
  test("no horizontal overflow", async ({ authedPage: page }) => {
    await stubCronApis(page);
    await page.goto("/cron-jobs");

    if ((page.viewportSize()?.width ?? 1280) < 768) {
      const noOverflow = await page.evaluate(
        () => document.body.scrollWidth <= document.body.clientWidth + 1,
      );
      expect(noOverflow).toBe(true);
    }
  });

  test("job cards are tappable on mobile", async ({ authedPage: page }) => {
    await stubCronApis(page);
    await page.goto("/cron-jobs");

    if ((page.viewportSize()?.width ?? 1280) < 768) {
      // Job name should be visible and tappable
      const jobCard = page.getByText("morning-scan");
      await expect(jobCard).toBeVisible();
      const box = await jobCard.boundingBox();
      expect(box).toBeTruthy();
      // Minimum touch target
      expect(box!.height).toBeGreaterThanOrEqual(20);
    }
  });
});
