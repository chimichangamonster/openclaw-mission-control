/// <reference types="cypress" />

import { setupCommonPageTestHooks } from "../support/testHooks";

describe("smoke: /boards", () => {
  const apiBase = "**/api/v1";

  setupCommonPageTestHooks(apiBase);

  function stubBoardsApis() {
    cy.intercept("GET", `${apiBase}/organization-settings/feature-flags*`, {
      statusCode: 200,
      body: { data: { feature_flags: {} } },
    }).as("featureFlags");

    cy.intercept("GET", `${apiBase}/boards*`, {
      statusCode: 200,
      body: {
        items: [
          {
            id: "b1",
            name: "Vantage Solutions",
            slug: "vantage-solutions",
            description: "Main ops board",
            gateway_id: "g1",
            board_group_id: null,
            board_type: "general",
            objective: null,
            success_metrics: null,
            target_date: null,
            goal_confirmed: true,
            goal_source: "test",
            organization_id: "org1",
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
          {
            id: "b2",
            name: "Waste Gurus",
            slug: "waste-gurus",
            description: "Waste management board",
            gateway_id: "g1",
            board_group_id: null,
            board_type: "general",
            objective: null,
            success_metrics: null,
            target_date: null,
            goal_confirmed: true,
            goal_source: "test",
            organization_id: "org1",
            created_at: "2026-01-02T00:00:00Z",
            updated_at: "2026-01-02T00:00:00Z",
          },
        ],
        total: 2,
        limit: 200,
        offset: 0,
      },
    }).as("boards");

    cy.intercept("GET", `${apiBase}/board-groups*`, {
      statusCode: 200,
      body: { items: [], total: 0, limit: 200, offset: 0 },
    }).as("boardGroups");
  }

  function visitBoards() {
    stubBoardsApis();
    cy.loginWithLocalAuth();
    cy.visit("/boards");
    cy.waitForAppLoaded();
  }

  it("desktop: renders page title", () => {
    cy.viewport(1280, 720);
    visitBoards();

    cy.contains(/boards/i).should("be.visible");
  });

  it("desktop: renders board list with entries", () => {
    cy.viewport(1280, 720);
    visitBoards();

    cy.contains("Vantage Solutions").should("be.visible");
    cy.contains("Waste Gurus").should("be.visible");
  });

  it("desktop: shows create board button for owner", () => {
    cy.viewport(1280, 720);
    visitBoards();

    cy.contains("a", /create board/i).should("be.visible");
  });

  it("desktop: sidebar is visible", () => {
    cy.viewport(1280, 720);
    visitBoards();

    cy.get("aside").should("be.visible");
  });

  it("mobile: sidebar hidden, hamburger visible", () => {
    cy.viewport(375, 812);
    visitBoards();

    cy.get("aside").should("not.be.visible");
    cy.get('[aria-label="Toggle navigation"]').should("be.visible");
  });

  it("mobile: boards list still renders", () => {
    cy.viewport(375, 812);
    visitBoards();

    cy.contains("Vantage Solutions").should("be.visible");
  });
});
