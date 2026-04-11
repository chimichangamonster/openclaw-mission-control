import { test, expect } from "./fixtures";
import type { Route } from "@playwright/test";

const API = "**/api/v1";

const emailAccounts = [
  {
    id: "ea1",
    provider: "outlook",
    email_address: "test@example.com",
    display_name: "Test Account",
    is_active: true,
    visibility: "shared",
    user_id: "u1",
    organization_id: "org1",
  },
];

const emailMessages = [
  {
    id: "msg1",
    subject: "Urgent client request",
    from_address: "client@corp.com",
    from_name: "Alice Client",
    sender_name: "Alice Client",
    sender_email: "client@corp.com",
    to_addresses: ["test@example.com"],
    body_text: "Need response ASAP on the proposal...",
    received_at: "2026-04-09T10:00:00Z",
    is_read: false,
    folder: "inbox",
    triage_status: "needs_review",
    triage_category: "inquiry",
    has_attachments: false,
    email_account_id: "ea1",
  },
  {
    id: "msg2",
    subject: "Invoice attached",
    from_address: "vendor@supply.com",
    from_name: "Bob Vendor",
    sender_name: "Bob Vendor",
    sender_email: "vendor@supply.com",
    to_addresses: ["test@example.com"],
    body_text: "Please find the invoice attached.",
    received_at: "2026-04-08T14:30:00Z",
    is_read: true,
    folder: "inbox",
    triage_status: "triaged",
    triage_category: "invoice",
    has_attachments: true,
    email_account_id: "ea1",
  },
  {
    id: "msg3",
    subject: "Meeting follow-up",
    from_address: "colleague@team.com",
    from_name: "Carol Team",
    sender_name: "Carol Team",
    sender_email: "colleague@team.com",
    to_addresses: ["test@example.com"],
    body_text: "Great call yesterday, here are the notes...",
    received_at: "2026-04-07T09:00:00Z",
    is_read: true,
    folder: "inbox",
    triage_status: "actioned",
    triage_category: "follow_up",
    has_attachments: false,
    email_account_id: "ea1",
  },
  {
    id: "msg4",
    subject: "Spam offer",
    from_address: "spam@junk.com",
    from_name: "Spammer",
    sender_name: "Spammer",
    sender_email: "spam@junk.com",
    to_addresses: ["test@example.com"],
    body_text: "You've won a million dollars!",
    received_at: "2026-04-06T08:00:00Z",
    is_read: true,
    folder: "inbox",
    triage_status: "spam",
    triage_category: "spam",
    has_attachments: false,
    email_account_id: "ea1",
  },
];

async function stubEmailApis(page: import("@playwright/test").Page) {
  await page.route(`${API}/email/accounts*`, (r: Route) => {
    if (r.request().url().includes("/messages")) return r.continue();
    return r.fulfill({ json: emailAccounts });
  });
  await page.route(`${API}/email/accounts/*/messages*`, (r: Route) => {
    const url = r.request().url();
    // Filter by triage_status if present
    const match = url.match(/triage_status=([^&]+)/);
    if (match) {
      const status = match[1];
      const filtered = emailMessages.filter(
        (m) => m.triage_status === status,
      );
      return r.fulfill({ json: filtered });
    }
    return r.fulfill({ json: emailMessages });
  });
}

test.describe("Email — page load", () => {
  test("renders folder tabs", async ({ authedPage: page }) => {
    await stubEmailApis(page);
    await page.goto("/email");

    // Verify folder navigation exists — "Inbox" button appears in both
    // the mobile strip (md:hidden) and sidebar (hidden md:block).
    // At least one is visible depending on viewport.
    const inbox = page.getByText("Inbox", { exact: true });
    await expect(inbox.first()).toBeAttached();
    // Verify it's also visually present in the rendered page
    await expect(page.locator("main")).toContainText("Inbox");
  });

  test("renders message list with subjects", async ({
    authedPage: page,
  }) => {
    await stubEmailApis(page);
    await page.goto("/email");

    await expect(page.getByText("Urgent client request")).toBeVisible();
    await expect(page.getByText("Invoice attached").first()).toBeVisible();
    await expect(page.getByText("Meeting follow-up")).toBeVisible();
  });
});

test.describe("Email — triage badges", () => {
  test("needs_review badge is visible with orange styling", async ({
    authedPage: page,
  }) => {
    await stubEmailApis(page);
    await page.goto("/email");

    // The "needs review" status badge (underscore replaced with space)
    const badge = page.getByText("needs review", { exact: true });
    await expect(badge).toBeVisible();

    // Verify orange styling class
    const classes = await badge.getAttribute("class");
    expect(classes).toContain("orange");
  });

  test("triaged badge is visible with blue styling", async ({
    authedPage: page,
  }) => {
    await stubEmailApis(page);
    await page.goto("/email");

    const badge = page.getByText("triaged", { exact: true });
    await expect(badge).toBeVisible();

    const classes = await badge.getAttribute("class");
    expect(classes).toContain("blue");
  });

  test("actioned badge is visible with green styling", async ({
    authedPage: page,
  }) => {
    await stubEmailApis(page);
    await page.goto("/email");

    const badge = page.getByText("actioned", { exact: true });
    await expect(badge).toBeVisible();

    const classes = await badge.getAttribute("class");
    expect(classes).toContain("green");
  });

  test("category badges render", async ({ authedPage: page }) => {
    await stubEmailApis(page);
    await page.goto("/email");

    await expect(page.getByText("inquiry", { exact: true })).toBeVisible();
    await expect(page.getByText("invoice", { exact: true })).toBeVisible();
  });
});

test.describe("Email — triage filter", () => {
  test("clicking Review filter shows only needs_review messages", async ({
    authedPage: page,
  }) => {
    await stubEmailApis(page);
    await page.goto("/email");

    // Wait for messages to load
    await expect(page.getByText("Urgent client request")).toBeVisible();

    // Click the Review filter button
    await page.getByRole("button", { name: "Review" }).click();

    // Only the needs_review message should appear
    await expect(page.getByText("Urgent client request")).toBeVisible();
    // The triaged message should be gone
    await expect(page.getByText("Invoice attached")).toBeHidden({
      timeout: 5000,
    });
  });
});

test.describe("Email — triage summary banner", () => {
  test("shows triage status counts when on All view", async ({
    authedPage: page,
  }) => {
    await stubEmailApis(page);
    await page.goto("/email");

    // "Pending" appears in mobile strip and desktop sidebar — check it's attached
    await expect(page.getByText(/Pending/).first()).toBeAttached();
    await expect(page.locator("main")).toContainText("Pending");
  });
});

test.describe("Email — mobile", () => {
  test("no horizontal overflow", async ({ authedPage: page }) => {
    await stubEmailApis(page);
    await page.goto("/email");

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
    await stubEmailApis(page);
    await page.goto("/email");

    if ((page.viewportSize()?.width ?? 1280) < 768) {
      // Sidebar uses CSS translate, check data attribute instead
      await expect(page.locator("[data-sidebar]")).toHaveAttribute(
        "data-sidebar",
        "closed",
      );
      await expect(
        page.getByRole("button", { name: "Toggle navigation" }),
      ).toBeVisible();
    }
  });

  test("triage filter buttons visible on mobile", async ({
    authedPage: page,
  }) => {
    await stubEmailApis(page);
    await page.goto("/email");

    if ((page.viewportSize()?.width ?? 1280) < 768) {
      // Mobile shows horizontal scrolling filter buttons
      await expect(page.getByRole("button", { name: "All" })).toBeVisible();
    }
  });
});
