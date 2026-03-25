/// <reference types="cypress" />

import { setupCommonPageTestHooks } from "../support/testHooks";

describe("smoke: /dashboard", () => {
  const apiBase = "**/api/v1";

  setupCommonPageTestHooks(apiBase);

  const emptySeries = {
    primary: { range: "7d", bucket: "day", points: [] },
    comparison: { range: "7d", bucket: "day", points: [] },
  };

  function stubDashboardApis() {
    cy.intercept("GET", `${apiBase}/organization-settings/feature-flags*`, {
      statusCode: 200,
      body: { data: { feature_flags: { email: true, cron_jobs: true, approvals: true } } },
    }).as("featureFlags");

    cy.intercept("GET", `${apiBase}/metrics/dashboard*`, {
      statusCode: 200,
      body: {
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
      },
    }).as("dashboardMetrics");

    cy.intercept("GET", `${apiBase}/boards*`, {
      statusCode: 200,
      body: { items: [], total: 0 },
    }).as("boardsList");

    cy.intercept("GET", `${apiBase}/agents*`, {
      statusCode: 200,
      body: { items: [], total: 0 },
    }).as("agentsList");

    cy.intercept("GET", `${apiBase}/activity*`, {
      statusCode: 200,
      body: { items: [], total: 0 },
    }).as("activityList");

    cy.intercept("GET", `${apiBase}/gateways/status*`, {
      statusCode: 200,
      body: { gateways: [] },
    }).as("gatewaysStatus");

    cy.intercept("GET", `${apiBase}/board-groups*`, {
      statusCode: 200,
      body: { items: [], total: 0 },
    }).as("boardGroupsList");
  }

  function visitDashboard() {
    stubDashboardApis();
    cy.loginWithLocalAuth();
    cy.visit("/dashboard");
    cy.waitForAppLoaded();
  }

  it("desktop: renders top metric cards", () => {
    cy.viewport(1280, 720);
    visitDashboard();

    cy.contains("Online Agents").should("be.visible");
    cy.contains("Tasks In Progress").should("be.visible");
    cy.contains("Error Rate").should("be.visible");
    cy.contains("Completion Speed").should("be.visible");
  });

  it("desktop: renders dashboard sections", () => {
    cy.viewport(1280, 720);
    visitDashboard();

    cy.contains("Workload").should("be.visible");
    cy.contains("Throughput").should("be.visible");
    cy.contains("Gateway Health").should("be.visible");
    cy.contains("Pending Approvals").should("be.visible");
    cy.contains("Sessions").should("be.visible");
    cy.contains("Recent Activity").should("be.visible");
  });

  it("desktop: sidebar is visible", () => {
    cy.viewport(1280, 720);
    visitDashboard();

    cy.get("aside").should("be.visible");
    cy.get('[aria-label="Toggle navigation"]').should("not.be.visible");
  });

  it("mobile: sidebar hidden, hamburger visible", () => {
    cy.viewport(375, 812);
    visitDashboard();

    cy.get('[aria-label="Toggle navigation"]').should("be.visible");
    cy.get("aside").should("not.be.visible");
  });

  it("mobile: metric cards still render", () => {
    cy.viewport(375, 812);
    visitDashboard();

    cy.contains("Online Agents").should("be.visible");
    cy.contains("Tasks In Progress").should("be.visible");
  });
});
