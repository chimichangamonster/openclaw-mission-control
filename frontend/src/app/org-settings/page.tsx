"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Key, Shield, Save, Trash2, Eye, EyeOff, AlertTriangle, DollarSign,
  Server, Upload, Image, ShieldCheck, Globe, CheckCircle2, XCircle, Loader2,
} from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { customFetch } from "@/api/mutator";

interface OrgSettings {
  openrouter_api_key: string | null;
  has_openrouter_key: boolean;
  openrouter_management_key: string | null;
  has_management_key: boolean;
  adobe_pdf_client_id: string | null;
  has_adobe_pdf_key: boolean;
  default_model_tier_max: number;
  configured_models: string[];
  feature_flags: Record<string, boolean>;
  agent_defaults: Record<string, unknown>;
  branding: Record<string, unknown>;
  logo_url: string | null;
  has_logo: boolean;
  has_custom_llm_endpoint: boolean;
  custom_llm_endpoint_name: string | null;
  custom_llm_endpoint_url: string | null;
  data_policy: {
    redaction_level: string;
    allow_email_content_to_llm: boolean;
    log_llm_inputs: boolean;
  };
  timezone: string;
  location: string;
  member_role: string;
  is_admin: boolean;
}

interface LLMRouting {
  configured: boolean;
  source: string | null;
  name: string | null;
  api_url: string | null;
  is_openrouter: boolean;
  models: string[];
  data_stays_private: boolean;
}

interface AuditEntry {
  id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: Record<string, unknown>;
  user_id: string | null;
  ip_address: string | null;
  created_at: string;
}

// ─── Interactive Cost Calculator ──────────────────────────────────────────────

function CostCalculator({
  t1Cost, t2Cost, t3Cost, cronCostT2, cronCostT3,
  hasRealData, projectedMonthly, daysTracked, dailyAvg, totalSpend,
}: {
  t1Cost: number; t2Cost: number; t3Cost: number;
  cronCostT2: number; cronCostT3: number;
  hasRealData: boolean; projectedMonthly: number | null;
  daysTracked: number; dailyAvg: number | null; totalSpend: number;
}) {
  const [users, setUsers] = useState(5);
  const [convsPerUser, setConvsPerUser] = useState(5);
  const [agents, setAgents] = useState(3);
  const [tier3Pct, setTier3Pct] = useState(30);
  const [cronJobs, setCronJobs] = useState(3);
  const [cronTier3Pct, setCronTier3Pct] = useState(50);

  const dailyConversations = users * convsPerUser;
  const tier3Fraction = tier3Pct / 100;
  const tier2Fraction = 1 - tier3Fraction;
  const avgConvCost = tier2Fraction * t2Cost + tier3Fraction * t3Cost;
  const dailyCost = dailyConversations * avgConvCost;

  const cronTier3Frac = cronTier3Pct / 100;
  const avgCronCost = (1 - cronTier3Frac) * cronCostT2 + cronTier3Frac * cronCostT3;
  const dailyCronCost = cronJobs * avgCronCost; // assume ~1 run/day avg

  const monthlyCost = (dailyCost + dailyCronCost) * 30;
  const annualCost = monthlyCost * 12;

  const SliderRow = ({ label, value, setValue, min, max, step, unit, hint }: {
    label: string; value: number; setValue: (v: number) => void;
    min: number; max: number; step: number; unit: string; hint?: string;
  }) => (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="text-xs text-slate-600">{label}</label>
        <span className="text-xs font-mono font-semibold text-slate-800">{value}{unit}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => setValue(Number(e.target.value))}
        className="w-full h-1.5 rounded-full appearance-none cursor-pointer bg-slate-200 accent-blue-600"
      />
      <div className="flex justify-between text-[9px] text-slate-400 mt-0.5">
        <span>{min}{unit}</span>
        {hint && <span>{hint}</span>}
        <span>{max}{unit}</span>
      </div>
    </div>
  );

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50/50 shadow-sm">
      <div className="px-5 py-4">
        <h2 className="text-sm font-semibold text-amber-900 flex items-center gap-2">
          <DollarSign className="h-4 w-4" /> AI Cost Calculator
        </h2>
        <p className="text-[11px] text-amber-600 mt-1">Adjust the sliders to estimate your monthly AI costs.</p>

        {/* Real data banner */}
        {hasRealData && projectedMonthly != null && (
          <div className="mt-3 rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2">
            <div className="flex items-baseline gap-2">
              <span className="text-lg font-bold text-emerald-800">${projectedMonthly}</span>
              <span className="text-[11px] text-emerald-600">/month based on actual usage</span>
            </div>
            <p className="text-[10px] text-emerald-600">
              {daysTracked} days tracked, ${dailyAvg}/day avg, ${totalSpend} total to date
            </p>
          </div>
        )}

        {/* Sliders */}
        <div className="mt-4 space-y-4">
          <SliderRow label="Team size (users)" value={users} setValue={setUsers} min={1} max={100} step={1} unit="" hint="who will interact with agents" />
          <SliderRow label="Conversations per user / day" value={convsPerUser} setValue={setConvsPerUser} min={1} max={20} step={1} unit="" hint="messages, commands, queries" />
          <SliderRow label="Active agents" value={agents} setValue={setAgents} min={1} max={20} step={1} unit="" />
          <SliderRow label="Reasoning model usage" value={tier3Pct} setValue={setTier3Pct} min={0} max={100} step={5} unit="%" hint="Tier 3 (Sonnet/Grok) vs Tier 2 (DeepSeek)" />
          <SliderRow label="Scheduled jobs (crons)" value={cronJobs} setValue={setCronJobs} min={0} max={30} step={1} unit="" />
          {cronJobs > 0 && (
            <SliderRow label="Cron reasoning model %" value={cronTier3Pct} setValue={setCronTier3Pct} min={0} max={100} step={10} unit="%" hint="% of cron jobs using Tier 3" />
          )}
        </div>

        {/* Result */}
        <div className="mt-4 rounded-lg bg-white border border-amber-200 px-4 py-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-bold text-amber-900">${monthlyCost.toFixed(2)}</span>
                <span className="text-xs text-amber-600">/month</span>
              </div>
              <p className="text-[10px] text-slate-500 mt-0.5">${annualCost.toFixed(0)}/year · ${dailyCost.toFixed(2)}/day conversations · ${(dailyCronCost * 30).toFixed(2)}/mo crons</p>
            </div>
            <div className="text-right">
              <p className="text-[10px] text-slate-500">{dailyConversations} conv/day</p>
              <p className="text-[10px] text-slate-500">${avgConvCost.toFixed(4)}/conv avg</p>
            </div>
          </div>

          {/* Cost breakdown bar */}
          <div className="mt-2 flex h-2 rounded-full overflow-hidden bg-slate-100">
            {tier2Fraction > 0 && <div className="bg-blue-400 transition-all" style={{ width: `${tier2Fraction * 100}%` }} />}
            {tier3Fraction > 0 && <div className="bg-purple-500 transition-all" style={{ width: `${tier3Fraction * 100}%` }} />}
          </div>
          <div className="flex justify-between text-[9px] mt-1">
            <span className="text-blue-600">Tier 2 Standard — ${t2Cost.toFixed(4)}/conv</span>
            <span className="text-purple-600">Tier 3 Reasoning — ${t3Cost.toFixed(4)}/conv</span>
          </div>
        </div>

        <div className="mt-3 flex items-center gap-2">
          <a
            href="/costs"
            className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700 transition"
          >
            Set Budget Cap
          </a>
          <span className="text-[10px] text-amber-600">Prevent unexpected charges by setting a monthly limit</span>
        </div>
      </div>
    </div>
  );
}

export default function OrgSettingsPage() {
  const { isSignedIn } = useAuth();
  const [settings, setSettings] = useState<OrgSettings | null>(null);
  const [llmRouting, setLlmRouting] = useState<LLMRouting | null>(null);
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Key input state
  const [newOrKey, setNewOrKey] = useState("");
  const [newMgmtKey, setNewMgmtKey] = useState("");
  const [showOrKey, setShowOrKey] = useState(false);
  const [showMgmtKey, setShowMgmtKey] = useState(false);

  // Feature flags edit state
  const [editFlags, setEditFlags] = useState<Record<string, boolean>>({});
  const [tierMax, setTierMax] = useState(3);

  // Custom LLM endpoint state
  const [llmUrl, setLlmUrl] = useState("");
  const [llmKey, setLlmKey] = useState("");
  const [llmName, setLlmName] = useState("Custom LLM");
  const [llmModels, setLlmModels] = useState("");
  const [showLlmKey, setShowLlmKey] = useState(false);
  const [savingLlm, setSavingLlm] = useState(false);
  const [healthStatus, setHealthStatus] = useState<{ ok: boolean; latency_ms?: number; error?: string } | null>(null);
  const [checkingHealth, setCheckingHealth] = useState(false);

  // Logo upload state
  const [uploadingLogo, setUploadingLogo] = useState(false);
  const logoInputRef = useRef<HTMLInputElement>(null);

  // Data policy state
  const [redactionLevel, setRedactionLevel] = useState("moderate");
  const [allowEmailToLlm, setAllowEmailToLlm] = useState(true);
  const [logLlmInputs, setLogLlmInputs] = useState(false);
  const [savingPolicy, setSavingPolicy] = useState(false);

  // Timezone & location
  const [editTimezone, setEditTimezone] = useState("America/Edmonton");
  const [editLocation, setEditLocation] = useState("");
  const [savingLocale, setSavingLocale] = useState(false);

  // Cost estimate state
  const [costEstimate, setCostEstimate] = useState<{
    has_real_data: boolean;
    days_tracked: number;
    projected_monthly: number | null;
    daily_avg: number | null;
    total_spend_to_date: number;
    tier_costs: { tier: string; model: string; per_conversation: number; per_100_conversations: number }[];
    examples: { description: string; monthly_est: number }[];
    note: string;
  } | null>(null);
  const [showBudgetPrompt, setShowBudgetPrompt] = useState(false);

  // Microsoft Graph state
  const [connectingGraph, setConnectingGraph] = useState(false);
  const [graphStatus, setGraphStatus] = useState<{ connected: boolean; email?: string } | null>(null);

  // Google Calendar state
  const [connectingGcal, setConnectingGcal] = useState(false);
  const [gcalStatus, setGcalStatus] = useState<{ connected: boolean; email?: string } | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [settingsRaw, auditRaw, routingRaw, estimateRaw, gcalRaw, graphRaw]: any[] = await Promise.all([
        customFetch("/api/v1/organization-settings", { method: "GET" }).catch(() => null),
        customFetch("/api/v1/organization-settings/audit-log?limit=20", { method: "GET" }).catch(() => null),
        customFetch("/api/v1/organization-settings/llm-routing", { method: "GET" }).catch(() => null),
        customFetch("/api/v1/cost-tracker/cost-estimate", { method: "GET" }).catch(() => null),
        customFetch("/api/v1/google-calendar/status", { method: "GET" }).catch(() => null),
        customFetch("/api/v1/microsoft-graph/status", { method: "GET" }).catch(() => null),
      ]);
      const gcData = gcalRaw?.data ?? gcalRaw;
      if (gcData) setGcalStatus(gcData);
      const grData = graphRaw?.data ?? graphRaw;
      if (grData) setGraphStatus(grData);
      const sData = settingsRaw?.data ?? settingsRaw;
      if (sData) {
        setSettings(sData as OrgSettings);
        setEditFlags(sData.feature_flags || {});
        setTierMax(sData.default_model_tier_max || 3);
        // Sync data policy state
        if (sData.data_policy) {
          setRedactionLevel(sData.data_policy.redaction_level || "moderate");
          setAllowEmailToLlm(sData.data_policy.allow_email_content_to_llm ?? true);
          setLogLlmInputs(sData.data_policy.log_llm_inputs ?? false);
        }
        // Sync timezone & location
        if (sData.timezone) setEditTimezone(sData.timezone);
        if (sData.location !== undefined) setEditLocation(sData.location);
      }
      const aData = auditRaw?.data ?? auditRaw;
      if (aData?.entries) setAuditLog(aData.entries as AuditEntry[]);
      const rData = routingRaw?.data ?? routingRaw;
      if (rData) setLlmRouting(rData as LLMRouting);
      const eData = estimateRaw?.data ?? estimateRaw;
      if (eData?.tier_costs) setCostEstimate(eData);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isSignedIn) loadData();
  }, [isSignedIn, loadData]);

  const saveSettings = async () => {
    try {
      setSaving(true);
      await customFetch("/api/v1/organization-settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          default_model_tier_max: tierMax,
          feature_flags: editFlags,
        }),
      });
      await loadData();
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  };

  const setOrKey = async () => {
    if (!newOrKey.trim()) return;
    const hadKey = settings?.has_openrouter_key;
    await customFetch("/api/v1/organization-settings/openrouter-key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: newOrKey.trim() }),
    });
    setNewOrKey("");
    await loadData();
    if (!hadKey) setShowBudgetPrompt(true);
  };

  const removeOrKey = async () => {
    await customFetch("/api/v1/organization-settings/openrouter-key", { method: "DELETE" });
    await loadData();
  };

  const setMgmtKey = async () => {
    if (!newMgmtKey.trim()) return;
    await customFetch("/api/v1/organization-settings/management-key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: newMgmtKey.trim() }),
    });
    setNewMgmtKey("");
    await loadData();
  };

  const removeMgmtKey = async () => {
    await customFetch("/api/v1/organization-settings/management-key", { method: "DELETE" });
    await loadData();
  };

  // Custom LLM endpoint
  const saveCustomLlm = async () => {
    if (!llmUrl.trim() || !llmKey.trim()) return;
    try {
      setSavingLlm(true);
      await customFetch("/api/v1/organization-settings/custom-llm-endpoint", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_url: llmUrl.trim(),
          api_key: llmKey.trim(),
          name: llmName.trim() || "Custom LLM",
          models: llmModels.split(",").map((m) => m.trim()).filter(Boolean),
        }),
      });
      setLlmUrl("");
      setLlmKey("");
      setLlmName("Custom LLM");
      setLlmModels("");
      setHealthStatus(null);
      await loadData();
    } finally {
      setSavingLlm(false);
    }
  };

  const removeCustomLlm = async () => {
    await customFetch("/api/v1/organization-settings/custom-llm-endpoint", { method: "DELETE" });
    setHealthStatus(null);
    await loadData();
  };

  const checkLlmHealth = async () => {
    try {
      setCheckingHealth(true);
      const raw: any = await customFetch("/api/v1/organization-settings/custom-llm-endpoint/health", { method: "POST" });
      const data = raw?.data ?? raw;
      setHealthStatus(data);
    } catch (e: any) {
      setHealthStatus({ ok: false, error: e?.message || "Health check failed" });
    } finally {
      setCheckingHealth(false);
    }
  };

  // Logo upload
  const uploadLogo = async (file: File) => {
    try {
      setUploadingLogo(true);
      const formData = new FormData();
      formData.append("file", file);
      await customFetch("/api/v1/organization-settings/logo", {
        method: "POST",
        body: formData,
      });
      await loadData();
    } finally {
      setUploadingLogo(false);
    }
  };

  const removeLogo = async () => {
    await customFetch("/api/v1/organization-settings/logo", { method: "DELETE" });
    await loadData();
  };

  // Data policy
  const saveDataPolicy = async () => {
    try {
      setSavingPolicy(true);
      await customFetch("/api/v1/organization-settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          data_policy: {
            redaction_level: redactionLevel,
            allow_email_content_to_llm: allowEmailToLlm,
            log_llm_inputs: logLlmInputs,
          },
        }),
      });
      await loadData();
    } finally {
      setSavingPolicy(false);
    }
  };

  // Microsoft Graph
  const connectMicrosoftGraph = async () => {
    try {
      setConnectingGraph(true);
      const raw: any = await customFetch("/api/v1/microsoft-graph/authorize", { method: "GET" });
      const data = raw?.data ?? raw;
      if (data?.authorization_url) {
        window.open(data.authorization_url, "_blank", "width=600,height=700");
      }
    } catch {
      // ignore — feature may be disabled
    } finally {
      setConnectingGraph(false);
    }
  };

  // Google Calendar
  const connectGoogleCalendar = async () => {
    try {
      setConnectingGcal(true);
      const raw: any = await customFetch("/api/v1/google-calendar/authorize", { method: "GET" });
      const data = raw?.data ?? raw;
      if (data?.authorization_url) {
        window.open(data.authorization_url, "_blank", "width=600,height=700");
      }
    } catch {
      // ignore — feature may be disabled
    } finally {
      setConnectingGcal(false);
    }
  };

  if (!isSignedIn) return null;

  return (
    <DashboardPageLayout
      signedOut={{ message: "Sign in to view organization settings.", forceRedirectUrl: "/org-settings", signUpForceRedirectUrl: "/org-settings" }}
      title="Organization Settings"
      description="API keys, integrations, data policy, and audit trail."
    >
      <div className="mx-auto max-w-3xl space-y-6 p-6">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Organization Settings</h1>
          <p className="text-sm text-slate-500">API keys, integrations, data policy, and audit trail</p>
        </div>

        {/* Admin Warning */}
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-3 flex gap-3">
          <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-amber-800">Admin-only settings</p>
            <p className="text-xs text-amber-700 mt-0.5">
              These settings control how your organization&apos;s agents operate. Changing API keys, model tiers, or feature flags can affect agent behavior and costs. If you&apos;re unsure about a setting, leave it at the default — the platform is pre-configured for optimal performance.
            </p>
          </div>
        </div>

        {loading ? (
          <div className="text-center text-sm text-slate-500 py-12">Loading...</div>
        ) : settings ? (
          <>
            {/* LLM Routing Status */}
            {llmRouting && (
              <div className={`rounded-xl border px-5 py-4 flex items-center gap-3 ${llmRouting.configured ? "border-emerald-200 bg-emerald-50" : "border-red-200 bg-red-50"}`}>
                {llmRouting.configured ? (
                  <CheckCircle2 className="h-5 w-5 text-emerald-500 shrink-0" />
                ) : (
                  <XCircle className="h-5 w-5 text-red-500 shrink-0" />
                )}
                <div className="flex-1">
                  <p className={`text-sm font-medium ${llmRouting.configured ? "text-emerald-800" : "text-red-800"}`}>
                    {llmRouting.configured ? `LLM Routing: ${llmRouting.name}` : "LLM Routing: Not Configured"}
                  </p>
                  <p className={`text-xs ${llmRouting.configured ? "text-emerald-600" : "text-red-600"}`}>
                    {llmRouting.configured
                      ? `Source: ${llmRouting.source}${llmRouting.data_stays_private ? " — data stays on your infrastructure" : " — via OpenRouter"}`
                      : "Add an OpenRouter API key or custom endpoint below to enable AI agents."}
                  </p>
                </div>
              </div>
            )}

            {/* API Keys */}
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-5 py-3">
                <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                  <Key className="h-4 w-4" /> API Keys
                </h2>
                <p className="text-xs text-slate-500">Bring your own OpenRouter keys. Falls back to platform default if not set.</p>
              </div>
              <div className="p-5 space-y-4">
                {/* Provider ToS Notice */}
                <div className="rounded-lg border border-blue-200 bg-blue-50/50 px-4 py-3">
                  <p className="text-xs font-medium text-blue-800">Provider Compliance</p>
                  <p className="text-[11px] text-blue-700 mt-1 leading-relaxed">
                    Use <strong>API keys</strong> from OpenRouter or provider developer consoles (console.anthropic.com, platform.openai.com, etc.).
                    Do not use OAuth tokens from personal subscriptions (Claude Pro/Max, ChatGPT Plus) — provider Terms of Service prohibit
                    routing personal plan credentials through third-party platforms.
                  </p>
                </div>

                {/* OpenRouter API Key */}
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">OpenRouter API Key</label>
                  {settings.has_openrouter_key ? (
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-mono text-slate-700 bg-slate-50 rounded px-2 py-1 flex-1">{settings.openrouter_api_key}</span>
                      <button onClick={removeOrKey} className="rounded-lg p-1.5 text-red-400 hover:text-red-600 hover:bg-red-50 transition">
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <div className="relative flex-1">
                        <input
                          type={showOrKey ? "text" : "password"}
                          value={newOrKey}
                          onChange={(e) => setNewOrKey(e.target.value)}
                          placeholder="sk-or-..."
                          className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-mono text-slate-800 pr-8 focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
                        />
                        <button onClick={() => setShowOrKey(!showOrKey)} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400">
                          {showOrKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                        </button>
                      </div>
                      <button onClick={setOrKey} disabled={!newOrKey.trim()} className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition">
                        Save
                      </button>
                    </div>
                  )}
                  <p className={`text-[10px] mt-1 ${settings.has_openrouter_key ? "text-emerald-500" : "text-amber-500"}`}>
                    {settings.has_openrouter_key ? "Using your own key — costs billed to your OpenRouter account" : "No key set — required for agents to make LLM calls. Get a key at openrouter.ai"}
                  </p>
                </div>

                {/* Management Key */}
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">OpenRouter Management Key</label>
                  {settings.has_management_key ? (
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-mono text-slate-700 bg-slate-50 rounded px-2 py-1 flex-1">{settings.openrouter_management_key}</span>
                      <button onClick={removeMgmtKey} className="rounded-lg p-1.5 text-red-400 hover:text-red-600 hover:bg-red-50 transition">
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <div className="relative flex-1">
                        <input
                          type={showMgmtKey ? "text" : "password"}
                          value={newMgmtKey}
                          onChange={(e) => setNewMgmtKey(e.target.value)}
                          placeholder="sk-or-mgmt-..."
                          className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-mono text-slate-800 pr-8 focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
                        />
                        <button onClick={() => setShowMgmtKey(!showMgmtKey)} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400">
                          {showMgmtKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                        </button>
                      </div>
                      <button onClick={setMgmtKey} disabled={!newMgmtKey.trim()} className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition">
                        Save
                      </button>
                    </div>
                  )}
                  <p className={`text-[10px] mt-1 ${settings.has_management_key ? "text-emerald-500" : "text-slate-400"}`}>
                    {settings.has_management_key ? "Using your own key" : "Optional — enables detailed spending history from OpenRouter"}
                  </p>
                </div>
              </div>
            </div>

            {/* AI Cost Calculator — interactive estimator */}
            {(llmRouting?.configured || settings.has_openrouter_key) && costEstimate && (() => {
              // Tier pricing from backend (per conversation)
              const tierMap = Object.fromEntries(costEstimate.tier_costs.map((t) => [t.tier.split(" ")[0] + " " + t.tier.split(" ")[2], t.per_conversation]));
              const t1Cost = costEstimate.tier_costs[0]?.per_conversation ?? 0.0003;
              const t2Cost = costEstimate.tier_costs[1]?.per_conversation ?? 0.001;
              const t3Cost = costEstimate.tier_costs[2]?.per_conversation ?? 0.02;
              const cronCostT2 = t2Cost * 2; // crons use ~2x tokens
              const cronCostT3 = t3Cost * 2;

              return (
                <CostCalculator
                  t1Cost={t1Cost}
                  t2Cost={t2Cost}
                  t3Cost={t3Cost}
                  cronCostT2={cronCostT2}
                  cronCostT3={cronCostT3}
                  hasRealData={costEstimate.has_real_data}
                  projectedMonthly={costEstimate.projected_monthly}
                  daysTracked={costEstimate.days_tracked}
                  dailyAvg={costEstimate.daily_avg}
                  totalSpend={costEstimate.total_spend_to_date}
                />
              );
            })()}

            {/* Budget Setup Prompt — appears after first key save */}
            {showBudgetPrompt && (
              <div className="rounded-xl border-2 border-red-300 bg-red-50 shadow-sm animate-[slideDown_0.3s_ease-out]">
                <div className="px-5 py-4">
                  <h2 className="text-sm font-semibold text-red-900 flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-red-500" /> Set a Budget Before Agents Start Spending
                  </h2>
                  <p className="mt-2 text-xs text-red-800 leading-relaxed">
                    Your API key is now active. Agents and cron jobs will begin using LLM tokens, which cost real money.
                    Without a budget cap, there is no limit on how much agents can spend.
                  </p>
                  <div className="mt-3 flex items-center gap-3">
                    <a
                      href="/costs"
                      className="rounded-lg bg-red-600 px-4 py-2 text-xs font-semibold text-white hover:bg-red-700 transition"
                    >
                      Set Budget Now
                    </a>
                    <button
                      onClick={() => setShowBudgetPrompt(false)}
                      className="text-xs text-red-500 hover:text-red-700 transition"
                    >
                      I'll do this later
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Custom LLM Endpoint */}
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-5 py-3">
                <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                  <Server className="h-4 w-4" /> Custom LLM Endpoint
                </h2>
                <p className="text-xs text-slate-500">Connect a self-hosted LLM for enterprise deployments. Data never leaves your infrastructure.</p>
              </div>
              <div className="p-5 space-y-4">
                {settings.has_custom_llm_endpoint ? (
                  <>
                    <div className="rounded-lg bg-slate-50 p-3 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-slate-800">{settings.custom_llm_endpoint_name}</span>
                        <button onClick={removeCustomLlm} className="rounded-lg p-1.5 text-red-400 hover:text-red-600 hover:bg-red-50 transition">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                      <p className="text-xs font-mono text-slate-500">{settings.custom_llm_endpoint_url}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={checkLlmHealth}
                        disabled={checkingHealth}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition"
                      >
                        {checkingHealth ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                        {checkingHealth ? "Checking..." : "Health Check"}
                      </button>
                      {healthStatus && (
                        <span className={`text-xs ${healthStatus.ok ? "text-emerald-600" : "text-red-600"}`}>
                          {healthStatus.ok ? `Healthy (${healthStatus.latency_ms}ms)` : healthStatus.error || "Unreachable"}
                        </span>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Endpoint Name</label>
                      <input
                        type="text"
                        value={llmName}
                        onChange={(e) => setLlmName(e.target.value)}
                        placeholder="e.g., Corp vLLM Cluster"
                        className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-800 focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">API URL</label>
                      <input
                        type="url"
                        value={llmUrl}
                        onChange={(e) => setLlmUrl(e.target.value)}
                        placeholder="https://llm.corp.internal/v1"
                        className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-mono text-slate-800 focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">API Key</label>
                      <div className="relative">
                        <input
                          type={showLlmKey ? "text" : "password"}
                          value={llmKey}
                          onChange={(e) => setLlmKey(e.target.value)}
                          placeholder="sk-..."
                          className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-mono text-slate-800 pr-8 focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
                        />
                        <button onClick={() => setShowLlmKey(!showLlmKey)} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400">
                          {showLlmKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                        </button>
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Available Models (comma-separated)</label>
                      <input
                        type="text"
                        value={llmModels}
                        onChange={(e) => setLlmModels(e.target.value)}
                        placeholder="llama-3.1-70b, mistral-large"
                        className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-800 focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
                      />
                      <p className="text-[10px] text-slate-400 mt-1">Optional — helps agents know which models are available on your endpoint.</p>
                    </div>
                    <div className="flex justify-end">
                      <button
                        onClick={saveCustomLlm}
                        disabled={savingLlm || !llmUrl.trim() || !llmKey.trim()}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition"
                      >
                        <Save className="h-3.5 w-3.5" />
                        {savingLlm ? "Saving..." : "Save Endpoint"}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Logo & Branding */}
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-5 py-3">
                <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                  <Image className="h-4 w-4" /> Logo & Branding
                </h2>
                <p className="text-xs text-slate-500">Your logo appears on generated documents (proposals, reports, invoices).</p>
              </div>
              <div className="p-5">
                {settings.has_logo && settings.logo_url ? (
                  <div className="flex items-center gap-4">
                    <div className="h-16 w-16 rounded-lg border border-slate-200 bg-slate-50 flex items-center justify-center overflow-hidden">
                      <img src={settings.logo_url} alt="Organization logo" className="max-h-full max-w-full object-contain" />
                    </div>
                    <div className="flex-1">
                      <p className="text-xs text-emerald-500">Logo uploaded</p>
                      <button onClick={removeLogo} className="mt-1 text-xs text-red-500 hover:text-red-700 transition">Remove logo</button>
                    </div>
                  </div>
                ) : (
                  <div>
                    <input
                      ref={logoInputRef}
                      type="file"
                      accept="image/png,image/jpeg,image/svg+xml,image/webp"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) uploadLogo(file);
                      }}
                    />
                    <button
                      onClick={() => logoInputRef.current?.click()}
                      disabled={uploadingLogo}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-dashed border-slate-300 px-4 py-3 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50 transition w-full justify-center"
                    >
                      <Upload className="h-4 w-4" />
                      {uploadingLogo ? "Uploading..." : "Upload Logo (PNG, JPG, SVG, WebP — max 5MB)"}
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Timezone & Location */}
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-5 py-3">
                <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                  <Globe className="h-4 w-4" /> Timezone & Location
                </h2>
                <p className="text-xs text-slate-500">Used for scheduling, cron jobs, and date formatting across the platform.</p>
              </div>
              <div className="p-5 space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Timezone</label>
                    <select
                      value={editTimezone}
                      onChange={(e) => setEditTimezone(e.target.value)}
                      className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
                    >
                      <optgroup label="North America">
                        <option value="America/Edmonton">Mountain Time (Edmonton)</option>
                        <option value="America/Vancouver">Pacific Time (Vancouver)</option>
                        <option value="America/Winnipeg">Central Time (Winnipeg)</option>
                        <option value="America/Toronto">Eastern Time (Toronto)</option>
                        <option value="America/Halifax">Atlantic Time (Halifax)</option>
                        <option value="America/St_Johns">Newfoundland (St. John&apos;s)</option>
                        <option value="America/New_York">Eastern Time (New York)</option>
                        <option value="America/Chicago">Central Time (Chicago)</option>
                        <option value="America/Denver">Mountain Time (Denver)</option>
                        <option value="America/Los_Angeles">Pacific Time (Los Angeles)</option>
                      </optgroup>
                      <optgroup label="International">
                        <option value="Europe/London">GMT (London)</option>
                        <option value="Europe/Paris">CET (Paris)</option>
                        <option value="Europe/Berlin">CET (Berlin)</option>
                        <option value="Asia/Dubai">GST (Dubai)</option>
                        <option value="Asia/Singapore">SGT (Singapore)</option>
                        <option value="Asia/Tokyo">JST (Tokyo)</option>
                        <option value="Australia/Sydney">AEST (Sydney)</option>
                        <option value="Pacific/Auckland">NZST (Auckland)</option>
                      </optgroup>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">Location</label>
                    <input
                      type="text"
                      value={editLocation}
                      onChange={(e) => setEditLocation(e.target.value)}
                      placeholder="Calgary, AB, Canada"
                      className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
                    />
                  </div>
                </div>
                <div className="flex justify-end">
                  <button
                    onClick={async () => {
                      try {
                        setSavingLocale(true);
                        await customFetch("/api/v1/organization-settings", {
                          method: "PUT",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ timezone: editTimezone, location: editLocation }),
                        });
                        await loadData();
                      } catch { /* ignore */ } finally {
                        setSavingLocale(false);
                      }
                    }}
                    disabled={savingLocale}
                    className="inline-flex items-center gap-2 rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 transition"
                  >
                    <Save className="h-3 w-3" />
                    {savingLocale ? "Saving..." : "Save"}
                  </button>
                </div>
              </div>
            </div>

            {/* Data Policy */}
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-5 py-3">
                <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4" /> Data Policy
                </h2>
                <p className="text-xs text-slate-500">Control how your data is handled when sent to AI models.</p>
              </div>
              <div className="p-5 space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Sensitive Data Redaction</label>
                  <select
                    value={redactionLevel}
                    onChange={(e) => setRedactionLevel(e.target.value)}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-800 focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
                  >
                    <option value="off">Off — no redaction (fastest, least private)</option>
                    <option value="moderate">Moderate — redact passwords, API keys, credit cards, SIN/SSN</option>
                    <option value="strict">Strict — redact all PII including emails, phone numbers, addresses</option>
                  </select>
                  <p className="text-[10px] text-slate-400 mt-1">Redaction strips sensitive data before it reaches LLM providers. Applied to emails, documents, and agent inputs.</p>
                </div>

                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-xs text-slate-700">
                    <input
                      type="checkbox"
                      checked={allowEmailToLlm}
                      onChange={(e) => setAllowEmailToLlm(e.target.checked)}
                      className="rounded border-slate-300"
                    />
                    Allow email content to be sent to LLM for processing
                  </label>
                  <p className="text-[10px] text-slate-400 ml-6">When disabled, agents can see email metadata (subject, sender, date) but not the body content.</p>
                </div>

                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-xs text-slate-700">
                    <input
                      type="checkbox"
                      checked={logLlmInputs}
                      onChange={(e) => setLogLlmInputs(e.target.checked)}
                      className="rounded border-slate-300"
                    />
                    Log LLM inputs for debugging
                  </label>
                  <p className="text-[10px] text-slate-400 ml-6">When enabled, prompts sent to LLMs are logged for troubleshooting. Disable for maximum privacy.</p>
                </div>

                <div className="flex justify-end">
                  <button
                    onClick={saveDataPolicy}
                    disabled={savingPolicy}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition"
                  >
                    <Save className="h-3.5 w-3.5" />
                    {savingPolicy ? "Saving..." : "Save Data Policy"}
                  </button>
                </div>
              </div>
            </div>

            {/* Microsoft Graph Integration */}
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-5 py-3">
                <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                  <Globe className="h-4 w-4" /> Microsoft 365 Integration
                </h2>
                <p className="text-xs text-slate-500">Connect Microsoft Graph for OneDrive, Calendar, and SharePoint access.</p>
              </div>
              <div className="p-5">
                {editFlags.microsoft_graph === false ? (
                  <p className="text-xs text-slate-400">Enable the &quot;microsoft graph&quot; feature flag above to use this integration.</p>
                ) : graphStatus?.connected ? (
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                      <span className="text-sm font-medium text-emerald-700">Connected</span>
                      <span className="text-xs text-emerald-600">{graphStatus.email}</span>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center gap-3">
                    <button
                      onClick={connectMicrosoftGraph}
                      disabled={connectingGraph}
                      className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition"
                    >
                      <svg className="h-4 w-4" viewBox="0 0 21 21" fill="none">
                        <rect width="10" height="10" fill="#F25022" />
                        <rect x="11" width="10" height="10" fill="#7FBA00" />
                        <rect y="11" width="10" height="10" fill="#00A4EF" />
                        <rect x="11" y="11" width="10" height="10" fill="#FFB900" />
                      </svg>
                      {connectingGraph ? "Connecting..." : "Connect Microsoft 365"}
                    </button>
                    <p className="text-[10px] text-slate-400">Opens Microsoft OAuth in a new window. Requires an admin Microsoft account.</p>
                  </div>
                )}
              </div>
            </div>

            {/* Google Calendar Integration */}
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-5 py-3">
                <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <path d="M19 4H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2V6a2 2 0 00-2-2z" stroke="#4285F4" strokeWidth="2" />
                    <path d="M16 2v4M8 2v4M3 10h18" stroke="#4285F4" strokeWidth="2" strokeLinecap="round" />
                    <circle cx="12" cy="15" r="2" fill="#34A853" />
                  </svg>
                  Google Calendar
                </h2>
                <p className="text-xs text-slate-500">Connect Google Calendar for scheduling meetings, site visits, and appointments.</p>
              </div>
              <div className="p-5">
                {editFlags.google_calendar === false ? (
                  <p className="text-xs text-slate-400">Enable the &quot;google calendar&quot; feature flag above to use this integration.</p>
                ) : gcalStatus?.connected ? (
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                      <span className="text-sm font-medium text-emerald-700">Connected</span>
                      <span className="text-xs text-emerald-600">{gcalStatus.email}</span>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center gap-3">
                    <button
                      onClick={connectGoogleCalendar}
                      disabled={connectingGcal}
                      className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition"
                    >
                      <svg className="h-4 w-4" viewBox="0 0 24 24">
                        <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
                        <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                        <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                        <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                      </svg>
                      {connectingGcal ? "Connecting..." : "Connect Google Calendar"}
                    </button>
                    <p className="text-[10px] text-slate-400">Opens Google OAuth in a new window. Uses your dedicated Google account.</p>
                  </div>
                )}
              </div>
            </div>

            {/* Feature Flags & Model Tier */}
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-5 py-3">
                <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                  <Shield className="h-4 w-4" /> Features & Limits
                </h2>
              </div>
              <div className="p-5 space-y-4">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Max Model Tier</label>
                  <select
                    value={tierMax}
                    onChange={(e) => setTierMax(parseInt(e.target.value))}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-800 focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
                  >
                    <option value={1}>Tier 1 — Nano only ($0.05-0.20/M)</option>
                    <option value={2}>Tier 2 — Standard ($0.26/M)</option>
                    <option value={3}>Tier 3 — Reasoning ($2-3/M) — Recommended</option>
                    <option value={4}>Tier 4 — Critical ($15/M) — Use with caution</option>
                  </select>
                  <p className="text-[10px] text-slate-400 mt-1">Controls the most expensive model your agents can use. Tier 3 is recommended — it includes high-quality models at reasonable cost. Tier 4 (Opus) is significantly more expensive and should only be enabled for critical decisions.</p>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">Feature Flags</label>
                  <p className="text-[10px] text-slate-400 mb-2">Enable or disable platform features for your organization. Disabled features will be hidden from agents and the dashboard. Only disable features you don&apos;t use — disabling an active feature will stop it from working.</p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {Object.entries(editFlags).map(([key, enabled]) => (
                      <label key={key} className="flex items-center gap-2 text-xs text-slate-700">
                        <input
                          type="checkbox"
                          checked={enabled}
                          onChange={(e) => setEditFlags({ ...editFlags, [key]: e.target.checked })}
                          className="rounded border-slate-300"
                        />
                        {key.replace(/_/g, " ")}
                      </label>
                    ))}
                  </div>
                </div>

                <div className="flex justify-end">
                  <button
                    onClick={saveSettings}
                    disabled={saving}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition"
                  >
                    <Save className="h-3.5 w-3.5" />
                    {saving ? "Saving..." : "Save Settings"}
                  </button>
                </div>
              </div>
            </div>

            {/* Audit Log */}
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-5 py-3">
                <h2 className="text-sm font-semibold text-slate-900">Audit Log</h2>
                <p className="text-xs text-slate-500">Recent security-sensitive operations</p>
              </div>
              {auditLog.length === 0 ? (
                <div className="p-8 text-center text-sm text-slate-500">No audit events yet</div>
              ) : (
                <div className="divide-y divide-slate-100">
                  {auditLog.map((entry) => (
                    <div key={entry.id} className="px-5 py-3 flex items-center justify-between">
                      <div>
                        <span className="text-xs font-medium text-slate-800">{entry.action}</span>
                        {entry.resource_type && (
                          <span className="ml-2 text-[10px] text-slate-400">{entry.resource_type}</span>
                        )}
                        {entry.details && Object.keys(entry.details).length > 0 && (
                          <p className="text-[10px] text-slate-400 mt-0.5">
                            {JSON.stringify(entry.details)}
                          </p>
                        )}
                      </div>
                      <span className="text-[10px] text-slate-400 tabular-nums whitespace-nowrap">
                        {new Date(entry.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="text-center text-sm text-slate-500 py-12">Failed to load settings</div>
        )}
      </div>
    </DashboardPageLayout>
  );
}
