"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import { Key, Shield, Save, Trash2, Eye, EyeOff, AlertTriangle } from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { customFetch } from "@/api/mutator";

interface OrgSettings {
  openrouter_api_key: string | null;
  has_openrouter_key: boolean;
  openrouter_management_key: string | null;
  has_management_key: boolean;
  default_model_tier_max: number;
  configured_models: string[];
  feature_flags: Record<string, boolean>;
  agent_defaults: Record<string, unknown>;
  branding: Record<string, unknown>;
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

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [settingsRaw, auditRaw]: any[] = await Promise.all([
        customFetch("/api/v1/organization-settings", { method: "GET" }).catch(() => null),
        customFetch("/api/v1/organization-settings/audit-log?limit=20", { method: "GET" }).catch(() => null),
      ]);
      const sData = settingsRaw?.data ?? settingsRaw;
      if (sData) {
        setSettings(sData as OrgSettings);
        setEditFlags(sData.feature_flags || {});
        setTierMax(sData.default_model_tier_max || 3);
      }
      const aData = auditRaw?.data ?? auditRaw;
      if (aData?.entries) setAuditLog(aData.entries as AuditEntry[]);
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

  if (!isSignedIn) return null;

  return (
    <DashboardPageLayout
      signedOut={{ message: "Sign in to view organization settings.", forceRedirectUrl: "/org-settings", signUpForceRedirectUrl: "/org-settings" }}
      title="Organization Settings"
      description="API keys, feature flags, and audit trail."
    >
      <div className="mx-auto max-w-3xl space-y-6 p-6">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Organization Settings</h1>
          <p className="text-sm text-slate-500">API keys, feature flags, and audit trail</p>
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
