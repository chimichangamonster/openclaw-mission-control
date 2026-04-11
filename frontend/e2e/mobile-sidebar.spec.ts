import { test, expect } from "./fixtures";
import type { Route } from "@playwright/test";

const API = "**/api/v1";

const emptySeries = {
  primary: { range: "7d", bucket: "day", points: [] },
  comparison: { range: "7d", bucket: "day", points: [] },
};

async function stubMinimalApis(page: import("@playwright/test").Page) {
  await page.route(`${API}/metrics/dashboard*`, (r: Route) =>
    r.fulfill({
      json: {
        generated_at: new Date().toISOString(),
        range: "7d",
        kpis: {
          inbox_tasks: 0,
          in_progress_tasks: 0,
          review_tasks: 0,
          done_tasks: 0,
          tasks_in_progress: 0,
          active_agents: 0,
          error_rate_pct: 0,
          median_cycle_time_hours_7d: null,
        },
        throughput: emptySeries,
        cycle_time: emptySeries,
        error_rate: emptySeries,
        wip: emptySeries,
        pending_approvals: { items: [], total: 0 },
      },
    }),
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

// Only run sidebar tests on mobile viewport projects
test.describe("Mobile sidebar", () => {
  test("hamburger visible, sidebar hidden by default", async ({
    authedPage: page,
  }) => {
    await stubMinimalApis(page);
    await page.goto("/dashboard");

    if ((page.viewportSize()?.width ?? 1280) >= 768) {
      test.skip();
      return;
    }

    await expect(
      page.getByRole("button", { name: "Toggle navigation" }),
    ).toBeVisible();
    await expect(page.locator("[data-sidebar]")).toHaveAttribute(
      "data-sidebar",
      "closed",
    );
    // Sidebar uses CSS translate (not display:none) — check data attribute
    // instead of visibility since Playwright considers translated elements visible
  });

  test("clicking hamburger opens sidebar with backdrop", async ({
    authedPage: page,
  }) => {
    await stubMinimalApis(page);
    await page.goto("/dashboard");

    if ((page.viewportSize()?.width ?? 1280) >= 768) {
      test.skip();
      return;
    }

    await page.getByRole("button", { name: "Toggle navigation" }).click();

    await expect(page.locator("[data-sidebar]")).toHaveAttribute(
      "data-sidebar",
      "open",
    );
    await expect(page.locator("aside")).toBeVisible();
    await expect(page.locator("[data-cy='sidebar-backdrop']")).toBeVisible();
  });

  test("clicking backdrop closes sidebar", async ({ authedPage: page }) => {
    await stubMinimalApis(page);
    await page.goto("/dashboard");

    if ((page.viewportSize()?.width ?? 1280) >= 768) {
      test.skip();
      return;
    }

    // Open
    await page.getByRole("button", { name: "Toggle navigation" }).click();
    await expect(page.locator("[data-sidebar]")).toHaveAttribute(
      "data-sidebar",
      "open",
    );

    // Click backdrop
    await page.locator("[data-cy='sidebar-backdrop']").click({ force: true });

    await expect(page.locator("[data-sidebar]")).toHaveAttribute(
      "data-sidebar",
      "closed",
    );
  });

  test("pressing Escape closes sidebar", async ({ authedPage: page }) => {
    await stubMinimalApis(page);
    await page.goto("/dashboard");

    if ((page.viewportSize()?.width ?? 1280) >= 768) {
      test.skip();
      return;
    }

    // Open
    await page.getByRole("button", { name: "Toggle navigation" }).click();
    await expect(page.locator("[data-sidebar]")).toHaveAttribute(
      "data-sidebar",
      "open",
    );

    // Press Escape
    await page.keyboard.press("Escape");

    await expect(page.locator("[data-sidebar]")).toHaveAttribute(
      "data-sidebar",
      "closed",
    );
  });

  test("clicking a nav link closes sidebar", async ({
    authedPage: page,
  }) => {
    await stubMinimalApis(page);
    await page.goto("/dashboard");

    if ((page.viewportSize()?.width ?? 1280) >= 768) {
      test.skip();
      return;
    }

    // Open
    await page.getByRole("button", { name: "Toggle navigation" }).click();
    await expect(page.locator("aside")).toBeVisible();

    // Click a nav link
    await page.locator("aside").getByRole("link", { name: "Chat" }).click();

    // Sidebar should close after navigation
    await expect(page.locator("[data-sidebar]")).toHaveAttribute(
      "data-sidebar",
      "closed",
    );
  });

  test("desktop: sidebar always visible, no hamburger", async ({
    authedPage: page,
  }) => {
    await stubMinimalApis(page);
    await page.goto("/dashboard");

    if ((page.viewportSize()?.width ?? 1280) < 768) {
      test.skip();
      return;
    }

    await expect(page.locator("aside")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Toggle navigation" }),
    ).toBeHidden();
  });
});
