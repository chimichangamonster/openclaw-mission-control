type OnboardingProfileLike = {
  name?: string | null;
  preferred_name?: string | null;
  timezone?: string | null;
};

export function isOnboardingComplete(
  profile: OnboardingProfileLike | null | undefined,
): boolean {
  if (!profile) return false;
  const resolvedName = profile.preferred_name?.trim() || profile.name?.trim();
  return Boolean(resolvedName) && Boolean(profile.timezone?.trim());
}

type MembershipLike = {
  role?: string | null;
};

const ADMIN_ROLES = new Set(["owner", "admin"]);

// An invited member (non-admin) of an existing org should NOT see the
// 5-step org-setup wizard — Steps 2-5 (Industry / API Key / Features /
// Checklist) configure the *org*, not the user. Only the user-profile
// step (Step 1) applies. This predicate decides whether to short-circuit
// onboarding to dashboard after the profile step.
//
// Returns true when the user has a membership AND their role is below
// admin. Returns false when membership is unknown (loading, error) or
// when the user is owner/admin (founder path — full wizard applies).
export function shouldSkipOrgSetupWizard(
  membership: MembershipLike | null | undefined,
): boolean {
  if (!membership) return false;
  const role = membership.role?.trim().toLowerCase();
  if (!role) return false;
  return !ADMIN_ROLES.has(role);
}
