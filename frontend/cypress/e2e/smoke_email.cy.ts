/// <reference types="cypress" />

import { setupCommonPageTestHooks } from "../support/testHooks";

describe("smoke: /email", () => {
  const apiBase = "**/api/v1";

  setupCommonPageTestHooks(apiBase);

  function stubEmailApis() {
    cy.intercept("GET", `${apiBase}/organization-settings/feature-flags*`, {
      statusCode: 200,
      body: { data: { feature_flags: { email: true } } },
    }).as("featureFlags");

    cy.intercept("GET", `${apiBase}/email/accounts*`, {
      statusCode: 200,
      body: [
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
      ],
    }).as("emailAccounts");

    cy.intercept("GET", `${apiBase}/email/accounts/*/messages*`, {
      statusCode: 200,
      body: [
        {
          id: "msg1",
          subject: "Test email subject",
          from_address: "sender@example.com",
          from_name: "Sender Name",
          to_addresses: ["test@example.com"],
          snippet: "This is a test email preview...",
          received_at: "2026-03-20T10:00:00Z",
          is_read: false,
          folder: "inbox",
          triage_status: null,
        },
        {
          id: "msg2",
          subject: "Another email",
          from_address: "other@example.com",
          from_name: "Other Sender",
          to_addresses: ["test@example.com"],
          snippet: "Another email body...",
          received_at: "2026-03-19T14:30:00Z",
          is_read: true,
          folder: "inbox",
          triage_status: "triaged",
        },
      ],
    }).as("emailMessages");
  }

  function visitEmail() {
    stubEmailApis();
    cy.loginWithLocalAuth();
    cy.visit("/email");
    cy.waitForAppLoaded();
  }

  it("desktop: renders folder tabs", () => {
    cy.viewport(1280, 720);
    visitEmail();

    cy.contains("Inbox").should("be.visible");
    cy.contains("Sent").should("be.visible");
    cy.contains("Archive").should("be.visible");
    cy.contains("Trash").should("be.visible");
  });

  it("desktop: renders message list", () => {
    cy.viewport(1280, 720);
    visitEmail();

    cy.contains("Test email subject").should("be.visible");
    cy.contains("sender@example.com").should("be.visible");
  });

  it("desktop: sidebar is visible", () => {
    cy.viewport(1280, 720);
    visitEmail();

    cy.get("aside").should("be.visible");
  });

  it("mobile: sidebar is hidden", () => {
    cy.viewport(375, 812);
    visitEmail();

    cy.get("aside").should("not.be.visible");
    cy.get('[aria-label="Toggle navigation"]').should("be.visible");
  });

  it("mobile: folder tabs still render", () => {
    cy.viewport(375, 812);
    visitEmail();

    cy.contains("Inbox").should("be.visible");
  });
});
