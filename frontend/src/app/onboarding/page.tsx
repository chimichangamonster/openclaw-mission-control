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
  RotateCcw,
  Save,
  Settings,
  User,
} from "lucide-react";

import { ApiError } from "@/api/mutator";
import {
  type getMeApiV1UsersMeGetResponse,
  useGetMeApiV1UsersMeGet,
  useUpdateMeApiV1UsersMePatch,
} from "@/api/generated/users/users";
import { customFetch } from "@/api/mutator";
import { DashboardShell } from "@/components/templates/DashboardShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import SearchableSelect from "@/components/ui/searchable-select";
import { isOnboardingComplete } from "@/lib/onboarding";
import { getSupportedTimezones } from "@/lib/timezones";
import { getApiBaseUrl } from "@/lib/api-base";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type IndustryTemplate = {
  id: string;
  name: string;
  description: string;
  icon: string;
  skill_count: number;
  config_categories: string[];
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

  const updateMeMutation = useUpdateMeApiV1UsersMePatch<ApiError>({
    mutation: {
      onSuccess: () => {
        setProfileSaved(true);
        setStep("industry");
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

  // If profile already complete, skip to industry step
  useEffect(() => {
    if (profile && isOnboardingComplete(profile) && !profileSaved) {
      setProfileSaved(true);
      setStep("industry");
    }
  }, [profile, profileSaved]);

  // Load templates
  useEffect(() => {
    if (!isSignedIn) return;
    const baseUrl = getApiBaseUrl();
    customFetch<{ status: number; data: IndustryTemplate[] }>(
      `${baseUrl}/api/v1/industry-templates`,
      { method: "GET" },
    ).then((res) => {
      if (res.status === 200) setTemplates(res.data);
    }).catch(() => {});
  }, [isSignedIn]);

  // Load feature flags
  const loadFeatures = useCallback(async () => {
    const baseUrl = getApiBaseUrl();
    try {
      const res = await customFetch<{ status: number; data: Record<string, boolean> }>(
        `${baseUrl}/api/v1/organization-settings/feature-flags`,
        { method: "GET" },
      );
      if (res.status === 200) setFeatures(res.data);
    } catch {
      // fallback
    }
  }, []);

  // Load onboarding status
  const loadOnboardingStatus = useCallback(async () => {
    const baseUrl = getApiBaseUrl();
    try {
      const res = await customFetch<{ status: number; data: OnboardingStatus }>(
        `${baseUrl}/api/v1/industry-templates/onboarding/status`,
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

  const handleApplyTemplate = async (templateId: string) => {
    const baseUrl = getApiBaseUrl();
    setError(null);
    try {
      await customFetch(`${baseUrl}/api/v1/industry-templates/${templateId}/apply`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      setSelectedTemplate(templateId);
      setTemplateApplied(true);
      await loadFeatures();
      setStep("api-key");
    } catch {
      setError("Failed to apply template.");
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
    const baseUrl = getApiBaseUrl();
    setError(null);
    try {
      await customFetch(`${baseUrl}/api/v1/organization-settings/openrouter-key`, {
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
    const baseUrl = getApiBaseUrl();
    setError(null);
    try {
      await customFetch(`${baseUrl}/api/v1/organization-settings/feature-flags`, {
        method: "PUT",
        body: JSON.stringify(features),
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

      case "industry":
        return (
          <div className="space-y-6">
            <p className="text-sm text-[color:var(--text-muted)]">
              Select your industry to pre-configure features, skills, and settings.
              You can customize everything later.
            </p>
            <div className="grid gap-4 md:grid-cols-2">
              {templates.map((t) => (
                <button
                  key={t.id}
                  onClick={() => handleApplyTemplate(t.id)}
                  className={`text-left rounded-xl border p-4 transition-all hover:shadow-md ${
                    selectedTemplate === t.id
                      ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
                      : "border-[color:var(--border)] hover:border-blue-300"
                  }`}
                >
                  <div className="flex items-center gap-3 mb-2">
                    <span className="text-2xl">{t.icon}</span>
                    <h3 className="font-semibold text-[color:var(--text)]">
                      {t.name}
                    </h3>
                  </div>
                  <p className="text-sm text-[color:var(--text-muted)]">
                    {t.description}
                  </p>
                  <div className="mt-3 flex items-center gap-2 text-xs text-[color:var(--text-muted)]">
                    <Layers className="h-3 w-3" />
                    {t.skill_count} skills
                  </div>
                </button>
              ))}
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" onClick={goBack}>
                <ArrowLeft className="h-4 w-4" /> Back
              </Button>
              <Button variant="outline" onClick={handleSkipTemplate} className="ml-auto">
                Skip for now <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        );

      case "api-key":
        return (
          <div className="space-y-6">
            <p className="text-sm text-[color:var(--text-muted)]">
              VantageClaw uses OpenRouter to connect to AI models. Add your API key
              to get started, or skip to use the platform default.
            </p>
            <div className="space-y-2">
              <label className="text-sm font-medium text-[color:var(--text)] flex items-center gap-2">
                <Key className="h-4 w-4 text-[color:var(--text-muted)]" />
                OpenRouter API Key
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
              <Button onClick={handleSaveApiKey} className="ml-auto">
                {apiKey.trim() ? "Save Key &" : "Skip &"} Continue{" "}
                <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        );

      case "features":
        return (
          <div className="space-y-6">
            <p className="text-sm text-[color:var(--text-muted)]">
              Enable the features your organization needs. You can change these
              anytime in Org Settings.
            </p>
            <div className="grid gap-3 md:grid-cols-2">
              {Object.entries(features).map(([key, enabled]) => (
                <label
                  key={key}
                  className="flex items-center gap-3 rounded-lg border border-[color:var(--border)] p-3 cursor-pointer hover:bg-[color:var(--surface-muted)] transition-colors"
                >
                  <input
                    type="checkbox"
                    checked={enabled}
                    onChange={(e) =>
                      setFeatures((prev) => ({
                        ...prev,
                        [key]: e.target.checked,
                      }))
                    }
                    className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-sm font-medium text-[color:var(--text)]">
                    {key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                  </span>
                </label>
              ))}
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
              <ol className="flex items-center gap-2">
                {STEPS.map((s, i) => {
                  const Icon = s.icon;
                  const isActive = s.key === step;
                  const isPast = i < stepIndex;
                  return (
                    <li key={s.key} className="flex items-center gap-2 flex-1">
                      <div
                        className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                          isActive
                            ? "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-200"
                            : isPast
                              ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-200"
                              : "bg-[color:var(--surface-muted)] text-[color:var(--text-muted)]"
                        }`}
                      >
                        {isPast ? (
                          <Check className="h-3.5 w-3.5" />
                        ) : (
                          <Icon className="h-3.5 w-3.5" />
                        )}
                        <span className="hidden sm:inline">{s.label}</span>
                      </div>
                      {i < STEPS.length - 1 && (
                        <div
                          className={`h-px flex-1 ${
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
