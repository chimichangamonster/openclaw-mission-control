import { describe, expect, it } from "vitest";

import { isOnboardingComplete, shouldSkipOrgSetupWizard } from "@/lib/onboarding";

describe("isOnboardingComplete", () => {
  it("returns false when profile is missing", () => {
    expect(isOnboardingComplete(null)).toBe(false);
    expect(isOnboardingComplete(undefined)).toBe(false);
  });

  it("returns false when timezone is missing", () => {
    expect(
      isOnboardingComplete({
        preferred_name: "Asha",
        timezone: "",
      }),
    ).toBe(false);
  });

  it("returns false when both name fields are missing", () => {
    expect(
      isOnboardingComplete({
        name: "   ",
        preferred_name: "   ",
        timezone: "America/New_York",
      }),
    ).toBe(false);
  });

  it("accepts preferred_name + timezone", () => {
    expect(
      isOnboardingComplete({
        preferred_name: "Asha",
        timezone: "America/New_York",
      }),
    ).toBe(true);
  });

  it("accepts fallback name + timezone", () => {
    expect(
      isOnboardingComplete({
        name: "Asha",
        timezone: "America/New_York",
      }),
    ).toBe(true);
  });
});

describe("shouldSkipOrgSetupWizard", () => {
  it("returns false when membership is missing or loading", () => {
    expect(shouldSkipOrgSetupWizard(null)).toBe(false);
    expect(shouldSkipOrgSetupWizard(undefined)).toBe(false);
    expect(shouldSkipOrgSetupWizard({})).toBe(false);
    expect(shouldSkipOrgSetupWizard({ role: "" })).toBe(false);
    expect(shouldSkipOrgSetupWizard({ role: "   " })).toBe(false);
  });

  it("returns false for owner and admin (founder path — full wizard)", () => {
    expect(shouldSkipOrgSetupWizard({ role: "owner" })).toBe(false);
    expect(shouldSkipOrgSetupWizard({ role: "admin" })).toBe(false);
    expect(shouldSkipOrgSetupWizard({ role: "OWNER" })).toBe(false);
    expect(shouldSkipOrgSetupWizard({ role: " admin " })).toBe(false);
  });

  it("returns true for non-admin members (invitee path — skip org steps)", () => {
    expect(shouldSkipOrgSetupWizard({ role: "operator" })).toBe(true);
    expect(shouldSkipOrgSetupWizard({ role: "member" })).toBe(true);
    expect(shouldSkipOrgSetupWizard({ role: "viewer" })).toBe(true);
  });
});
