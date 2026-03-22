"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Key, Shield, Save, Trash2, Eye, EyeOff, AlertTriangle,
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

  // Microsoft Graph state
  const [connectingGraph, setConnectingGraph] = useState(false);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [settingsRaw, auditRaw, routingRaw]: any[] = await Promise.all([
        customFetch("/api/v1/organization-settings", { method: "GET" }).catch(() => null),
        customFetch("/api/v1/organization-settings/audit-log?limit=20", { method: "GET" }).catch(() => null),
        customFetch("/api/v1/organization-settings/llm-routing", { method: "GET" }).catch(() => null),
      ]);
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
      }
      const aData = auditRaw?.data ?? auditRaw;
      if (aData?.entries) setAuditLog(aData.entries as AuditEntry[]);
      const rData = routingRaw?.data ?? routingRaw;
      if (rData) setLlmRouting(rData as LLMRouting);
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
    await customFetch("/api/v1/organization-settings/openrouter-key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: newOrKey.trim() }),
    });
    setNewOrKey("");
    await loadData();
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
