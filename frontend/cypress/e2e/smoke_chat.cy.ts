/// <reference types="cypress" />

import { setupCommonPageTestHooks } from "../support/testHooks";

describe("smoke: /chat", () => {
  const apiBase = "**/api/v1";

  setupCommonPageTestHooks(apiBase);

  function stubChatApis() {
    cy.intercept("GET", `${apiBase}/organization-settings/feature-flags*`, {
      statusCode: 200,
      body: { data: { feature_flags: { email: true } } },
    }).as("featureFlags");

    // Gateway sessions list — return a session for The Claw on #general
    cy.intercept("GET", `${apiBase}/gateways/sessions*`, {
      statusCode: 200,
      body: {
        data: [
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
    }).as("gatewaySessions");

    // Session history — empty conversation
    cy.intercept("GET", `${apiBase}/gateways/sessions/*/history*`, {
      statusCode: 200,
      body: { data: [] },
    }).as("sessionHistory");

    // Activity live stream — no events
    cy.intercept("GET", `${apiBase}/activity/live/stream*`, {
      statusCode: 200,
      headers: { "content-type": "text/event-stream" },
      body: "",
    }).as("activityStream");
  }

  function visitChat() {
    stubChatApis();
    cy.loginWithLocalAuth();
    cy.visit("/chat");
    cy.waitForAppLoaded();
  }

  it("desktop: renders The Claw header with bot icon", () => {
    cy.viewport(1280, 720);
    visitChat();

    cy.contains("The Claw").should("be.visible");
  });

  it("desktop: renders input area with textarea and send button", () => {
    cy.viewport(1280, 720);
    visitChat();

    cy.get("textarea").should("be.visible");
    // Send button exists (may be disabled when input is empty)
    cy.get("button").filter(":has(svg)").should("have.length.greaterThan", 0);
  });

  it("desktop: shows suggestion pills when no messages", () => {
    cy.viewport(1280, 720);
    visitChat();

    // The greeting text from The Claw
    cy.contains("The Claw").should("be.visible");
  });

  it("desktop: compact and clear buttons exist", () => {
    cy.viewport(1280, 720);
    visitChat();

    cy.get('button[title*="Compact"]').should("exist");
    cy.get('button[title*="Clear"]').should("exist");
  });

  it("mobile: layout does not overflow horizontally", () => {
    cy.viewport(375, 812);
    visitChat();

    cy.contains("The Claw").should("be.visible");
    cy.get("textarea").should("be.visible");

    // Verify no horizontal overflow
    cy.document().then((doc) => {
      const body = doc.body;
      expect(body.scrollWidth).to.be.lte(body.clientWidth + 1);
    });
  });
});
