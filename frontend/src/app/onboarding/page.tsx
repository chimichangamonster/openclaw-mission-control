"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  SignInButton,
  SignedIn,
  SignedOut,
  useAuth,
  useUser,
} from "@/auth/clerk";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  Check,
  CheckCircle2,
  Circle,
  Globe,
  Key,
  Layers,
  ListChecks,
  RotateCcw,
  Save,
  Settings,
  Sparkles,
  User,
} from "lucide-react";

import { ApiError } from "@/api/mutator";
import {
  type getMeApiV1UsersMeGetResponse,
  useGetMeApiV1UsersMeGet,
  useUpdateMeApiV1UsersMePatch,
} from "@/api/generated/users/users";
import {
  type getMyMembershipApiV1OrganizationsMeMemberGetResponse,
  useGetMyMembershipApiV1OrganizationsMeMemberGet,
} from "@/api/generated/organizations/organizations";
import { customFetch } from "@/api/mutator";
import { DashboardShell } from "@/components/templates/DashboardShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import SearchableSelect from "@/components/ui/searchable-select";
import { isOnboardingComplete, shouldSkipOrgSetupWizard } from "@/lib/onboarding";
import { getSupportedTimezones } from "@/lib/timezones";


// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ConfigCategory = {
  key: string;
  label: string;
  item_count: number;
};

type IndustryTemplate = {
  id: string;
  name: string;
  description: string;
  icon: string;
  skill_count: number;
  config_categories: ConfigCategory[];
  skills?: string[];
  onboarding_step_count?: number;
  feature_flags?: string[];
};

type AutoDetectResult = {
  template_id: string | null;
  confidence: number;
};

type OnboardingStatus = {
  template_id: string | null;
  steps: {
    step_key: string;
    label: string;
    description: string;
    completed: boolean;
  }[];
  progress_pct: number;
};

// ---------------------------------------------------------------------------
// Steps
// ---------------------------------------------------------------------------

const STEPS = [
  { key: "profile", label: "Profile", icon: User },
  { key: "industry", label: "Industry", icon: Building2 },
  { key: "api-key", label: "API Key", icon: Key },
  { key: "features", label: "Features", icon: Settings },
  { key: "checklist", label: "Checklist", icon: Layers },
] as const;

type StepKey = (typeof STEPS)[number]["key"];

// ---------------------------------------------------------------------------
// Feature flag metadata — grouped with human-readable descriptions
// ---------------------------------------------------------------------------

const FEATURE_GROUPS: {
  label: string;
  flags: { key: string; name: string; description: string }[];
}[] = [
  {
    label: "Business Operations",
    flags: [
      {
        key: "bookkeeping",
        name: "Bookkeeping & Invoicing",
        description: "Expense tracking, invoicing, GST calculations",
      },
      {
        key: "document_generation",
        name: "Document Generation",
        description: "Proposals, reports, PDF generation",
      },
      {
        key: "email",
        name: "Email Integration",
        description: "Sync and triage email from Outlook/Zoho",
      },
      {
        key: "google_calendar",
        name: "Google Calendar",
        description: "Schedule events, manage calendar",
      },
      {
        key: "microsoft_graph",
        name: "Microsoft 365",
        description: "OneDrive, Outlook Calendar, SharePoint",
      },
    ],
  },
  {
    label: "Trading & Markets",
    flags: [
      {
        key: "paper_trading",
        name: "Paper Trading",
        description: "Simulated stock trading with portfolios",
      },
      {
        key: "paper_bets",
        name: "Sports Betting",
        description: "Odds comparison, bankroll management",
      },
      {
        key: "watchlist",
        name: "Stock Watchlist",
        description: "Track tickers, RSI alerts, volume monitoring",
      },
      {
        key: "polymarket",
        name: "Prediction Markets",
        description: "Polymarket trading research",
      },
      {
        key: "crypto_trading",
        name: "Crypto Trading",
        description: "Swing trading, Fear & Greed index",
      },
    ],
  },
  {
    label: "System",
    flags: [
      {
        key: "cron_jobs",
        name: "Scheduled Jobs",
        description: "Automated daily/weekly agent tasks",
      },
      {
        key: "approvals",
        name: "Approvals",
        description: "Human-in-the-loop review for agent actions",
      },
      {
        key: "cost_tracker",
        name: "Cost Tracker",
        description: "Monitor AI spending and model usage",
      },
      {
        key: "wechat",
        name: "WeChat/WeCom",
        description: "Enterprise WeChat messaging and login",
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function OnboardingPage() {
  const router = useRouter();
  const { isSignedIn } = useAuth();
  const { user } = useUser();

  const [step, setStep] = useState<StepKey>("profile");
  const [name, setName] = useState("");
  const [timezone, setTimezone] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [profileSaved, setProfileSaved] = useState(false);

  // Industry
  const [templates, setTemplates] = useState<IndustryTemplate[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [templateApplied, setTemplateApplied] = useState(false);
  const [recommendedTemplate, setRecommendedTemplate] = useState<string | null>(null);
  const [excludedCategories, setExcludedCategories] = useState<Set<string>>(new Set());
  const [applyingTemplate, setApplyingTemplate] = useState(false);

  // API Key
  const [apiKey, setApiKey] = useState("");
  const [apiKeySaved, setApiKeySaved] = useState(false);

  // Features
  const [features, setFeatures] = useState<Record<string, boolean>>({});
  const [featuresSaved, setFeaturesSaved] = useState(false);

  // Checklist
  const [onboardingStatus, setOnboardingStatus] =
    useState<OnboardingStatus | null>(null);

  const meQuery = useGetMeApiV1UsersMeGet<
    getMeApiV1UsersMeGetResponse,
    ApiError
  >({
    query: {
      enabled: Boolean(isSignedIn),
      retry: false,
      refetchOnMount: "always",
    },
  });

  const membershipQuery = useGetMyMembershipApiV1OrganizationsMeMemberGet<
    getMyMembershipApiV1OrganizationsMeMemberGetResponse,
    ApiError
  >({
    query: {
      enabled: Boolean(isSignedIn),
      retry: false,
      refetchOnMount: "always",
    },
  });

  const membership =
    membershipQuery.data?.status === 200 ? membershipQuery.data.data : null;
  const skipOrgWizard = shouldSkipOrgSetupWizard(membership);

  const updateMeMutation = useUpdateMeApiV1UsersMePatch<ApiError>({
    mutation: {
      onSuccess: () => {
        setProfileSaved(true);
        // Invited members (non-admin) only need the user-profile step. The
        // remaining steps (Industry / API Key / Features / Checklist) configure
        // the org and are admin-only — short-circuit to dashboard so members
        // don't see a misleading "set up your organization" wizard.
        if (skipOrgWizard) {
          router.replace("/dashboard");
          return;
        }
        setStep("industry");
        // Auto-detect industry after profile save
        customFetch<{ status: number; data: AutoDetectResult }>(
          `/api/v1/industry-templates/auto-detect`,
          { method: "GET" },
        )
          .then((res) => {
            const HIDDEN_TEMPLATES = ["day_trading", "sports_betting"];
            if (
              res.status === 200 &&
              res.data.template_id &&
              res.data.confidence >= 0.4 &&
              !HIDDEN_TEMPLATES.includes(res.data.template_id)
            ) {
              setRecommendedTemplate(res.data.template_id);
            }
          })
          .catch(() => {});
      },
      onError: (err) => {
        setError(err.message || "Something went wrong.");
      },
    },
  });

  const profile = meQuery.data?.status === 200 ? meQuery.data.data : null;
  const isLoading = meQuery.isLoading || updateMeMutation.isPending;

  const clerkFallbackName =
    user?.fullName ?? user?.firstName ?? user?.username ?? "";
  const resolvedName = name.trim()
    ? name
    : (profile?.preferred_name ?? profile?.name ?? clerkFallbackName ?? "");
  const resolvedTimezone = timezone.trim()
    ? timezone
    : (profile?.timezone ?? "");

  const timezones = useMemo(() => getSupportedTimezones(), []);
  const timezoneOptions = useMemo(
    () => timezones.map((tz) => ({ value: tz, label: tz })),
    [timezones],
  );

  // If profile already complete, advance past Step 1. Invited members
  // (non-admin) skip the org-setup wizard entirely and go to dashboard;
  // admin/owner founders proceed to the Industry step.
  useEffect(() => {
    if (profile && isOnboardingComplete(profile) && !profileSaved) {
      setProfileSaved(true);
      if (skipOrgWizard) {
        router.replace("/dashboard");
        return;
      }
      setStep("industry");
    }
  }, [profile, profileSaved, skipOrgWizard, router]);

  // Load templates
  useEffect(() => {
    if (!isSignedIn) return;
    customFetch<{ status: number; data: IndustryTemplate[] }>(
      `/api/v1/industry-templates`,
      { method: "GET" },
    ).then((res) => {
      if (res.status === 200) {
        // Hide trading/betting templates — these are personal test tools, not business verticals
        const HIDDEN_TEMPLATES = ["day_trading", "sports_betting"];
        setTemplates(res.data.filter((t: IndustryTemplate) => !HIDDEN_TEMPLATES.includes(t.id)));
      }
    }).catch(() => {});
  }, [isSignedIn]);

  // Load feature flags
  const loadFeatures = useCallback(async () => {
    try {
      const res = await customFetch<{ status: number; data: { feature_flags: Record<string, boolean> } }>(
        `/api/v1/organization-settings/feature-flags`,
        { method: "GET" },
      );
      if (res.status === 200) setFeatures(res.data.feature_flags);
    } catch {
      // fallback
    }
  }, []);

  // Load onboarding status
  const loadOnboardingStatus = useCallback(async () => {
    try {
      const res = await customFetch<{ status: number; data: OnboardingStatus }>(
        `/api/v1/industry-templates/onboarding/status`,
        { method: "GET" },
      );
      if (res.status === 200) setOnboardingStatus(res.data);
    } catch {
      // org may not have template applied
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const handleProfileSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isSignedIn) return;
    const n = resolvedName.trim();
    const tz = resolvedTimezone.trim();
    if (!n || !tz) {
      setError("Please complete the required fields.");
      return;
    }
    setError(null);
    try {
      await updateMeMutation.mutateAsync({
        data: { name: n, preferred_name: n, timezone: tz },
      });
    } catch {
      // handled by onError
    }
  };

  const handleSelectTemplate = (templateId: string) => {
    setSelectedTemplate(templateId);
    setExcludedCategories(new Set());
    setError(null);
  };

  const handleToggleCategory = (categoryKey: string) => {
    setExcludedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(categoryKey)) {
        next.delete(categoryKey);
      } else {
        next.add(categoryKey);
      }
      return next;
    });
  };

  const handleApplyTemplate = async () => {
    if (!selectedTemplate) return;
    setError(null);
    setApplyingTemplate(true);
    try {
      await customFetch(`/api/v1/industry-templates/${selectedTemplate}/apply`, {
        method: "POST",
        body: JSON.stringify({
          exclude_categories: Array.from(excludedCategories),
        }),
      });
      setTemplateApplied(true);
      await loadFeatures();
      setStep("api-key");
    } catch {
      setError("Failed to apply template.");
    } finally {
      setApplyingTemplate(false);
    }
  };

  const handleSkipTemplate = () => {
    loadFeatures();
    setStep("api-key");
  };

  const handleSaveApiKey = async () => {
    if (!apiKey.trim()) {
      setApiKeySaved(true);
      setStep("features");
      return;
    }
    setError(null);
    try {
      await customFetch(`/api/v1/organization-settings/openrouter-key`, {
        method: "POST",
        body: JSON.stringify({ key: apiKey.trim() }),
      });
      setApiKeySaved(true);
      setStep("features");
    } catch {
      setError("Failed to save API key. Check that it starts with 'sk-or-'.");
    }
  };

  const handleSaveFeatures = async () => {
    setError(null);
    try {
      await customFetch(`/api/v1/organization-settings`, {
        method: "PUT",
        body: JSON.stringify({ feature_flags: features }),
      });
      setFeaturesSaved(true);
      await loadOnboardingStatus();
      setStep("checklist");
    } catch {
      setError("Failed to save features.");
    }
  };

  const handleFinish = () => {
    router.replace("/dashboard");
  };

  // ---------------------------------------------------------------------------
  // Stepper
  // ---------------------------------------------------------------------------

  const stepIndex = STEPS.findIndex((s) => s.key === step);

  const goBack = () => {
    if (stepIndex > 0) setStep(STEPS[stepIndex - 1].key);
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const renderStep = () => {
    switch (step) {
      case "profile":
        return (
          <form onSubmit={handleProfileSubmit} className="space-y-6">
            <div className="grid gap-6 md:grid-cols-2">
              <div className="space-y-2">
                <label className="text-sm font-medium text-[color:var(--text)] flex items-center gap-2">
                  <User className="h-4 w-4 text-[color:var(--text-muted)]" />
                  Name <span className="text-red-500">*</span>
                </label>
                <Input
                  value={resolvedName}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Enter your name"
                  disabled={isLoading}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-[color:var(--text)] flex items-center gap-2">
                  <Globe className="h-4 w-4 text-[color:var(--text-muted)]" />
                  Timezone <span className="text-red-500">*</span>
                </label>
                <SearchableSelect
                  ariaLabel="Select timezone"
                  value={resolvedTimezone}
                  onValueChange={setTimezone}
                  options={timezoneOptions}
                  placeholder="Select timezone"
                  searchPlaceholder="Search timezones..."
                  emptyMessage="No matching timezones."
                />
              </div>
            </div>
            <div className="flex gap-3 pt-2">
              <Button
                type="submit"
                className="flex-1"
                disabled={isLoading || !resolvedName.trim() || !resolvedTimezone.trim()}
              >
                <Save className="h-4 w-4" />
                {isLoading ? "Saving..." : "Save & Continue"}
              </Button>
            </div>
          </form>
        );

      case "industry": {
        // Sort templates so recommended one appears first
        const sortedTemplates = [...templates].sort((a, b) => {
          if (a.id === recommendedTemplate) return -1;
          if (b.id === recommendedTemplate) return 1;
          return 0;
        });
        const activeTemplate = templates.find((t) => t.id === selectedTemplate);
        return (
          <div className="space-y-6">
            <p className="text-sm text-[color:var(--text-muted)]">
              Select your industry to pre-configure features, skills, and settings.
              You can customize everything later.
            </p>

            {/* Template grid — hidden once a template is selected for customization */}
            {!selectedTemplate && (
              <div className="grid gap-4 md:grid-cols-2">
                {sortedTemplates.map((t) => {
                  const isRecommended = t.id === recommendedTemplate;
                  return (
                    <button
                      key={t.id}
                      onClick={() => handleSelectTemplate(t.id)}
                      className={`relative text-left rounded-xl border p-4 transition-all hover:shadow-md ${
                        isRecommended
                          ? "border-amber-400 bg-amber-50/50 dark:border-amber-600 dark:bg-amber-950/30 hover:border-amber-500"
                          : "border-[color:var(--border)] hover:border-blue-300"
                      }`}
                    >
                      {isRecommended && (
                        <span className="absolute -top-2.5 right-3 inline-flex items-center gap-1 rounded-full bg-amber-100 dark:bg-amber-900 px-2.5 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-200">
                          <Sparkles className="h-3 w-3" />
                          Recommended
                        </span>
                      )}
                      <div className="flex items-center gap-3 mb-2">
                        <span className="text-2xl">{t.icon}</span>
                        <h3 className="font-semibold text-[color:var(--text)]">
                          {t.name}
                        </h3>
                      </div>
                      <p className="text-sm text-[color:var(--text-muted)]">
                        {t.description}
                      </p>
                      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-[color:var(--text-muted)]">
                        <span className="inline-flex items-center gap-1">
                          <Layers className="h-3 w-3" />
                          {t.skill_count} skills
                        </span>
                        {t.onboarding_step_count != null && t.onboarding_step_count > 0 && (
                          <span className="inline-flex items-center gap-1">
                            <ListChecks className="h-3 w-3" />
                            {t.onboarding_step_count} setup steps
                          </span>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}

            {/* Customize panel — shown after selecting a template */}
            {selectedTemplate && activeTemplate && (
              <div className="space-y-4">
                <div className="flex items-center gap-3 rounded-lg border border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950 p-4">
                  <span className="text-2xl">{activeTemplate.icon}</span>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-[color:var(--text)]">
                      {activeTemplate.name}
                    </h3>
                    <p className="text-xs text-[color:var(--text-muted)]">
                      {activeTemplate.description}
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setSelectedTemplate(null);
                      setExcludedCategories(new Set());
                    }}
                  >
                    <RotateCcw className="h-3 w-3" /> Change
                  </Button>
                </div>

                <div>
                  <h3 className="text-sm font-medium text-[color:var(--text)] mb-3">
                    Choose what to set up
                  </h3>
                  <p className="text-xs text-[color:var(--text-muted)] mb-3">
                    Uncheck anything your business doesn&apos;t need. You can always add these later.
                  </p>
                  <div className="space-y-2">
                    {activeTemplate.config_categories.map((cat) => (
                      <label
                        key={cat.key}
                        className="flex items-center gap-3 rounded-lg border border-[color:var(--border)] p-3 cursor-pointer hover:bg-[color:var(--surface-muted)] transition-colors"
                      >
                        <input
                          type="checkbox"
                          checked={!excludedCategories.has(cat.key)}
                          onChange={() => handleToggleCategory(cat.key)}
                          className="h-4 w-4 shrink-0 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        />
                        <div className="flex-1 min-w-0">
                          <span className="text-sm font-medium text-[color:var(--text)]">
                            {cat.label}
                          </span>
                          <span className="ml-2 text-xs text-[color:var(--text-muted)]">
                            ({cat.item_count} defaults)
                          </span>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            )}

            <div className="flex gap-3 pt-2">
              <Button variant="outline" onClick={selectedTemplate ? () => { setSelectedTemplate(null); setExcludedCategories(new Set()); } : goBack}>
                <ArrowLeft className="h-4 w-4" /> Back
              </Button>
              {selectedTemplate ? (
                <Button onClick={handleApplyTemplate} disabled={applyingTemplate} className="ml-auto">
                  {applyingTemplate ? "Applying..." : "Apply & Continue"} <ArrowRight className="h-4 w-4" />
                </Button>
              ) : (
                <Button variant="outline" onClick={handleSkipTemplate} className="ml-auto">
                  Skip for now <ArrowRight className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>
        );
      }

      case "api-key":
        return (
          <div className="space-y-6">
            <p className="text-sm text-[color:var(--text-muted)]">
              VantageClaw uses OpenRouter to connect to AI models. Add your own API key
              for dedicated usage, or skip this step entirely.
            </p>
            <div className="space-y-2">
              <label className="text-sm font-medium text-[color:var(--text)] flex items-center gap-2">
                <Key className="h-4 w-4 text-[color:var(--text-muted)]" />
                OpenRouter API Key
                <span className="text-xs font-normal text-[color:var(--text-muted)]">(optional)</span>
              </label>
              <Input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-or-..."
              />
              <p className="text-xs text-[color:var(--text-muted)]">
                Get your key at{" "}
                <a
                  href="https://openrouter.ai/keys"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline"
                >
                  openrouter.ai/keys
                </a>
                . Must be an API key, not a personal subscription.
              </p>
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" onClick={goBack}>
                <ArrowLeft className="h-4 w-4" /> Back
              </Button>
              {apiKey.trim() ? (
                <Button onClick={handleSaveApiKey} className="ml-auto">
                  Save Key & Continue <ArrowRight className="h-4 w-4" />
                </Button>
              ) : (
                <Button onClick={handleSaveApiKey} className="ml-auto">
                  Skip for Now <ArrowRight className="h-4 w-4" />
                </Button>
              )}
            </div>
            {!apiKey.trim() && (
              <p className="text-xs text-center text-[color:var(--text-muted)]">
                You can add your API key later in Organization Settings.
              </p>
            )}
          </div>
        );

      case "features": {
        // Build a lookup of known flags for O(1) access
        const knownFlags = new Set(
          FEATURE_GROUPS.flatMap((g) => g.flags.map((f) => f.key)),
        );
        // Collect any flags from the backend that aren't in our metadata
        const unknownFlags = Object.keys(features).filter(
          (k) => !knownFlags.has(k),
        );

        return (
          <div className="space-y-6">
            <p className="text-sm text-[color:var(--text-muted)]">
              Enable the features your organization needs. You can change these
              anytime in Organization Settings.
            </p>
            <div className="space-y-6">
              {FEATURE_GROUPS.map((group) => {
                // Only show group if at least one flag exists in the features map
                const visibleFlags = group.flags.filter(
                  (f) => f.key in features,
                );
                if (visibleFlags.length === 0) return null;
                return (
                  <div key={group.label}>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-[color:var(--text-muted)] mb-3">
                      {group.label}
                    </h3>
                    <div className="space-y-2">
                      {visibleFlags.map((flag) => (
                        <label
                          key={flag.key}
                          className="flex items-start gap-3 rounded-lg border border-[color:var(--border)] p-3 cursor-pointer hover:bg-[color:var(--surface-muted)] transition-colors"
                        >
                          <input
                            type="checkbox"
                            checked={features[flag.key] ?? false}
                            onChange={(e) =>
                              setFeatures((prev) => ({
                                ...prev,
                                [flag.key]: e.target.checked,
                              }))
                            }
                            className="mt-0.5 h-4 w-4 shrink-0 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                          />
                          <div className="min-w-0">
                            <span className="text-sm font-medium text-[color:var(--text)]">
                              {flag.name}
                            </span>
                            <p className="text-xs text-[color:var(--text-muted)] mt-0.5">
                              {flag.description}
                            </p>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>
                );
              })}
              {/* Render any flags not in our metadata as a fallback */}
              {unknownFlags.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-[color:var(--text-muted)] mb-3">
                    Other
                  </h3>
                  <div className="space-y-2">
                    {unknownFlags.map((key) => (
                      <label
                        key={key}
                        className="flex items-center gap-3 rounded-lg border border-[color:var(--border)] p-3 cursor-pointer hover:bg-[color:var(--surface-muted)] transition-colors"
                      >
                        <input
                          type="checkbox"
                          checked={features[key] ?? false}
                          onChange={(e) =>
                            setFeatures((prev) => ({
                              ...prev,
                              [key]: e.target.checked,
                            }))
                          }
                          className="h-4 w-4 shrink-0 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        />
                        <span className="text-sm font-medium text-[color:var(--text)]">
                          {key
                            .replace(/_/g, " ")
                            .replace(/\b\w/g, (c) => c.toUpperCase())}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" onClick={goBack}>
                <ArrowLeft className="h-4 w-4" /> Back
              </Button>
              <Button onClick={handleSaveFeatures} className="ml-auto">
                Save & Continue <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        );
      }

      case "checklist":
        return (
          <div className="space-y-6">
            {onboardingStatus && onboardingStatus.steps.length > 0 ? (
              <>
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-2 rounded-full bg-[color:var(--surface-muted)] overflow-hidden">
                    <div
                      className="h-full bg-blue-500 rounded-full transition-all"
                      style={{ width: `${onboardingStatus.progress_pct}%` }}
                    />
                  </div>
                  <span className="text-sm font-medium text-[color:var(--text-muted)]">
                    {onboardingStatus.progress_pct}%
                  </span>
                </div>
                <div className="space-y-3">
                  {onboardingStatus.steps.map((s) => (
                    <div
                      key={s.step_key}
                      className={`flex items-start gap-3 rounded-lg border p-4 ${
                        s.completed
                          ? "border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950"
                          : "border-[color:var(--border)]"
                      }`}
                    >
                      {s.completed ? (
                        <CheckCircle2 className="h-5 w-5 text-green-600 mt-0.5 shrink-0" />
                      ) : (
                        <Circle className="h-5 w-5 text-[color:var(--text-muted)] mt-0.5 shrink-0" />
                      )}
                      <div>
                        <p className="text-sm font-medium text-[color:var(--text)]">
                          {s.label}
                        </p>
                        {s.description && (
                          <p className="text-xs text-[color:var(--text-muted)] mt-1">
                            {s.description}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="rounded-lg border border-blue-200 bg-blue-50 dark:border-blue-900 dark:bg-blue-950 p-4 text-sm">
                <p className="text-[color:var(--text)]">
                  Your organization is set up. You can complete the
                  remaining setup tasks from the dashboard at any time.
                </p>
              </div>
            )}
            <div className="flex gap-3 pt-2">
              <Button variant="outline" onClick={goBack}>
                <ArrowLeft className="h-4 w-4" /> Back
              </Button>
              <Button onClick={handleFinish} className="ml-auto">
                <Check className="h-4 w-4" /> Go to Dashboard
              </Button>
            </div>
          </div>
        );
    }
  };

  return (
    <DashboardShell>
      <SignedOut>
        <div className="lg:col-span-2 flex min-h-[70vh] items-center justify-center">
          <div className="w-full max-w-2xl rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] shadow-sm">
            <div className="border-b border-[color:var(--border)] px-6 py-5">
              <h1 className="text-2xl font-semibold tracking-tight text-[color:var(--text)]">
                Welcome to VantageClaw
              </h1>
              <p className="mt-1 text-sm text-[color:var(--text-muted)]">
                Sign in to set up your organization.
              </p>
            </div>
            <div className="px-6 py-6">
              <SignInButton
                mode="modal"
                forceRedirectUrl="/onboarding"
                signUpForceRedirectUrl="/onboarding"
              >
                <Button size="lg">Sign in</Button>
              </SignInButton>
            </div>
          </div>
        </div>
      </SignedOut>
      <SignedIn>
        <div className="lg:col-span-2 flex min-h-[70vh] items-center justify-center px-4">
          <div className="w-full max-w-3xl">
            {/* Stepper */}
            <nav className="mb-8">
              <ol className="flex items-center gap-1 sm:gap-2">
                {STEPS.map((s, i) => {
                  const Icon = s.icon;
                  const isActive = s.key === step;
                  const isPast = i < stepIndex;
                  return (
                    <li key={s.key} className="flex items-center gap-1 sm:gap-2 flex-1 min-w-0">
                      <div
                        className={`flex items-center justify-center gap-1.5 sm:gap-2 rounded-full px-2 py-1 sm:px-3 sm:py-1.5 text-xs font-medium transition-colors shrink-0 ${
                          isActive
                            ? "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-200"
                            : isPast
                              ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-200"
                              : "bg-[color:var(--surface-muted)] text-[color:var(--text-muted)]"
                        }`}
                      >
                        {/* Mobile: show check or step number. Desktop: show check or icon */}
                        {isPast ? (
                          <Check className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
                        ) : (
                          <>
                            <span className="sm:hidden text-[10px]">{i + 1}</span>
                            <Icon className="hidden sm:block h-3.5 w-3.5" />
                          </>
                        )}
                        <span className="hidden md:inline">{s.label}</span>
                      </div>
                      {i < STEPS.length - 1 && (
                        <div
                          className={`h-px flex-1 min-w-2 ${
                            isPast ? "bg-green-300 dark:bg-green-700" : "bg-[color:var(--border)]"
                          }`}
                        />
                      )}
                    </li>
                  );
                })}
              </ol>
            </nav>

            {/* Card */}
            <section className="rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] shadow-sm">
              <div className="border-b border-[color:var(--border)] px-6 py-5">
                <h1 className="text-xl font-semibold tracking-tight text-[color:var(--text)]">
                  {STEPS[stepIndex].label}
                </h1>
                <p className="mt-1 text-sm text-[color:var(--text-muted)]">
                  Step {stepIndex + 1} of {STEPS.length}
                </p>
              </div>
              <div className="px-6 py-6">
                {error && (
                  <div className="mb-4 rounded-lg border border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950 p-3 text-sm text-red-700 dark:text-red-300">
                    {error}
                  </div>
                )}
                {renderStep()}
              </div>
            </section>
          </div>
        </div>
      </SignedIn>
    </DashboardShell>
  );
}
