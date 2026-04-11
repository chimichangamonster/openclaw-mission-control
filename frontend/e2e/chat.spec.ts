import { test, expect } from "./fixtures";
import type { Route } from "@playwright/test";

const API = "**/api/v1";

function stubChatApis(page: import("@playwright/test").Page) {
  return Promise.all([
    page.route(/\/api\/v1\/gateways\/sessions(\?|$)/, (r: Route) =>
      r.fulfill({
        json: {
          sessions: [
            {
              key: "general-the-claw",
              displayName: "The Claw",
              groupChannel: "general",
              model: "anthropic/claude-sonnet-4",
              totalTokens: 5000,
              inputTokens: 3000,
              outputTokens: 2000,
            },
          ],
        },
      }),
    ),
    page.route(`${API}/gateways/sessions/*/history*`, (r: Route) =>
      r.fulfill({ json: { history: [] } }),
    ),
    page.route(`${API}/boards*`, (r: Route) =>
      r.fulfill({
        json: {
          items: [
            {
              id: "b1",
              name: "Vantage Solutions",
              gateway_id: "gw1",
              organization_id: "org1",
            },
          ],
          total: 1,
        },
      }),
    ),
    page.route(`${API}/gateways/status*`, (r: Route) =>
      r.fulfill({
        json: {
          gateways: [{ id: "gw1", connected: true, name: "vantage" }],
        },
      }),
    ),
  ]);
}

test.describe("Chat — page load", () => {
  test("renders The Claw header and input area", async ({
    authedPage: page,
  }) => {
    await stubChatApis(page);
    await page.goto("/chat");

    await expect(page.getByText("The Claw", { exact: true })).toBeVisible();
    await expect(page.locator("textarea")).toBeVisible();
  });

  test("compact and clear buttons exist", async ({ authedPage: page }) => {
    await stubChatApis(page);
    await page.goto("/chat");

    await expect(
      page.locator('button[title*="Compact"], button[title*="compact"]').first(),
    ).toBeVisible();
    await expect(
      page.locator('button[title*="Clear"], button[title*="clear"]').first(),
    ).toBeVisible();
  });
});

test.describe("Chat — send message", () => {
  test("sending a message shows it in the conversation", async ({
    authedPage: page,
  }) => {
    await stubChatApis(page);

    // Intercept the send endpoint — return success
    await page.route(`${API}/gateways/sessions/*/message*`, (r: Route) =>
      r.fulfill({ json: { ok: true } }),
    );

    // After send, return history with user + agent messages
    let sendCount = 0;
    await page.route(`${API}/gateways/sessions/*/history*`, (r: Route) => {
      sendCount++;
      if (sendCount <= 1) {
        return r.fulfill({ json: { history: [] } });
      }
      return r.fulfill({
        json: {
          history: [
            {
              role: "user",
              content: "Hello there",
              timestamp: new Date().toISOString(),
            },
            {
              role: "assistant",
              content: "Hi! How can I help you today?",
              timestamp: new Date().toISOString(),
            },
          ],
        },
      });
    });

    await page.goto("/chat");
    await page.locator("textarea").fill("Hello there");
    await page.locator("textarea").press("Enter");

    // Optimistic user message appears immediately
    await expect(page.getByText("Hello there")).toBeVisible({ timeout: 5000 });

    // Agent response appears after polling picks up the new history
    await expect(
      page.getByText("Hi! How can I help you today?"),
    ).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("Chat — mobile", () => {
  test("no horizontal overflow on mobile", async ({ authedPage: page }) => {
    await stubChatApis(page);
    await page.goto("/chat");

    if ((page.viewportSize()?.width ?? 1280) < 768) {
      await expect(page.getByText("The Claw", { exact: true })).toBeVisible();
      await expect(page.locator("textarea")).toBeVisible();

      const noOverflow = await page.evaluate(
        () => document.body.scrollWidth <= document.body.clientWidth + 1,
      );
      expect(noOverflow).toBe(true);
    }
  });

  test("textarea has adequate touch target height", async ({
    authedPage: page,
  }) => {
    await stubChatApis(page);
    await page.goto("/chat");

    if ((page.viewportSize()?.width ?? 1280) < 768) {
      const box = await page.locator("textarea").boundingBox();
      expect(box).toBeTruthy();
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }
  });
});
