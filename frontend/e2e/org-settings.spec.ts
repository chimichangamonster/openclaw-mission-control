import { test, expect } from "./fixtures";
import type { Route } from "@playwright/test";

const API = "**/api/v1";

const baseSettings = {
  openrouter_api_key: null,
  has_openrouter_key: true,
  openrouter_management_key: null,
  has_management_key: false,
  adobe_pdf_client_id: null,
  has_adobe_pdf_key: false,
  default_model_tier_max: 3,
  configured_models: [],
  feature_flags: { email: true, cron_jobs: true },
  agent_defaults: {},
  branding: {},
  logo_url: null,
  has_logo: false,
  has_custom_llm_endpoint: false,
  custom_llm_endpoint_name: null,
  custom_llm_endpoint_url: null,
  data_policy: {
    redaction_level: "moderate",
    allow_email_content_to_llm: false,
    log_llm_inputs: false,
  },
  timezone: "America/Edmonton",
  location: "Edmonton, AB",
};

const costEstimate = {
  tier_costs: [
    { tier: "Tier 1 Nano", per_conversation: 0.0003 },
    { tier: "Tier 2 Standard", per_conversation: 0.001 },
    { tier: "Tier 3 Reasoning", per_conversation: 0.02 },
  ],
  has_real_data: false,
  projected_monthly: 0,
  days_tracked: 0,
  daily_avg: 0,
  total_spend_to_date: 0,
};

async function stubOrgSettingsApis(
  page: import("@playwright/test").Page,
  role = "owner",
) {
  const isAdmin = role === "owner" || role === "admin";
  await page.route(`${API}/organization-settings`, (r: Route) =>
    r.fulfill({
      json: { ...baseSettings, member_role: role, is_admin: isAdmin },
    }),
  );
  await page.route(`${API}/organization-settings/audit-log*`, (r: Route) =>
    r.fulfill({ json: { entries: [], total: 0 } }),
  );
  await page.route(`${API}/organization-settings/llm-routing*`, (r: Route) =>
    r.fulfill({
      json: {
        configured: false,
        source: null,
        name: null,
        api_url: null,
        is_openrouter: false,
        models: [],
        data_stays_private: false,
      },
    }),
  );
  await page.route(`${API}/cost-tracker/cost-estimate*`, (r: Route) =>
    r.fulfill({ json: costEstimate }),
  );
}

test.describe("Org Settings — admin view", () => {
  test("renders API Keys section", async ({ authedPage: page }) => {
    await stubOrgSettingsApis(page);
    await page.goto("/org-settings");

    await expect(page.getByRole("heading", { name: "API Keys" })).toBeVisible();
  });

  test("renders Feature Flags section", async ({ authedPage: page }) => {
    await stubOrgSettingsApis(page);
    await page.goto("/org-settings");

    await expect(page.getByText("Feature Flags", { exact: true }).first()).toBeVisible();
  });

  test("renders Data Policy section", async ({ authedPage: page }) => {
    await stubOrgSettingsApis(page);
    await page.goto("/org-settings");

    await expect(page.getByRole("heading", { name: "Data Policy" })).toBeVisible();
  });

  test("renders Cost Calculator section", async ({ authedPage: page }) => {
    await stubOrgSettingsApis(page);
    await page.goto("/org-settings");

    await expect(page.getByText("AI Cost Calculator")).toBeVisible();
  });
});

test.describe("Org Settings — mobile", () => {
  test("no horizontal overflow", async ({ authedPage: page }) => {
    await stubOrgSettingsApis(page);
    await page.goto("/org-settings");

    if ((page.viewportSize()?.width ?? 1280) < 768) {
      const noOverflow = await page.evaluate(
        () => document.body.scrollWidth <= document.body.clientWidth + 1,
      );
      expect(noOverflow).toBe(true);
    }
  });

  test("sidebar hidden, hamburger visible", async ({
    authedPage: page,
  }) => {
    await stubOrgSettingsApis(page);
    await page.goto("/org-settings");

    if ((page.viewportSize()?.width ?? 1280) < 768) {
      // Sidebar is off-screen via CSS translate, check data attribute instead
      await expect(page.locator("[data-sidebar]")).toHaveAttribute(
        "data-sidebar",
        "closed",
      );
      await expect(
        page.getByRole("button", { name: "Toggle navigation" }),
      ).toBeVisible();
    }
  });
});
