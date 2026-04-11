import { test as base, type Page, type Route } from "@playwright/test";

const LOCAL_AUTH_TOKEN =
  "playwright-local-auth-token-0123456789-0123456789-0123456789x";
const STORAGE_KEY = "mc_local_auth_token";

/** Seed session storage with a local-auth token and dismiss welcome modal. */
async function seedAuth(page: Page) {
  await page.addInitScript(
    ({ key, token }: { key: string; token: string }) => {
      window.sessionStorage.setItem(key, token);
      // Dismiss the WelcomeModal so it doesn't block tests
      window.localStorage.setItem("vantageclaw_welcome_dismissed", "1");
    },
    { key: STORAGE_KEY, token: LOCAL_AUTH_TOKEN },
  );
}

// ---------------------------------------------------------------------------
// Shared API stub data
// ---------------------------------------------------------------------------

export const STUB_USER = {
  id: "u1",
  clerk_user_id: "local-auth-user",
  email: "local-auth-user@example.com",
  name: "Local User",
  preferred_name: "Local User",
  timezone: "UTC",
};

export const STUB_ORG = {
  id: "org1",
  name: "Testing Org",
  is_active: true,
  role: "owner",
};

export const STUB_MEMBERSHIP = {
  id: "membership-1",
  organization_id: "org1",
  user_id: "u1",
  role: "owner",
  all_boards_read: true,
  all_boards_write: true,
  board_access: [],
};

const API = "**/api/v1";

/** Intercept the common endpoints that every authenticated page needs. */
async function stubCommonApis(
  page: Page,
  opts: { featureFlags?: Record<string, boolean>; orgRole?: string } = {},
) {
  const role = opts.orgRole ?? "owner";
  const flags = opts.featureFlags ?? {
    email: true,
    cron_jobs: true,
    cost_tracker: true,
    bookkeeping: true,
    google_calendar: true,
    pentest: true,
    approvals: true,
  };

  await page.route(`${API}/healthz`, (route: Route) =>
    route.fulfill({ json: { ok: true } }),
  );
  await page.route(`${API}/users/me*`, (route: Route) =>
    route.fulfill({ json: STUB_USER }),
  );
  await page.route(`${API}/organizations/me/list*`, (route: Route) =>
    route.fulfill({
      json: [{ ...STUB_ORG, role }],
    }),
  );
  await page.route(`${API}/organizations/me/member*`, (route: Route) =>
    route.fulfill({
      json: { ...STUB_MEMBERSHIP, role },
    }),
  );
  // customFetch wraps response as {data: <body>}, so return raw body.
  // useFeatureFlags reads res.data.feature_flags
  await page.route(
    `${API}/organization-settings/feature-flags*`,
    (route: Route) =>
      route.fulfill({ json: { feature_flags: flags } }),
  );
  await page.route(`${API}/system/health*`, (route: Route) =>
    route.fulfill({ json: { status: "healthy", components: {} } }),
  );
  // Terms acceptance — customFetch wraps as {data: <body>}, TermsGate
  // does raw?.data ?? raw → needs terms_accepted at top level of JSON body
  await page.route(`${API}/auth/terms-status*`, (route: Route) =>
    route.fulfill({
      json: {
        terms_accepted: true,
        current_version: "1",
        accepted_version: "1",
      },
    }),
  );
  // SSE stream — return empty 200 so it doesn't hang
  await page.route(`${API}/activity/live/stream*`, (route: Route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream" },
      body: "",
    }),
  );
}

// ---------------------------------------------------------------------------
// Exported test fixture
// ---------------------------------------------------------------------------

type Fixtures = {
  authedPage: Page;
  stubApis: (
    opts?: Parameters<typeof stubCommonApis>[1],
  ) => Promise<void>;
};

export const test = base.extend<Fixtures>({
  authedPage: async ({ page }, use) => {
    await seedAuth(page);
    await stubCommonApis(page);
    await use(page);
  },

  stubApis: async ({ page }, use) => {
    await use(async (opts) => {
      await seedAuth(page);
      await stubCommonApis(page, opts);
    });
  },
});

export { expect } from "@playwright/test";
