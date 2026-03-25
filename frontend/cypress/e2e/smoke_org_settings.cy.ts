/// <reference types="cypress" />

import { setupCommonPageTestHooks } from "../support/testHooks";

describe("smoke: /org-settings", () => {
  const apiBase = "**/api/v1";

  const baseSettings = {
    openrouter_api_key: null,
    has_openrouter_key: false,
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

  function stubOrgSettingsApis(role: string) {
    const isAdmin = role === "owner" || role === "admin";

    cy.intercept("GET", `${apiBase}/organization-settings/feature-flags*`, {
      statusCode: 200,
      body: { data: { feature_flags: { email: true, cron_jobs: true } } },
    }).as("featureFlags");

    cy.intercept("GET", `${apiBase}/organization-settings`, {
      statusCode: 200,
      body: {
        data: {
          ...baseSettings,
          member_role: role,
          is_admin: isAdmin,
        },
      },
    }).as("orgSettings");

    cy.intercept("GET", `${apiBase}/organization-settings/audit-log*`, {
      statusCode: 200,
      body: { data: [] },
    }).as("auditLog");

    cy.intercept("GET", `${apiBase}/organization-settings/llm-routing`, {
      statusCode: 200,
      body: {
        data: {
          configured: false,
          source: null,
          name: null,
          api_url: null,
          is_openrouter: false,
          models: [],
          data_stays_private: false,
        },
      },
    }).as("llmRouting");
  }

  describe("admin view", () => {
    setupCommonPageTestHooks(apiBase, { orgMemberRole: "owner" });

    function visitOrgSettings() {
      stubOrgSettingsApis("owner");
      cy.loginWithLocalAuth();
      cy.visit("/org-settings");
      cy.waitForAppLoaded();
    }

    it("desktop: renders API Keys section", () => {
      cy.viewport(1280, 720);
      visitOrgSettings();

      cy.contains("API Keys").should("be.visible");
    });

    it("desktop: renders Feature Flags section", () => {
      cy.viewport(1280, 720);
      visitOrgSettings();

      cy.contains("Feature Flags").should("be.visible");
    });

    it("desktop: renders Cost Calculator section", () => {
      cy.viewport(1280, 720);
      visitOrgSettings();

      cy.contains("Cost Calculator").should("be.visible");
    });

    it("desktop: renders Data Policy section", () => {
      cy.viewport(1280, 720);
      visitOrgSettings();

      cy.contains("Data Policy").should("be.visible");
    });

    it("desktop: sidebar is visible", () => {
      cy.viewport(1280, 720);
      visitOrgSettings();

      cy.get("aside").should("be.visible");
    });

    it("mobile: sidebar hidden, hamburger visible", () => {
      cy.viewport(375, 812);
      visitOrgSettings();

      cy.get("aside").should("not.be.visible");
      cy.get('[aria-label="Toggle navigation"]').should("be.visible");
    });
  });

  describe("member (non-admin) view", () => {
    setupCommonPageTestHooks(apiBase, { orgMemberRole: "member" });

    function visitOrgSettingsMember() {
      stubOrgSettingsApis("member");
      cy.loginWithLocalAuth();
      cy.visit("/org-settings");
      cy.waitForAppLoaded();
    }

    it("desktop: renders page without error", () => {
      cy.viewport(1280, 720);
      visitOrgSettingsMember();

      // Page should load — member sees a restricted view
      // The settings endpoint returns is_admin: false for members
      cy.get("body").should("be.visible");
    });
  });
});
