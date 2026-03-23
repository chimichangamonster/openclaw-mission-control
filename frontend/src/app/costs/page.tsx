"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useRef, useState } from "react";
import { DollarSign, TrendingUp, AlertTriangle, Zap, BarChart3, RefreshCw, Calendar, Settings, X, Save } from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { FeatureGate } from "@/components/molecules/FeatureGate";
import { customFetch } from "@/api/mutator";

interface UsageData {
  total_credits: number;
  total_usage: number;
  remaining: number;
  limit: number;
  usage_daily: number;
  usage_weekly: number;
  usage_monthly: number;
  limit_reset: string;
  is_free_tier: boolean;
}

interface SessionData {
  channel: string;
  agent: string;
  model: string;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  estimatedCost: number;
}

interface ModelInfo {
  id: string;
  name: string;
  prompt_per_m: number;
  completion_per_m: number;
  context_length: number | null;
  configured: boolean;
  agents: string[];
  tier: string;
}

interface ModelUsage {
  model: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost: number;
  session_count: number;
  agents: string[];
  tier: string;
}

interface ActivityModelEntry {
  model: string;
  cost: number;
  requests: number;
  prompt_tokens: number;
  completion_tokens: number;
  tier: string;
}

interface ActivityPeriod {
  period: string;
  total_cost: number;
  models: ActivityModelEntry[];
}

interface ActivityData {
  period_type: string;
  periods: ActivityPeriod[];
  model_totals: ActivityModelEntry[];
  grand_total: number;
}

// Fallback pricing for cost estimation if live data not loaded yet
const FALLBACK_PRICING: Record<string, { prompt: number; completion: number }> = {
  "claude-sonnet-4": { prompt: 3.0, completion: 15.0 },
  "deepseek-v3.2": { prompt: 0.26, completion: 0.38 },
  "grok-4": { prompt: 3.0, completion: 15.0 },
  "gemini-2.5-flash": { prompt: 0.3, completion: 2.5 },
  "gpt-5-nano": { prompt: 0.05, completion: 0.4 },
};

function estimateCost(model: string, inputTokens: number, outputTokens: number, liveModels: ModelInfo[]): number {
  const shortModel = model.split("/").pop() || model;
  // Try live pricing first
  const live = liveModels.find((m) => m.id.endsWith(shortModel) || m.name.toLowerCase().includes(shortModel.toLowerCase()));
  if (live) return (inputTokens / 1_000_000) * live.prompt_per_m + (outputTokens / 1_000_000) * live.completion_per_m;
  // Fallback
  const fb = FALLBACK_PRICING[shortModel];
  if (fb) return (inputTokens / 1_000_000) * fb.prompt + (outputTokens / 1_000_000) * fb.completion;
  return 0;
}

export default function CostsPage() {
  const { isSignedIn } = useAuth();
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [sessions, setSessions] = useState<SessionData[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelUsage, setModelUsage] = useState<ModelUsage[]>([]);
  const [showAllModels, setShowAllModels] = useState(false);
  const [loading, setLoading] = useState(true);
  const [liveRefreshing, setLiveRefreshing] = useState(false);
  const [activity, setActivity] = useState<ActivityData | null>(null);
  const [activityPeriod, setActivityPeriod] = useState<"daily" | "weekly" | "monthly">("daily");
  const [activityLoading, setActivityLoading] = useState(false);
  const [budget, setBudget] = useState<any>(null);
  const [editingBudget, setEditingBudget] = useState(false);
  const [budgetForm, setBudgetForm] = useState({ monthly_budget: 25, alert_thresholds: "50, 80, 95", agent_daily_limits: "{}", default_agent_daily_limit: 2.0, throttle_to_tier1_on_exceed: true, alerts_enabled: true });
  const [savingBudget, setSavingBudget] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadActivity = useCallback(async (period: string) => {
    try {
      setActivityLoading(true);
      const raw: any = await customFetch(`/api/v1/cost-tracker/activity?period=${period}`, { method: "GET" }).catch(() => null);
      const data = raw?.data ?? raw;
      if (data?.periods) {
        setActivity(data as ActivityData);
      }
    } catch {
      // ignore
    } finally {
      setActivityLoading(false);
    }
  }, []);

  const loadModelUsage = useCallback(async () => {
    try {
      const raw: any = await customFetch("/api/v1/cost-tracker/usage-by-model", { method: "GET" }).catch(() => null);
      const data = raw?.data ?? raw;
      if (data?.models) {
        setModelUsage(data.models as ModelUsage[]);
      }
    } catch {
      // ignore
    }
  }, []);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);

      // Fetch OpenRouter usage
      const usageRaw: any = await customFetch("/api/v1/cost-tracker/usage", { method: "GET" });
      const usageResult = usageRaw?.data ?? usageRaw;
      if (usageResult && usageResult.total_credits !== undefined) {
        setUsage(usageResult as UsageData);
      }

      // Fetch live model pricing
      const modelsRaw: any = await customFetch("/api/v1/cost-tracker/models?filter=configured", { method: "GET" }).catch(() => null);
      const modelsData = modelsRaw?.data ?? modelsRaw;
      if (modelsData?.models) setModels(modelsData.models as ModelInfo[]);

      // Fetch budget status
      const budgetRaw: any = await customFetch("/api/v1/cost-tracker/budget", { method: "GET" }).catch(() => null);
      const budgetData = budgetRaw?.data ?? budgetRaw;
      if (budgetData?.config) setBudget(budgetData);

      // Fetch per-model usage + historical activity
      await Promise.all([loadModelUsage(), loadActivity(activityPeriod)]);

      // Fetch gateway sessions for per-agent breakdown
      const boardId = "fc95c061-3c32-4c82-a87d-9e21225e59fd";
      const sessionsRaw: any = await customFetch(`/api/v1/gateways/status?board_id=${boardId}`, { method: "GET" });
      const data = sessionsRaw?.data ?? sessionsRaw;
      if (data) {
        const sessionList: SessionData[] = (data.sessions || [])
          .filter((s: Record<string, unknown>) => {
            const key = (s.key as string) || "";
            return key.includes("discord") || key.includes("the-claw") || key.includes("market-scout") || key.includes("sports-analyst") || key.includes("stock-analyst");
          })
          .map((s: Record<string, unknown>) => {
            const key = (s.key as string) || "";
            const model = ((s.model as string) || "").split("/").pop() || "unknown";
            const agent = key.split(":")[1] || "unknown";
            const channel = (s.groupChannel as string) || (s.displayName as string) || "direct";
            const inputTokens = (s.inputTokens as number) || 0;
            const outputTokens = (s.outputTokens as number) || 0;
            return {
              channel,
              agent,
              model,
              inputTokens,
              outputTokens,
              totalTokens: (s.totalTokens as number) || 0,
              estimatedCost: estimateCost(model, inputTokens, outputTokens, []),
            };
          })
          .sort((a: SessionData, b: SessionData) => b.estimatedCost - a.estimatedCost);
        setSessions(sessionList);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [loadModelUsage, loadActivity, activityPeriod]);

  useEffect(() => {
    if (isSignedIn) loadData();
  }, [isSignedIn, loadData]);

  // Live refresh: poll per-model usage every 30s
  useEffect(() => {
    if (!isSignedIn) return;
    intervalRef.current = setInterval(async () => {
      setLiveRefreshing(true);
      await loadModelUsage();
      setLiveRefreshing(false);
    }, 30_000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [isSignedIn, loadModelUsage]);

  const usagePct = usage ? ((usage.total_usage / usage.total_credits) * 100) : 0;
  const totalSessionCost = sessions.reduce((sum, s) => sum + s.estimatedCost, 0);

  return (
    <FeatureGate flag="cost_tracker" label="Cost & Usage">
    <DashboardPageLayout
      signedOut={{ message: "Sign in to view costs.", forceRedirectUrl: "/costs", signUpForceRedirectUrl: "/costs" }}
      title="Cost & Usage"
      description="OpenRouter spending, per-agent token usage, and budget tracking."
    >
      {loading ? (
        <p className="py-8 text-center text-sm text-slate-500">Loading cost data...</p>
      ) : (
        <div className="space-y-6">
          {/* Budget Overview Cards */}
          {usage && (
            <div className="grid gap-4 md:grid-cols-4">
              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center gap-2 text-sm text-slate-500">
                  <DollarSign className="h-4 w-4" />
                  Total Spent
                </div>
                <p className="mt-1 text-2xl font-bold text-slate-900">${usage.total_usage.toFixed(2)}</p>
                <p className="mt-1 text-xs text-slate-400">of ${usage.total_credits.toFixed(0)} credits</p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center gap-2 text-sm text-slate-500">
                  <TrendingUp className="h-4 w-4" />
                  This Month
                </div>
                <p className="mt-1 text-2xl font-bold text-slate-900">${usage.usage_monthly.toFixed(2)}</p>
                <p className="mt-1 text-xs text-slate-400">${usage.usage_daily.toFixed(2)}/day avg</p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center gap-2 text-sm text-slate-500">
                  <Zap className="h-4 w-4" />
                  This Week
                </div>
                <p className="mt-1 text-2xl font-bold text-slate-900">${usage.usage_weekly.toFixed(2)}</p>
                <p className="mt-1 text-xs text-slate-400">${(usage.usage_weekly / 7).toFixed(2)}/day</p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center gap-2 text-sm text-slate-500">
                  {usagePct > 80 ? <AlertTriangle className="h-4 w-4 text-amber-500" /> : <BarChart3 className="h-4 w-4" />}
                  Budget Remaining
                </div>
                <p className={`mt-1 text-2xl font-bold ${usagePct > 80 ? "text-amber-600" : "text-emerald-600"}`}>
                  ${usage.remaining.toFixed(2)}
                </p>
                <div className="mt-2 h-2 w-full rounded-full bg-slate-100">
                  <div
                    className={`h-2 rounded-full transition-all ${usagePct > 80 ? "bg-amber-500" : usagePct > 50 ? "bg-blue-500" : "bg-emerald-500"}`}
                    style={{ width: `${Math.min(usagePct, 100)}%` }}
                  />
                </div>
                <p className="mt-1 text-xs text-slate-400">{usagePct.toFixed(0)}% used • resets {usage.limit_reset}</p>
              </div>
            </div>
          )}

          {/* Budget Controls & Per-Agent Spend */}
          {budget && (
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-4 py-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">Budget Controls</h3>
                  <p className="text-xs text-slate-500">
                    Monthly budget: ${budget.config.monthly_budget.toFixed(2)} • Default daily limit: ${budget.config.default_agent_daily_limit?.toFixed(2) ?? "2.00"}/agent • Alerts at {budget.config.alert_thresholds.join("%, ")}%
                  </p>
                </div>
                <button
                  onClick={() => {
                    if (!editingBudget) {
                      setBudgetForm({
                        monthly_budget: budget.config.monthly_budget,
                        alert_thresholds: budget.config.alert_thresholds.join(", "),
                        agent_daily_limits: JSON.stringify(budget.config.agent_daily_limits, null, 2),
                        default_agent_daily_limit: budget.config.default_agent_daily_limit ?? 2.0,
                        throttle_to_tier1_on_exceed: budget.config.throttle_to_tier1_on_exceed,
                        alerts_enabled: budget.config.alerts_enabled,
                      });
                    }
                    setEditingBudget(!editingBudget);
                  }}
                  className="rounded-lg p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition"
                >
                  {editingBudget ? <X className="h-4 w-4" /> : <Settings className="h-4 w-4" />}
                </button>
              </div>

              {/* Budget Editor */}
              {editingBudget && (
                <div className="border-b border-slate-100 bg-slate-50/50 p-4 space-y-3">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Monthly Budget ($)</label>
                      <input
                        type="number"
                        step="5"
                        min="0"
                        value={budgetForm.monthly_budget}
                        onChange={(e) => setBudgetForm({ ...budgetForm, monthly_budget: parseFloat(e.target.value) || 0 })}
                        className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-800 focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Default Daily Limit ($)</label>
                      <input
                        type="number"
                        step="0.5"
                        min="0"
                        value={budgetForm.default_agent_daily_limit}
                        onChange={(e) => setBudgetForm({ ...budgetForm, default_agent_daily_limit: parseFloat(e.target.value) || 0 })}
                        className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-800 focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
                      />
                      <p className="text-[10px] text-slate-400 mt-0.5">Applies to all agents without a specific override</p>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600 mb-1">Alert Thresholds (%)</label>
                      <input
                        type="text"
                        value={budgetForm.alert_thresholds}
                        onChange={(e) => setBudgetForm({ ...budgetForm, alert_thresholds: e.target.value })}
                        placeholder="50, 80, 95"
                        className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-800 focus:border-blue-400 focus:ring-1 focus:ring-blue-400 outline-none"
                      />
                    </div>
                  </div>
                  {/* Agent-specific overrides hidden — managed via API for power users */}
                  <div className="flex items-center gap-6">
                    <label className="flex items-center gap-2 text-xs text-slate-600">
                      <input
                        type="checkbox"
                        checked={budgetForm.alerts_enabled}
                        onChange={(e) => setBudgetForm({ ...budgetForm, alerts_enabled: e.target.checked })}
                        className="rounded border-slate-300"
                      />
                      Discord Alerts
                    </label>
                    <label className="flex items-center gap-2 text-xs text-slate-600">
                      <input
                        type="checkbox"
                        checked={budgetForm.throttle_to_tier1_on_exceed}
                        onChange={(e) => setBudgetForm({ ...budgetForm, throttle_to_tier1_on_exceed: e.target.checked })}
                        className="rounded border-slate-300"
                      />
                      Throttle to Tier 1 on Exceed
                    </label>
                  </div>
                  <div className="flex justify-end">
                    <button
                      disabled={savingBudget}
                      onClick={async () => {
                        try {
                          setSavingBudget(true);
                          const thresholds = budgetForm.alert_thresholds.split(",").map((s: string) => parseInt(s.trim())).filter((n: number) => !isNaN(n));
                          let agentLimits: Record<string, number>;
                          try { agentLimits = JSON.parse(budgetForm.agent_daily_limits); } catch { agentLimits = budget.config.agent_daily_limits; }
                          await customFetch("/api/v1/cost-tracker/budget", {
                            method: "PUT",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                              monthly_budget: budgetForm.monthly_budget,
                              alert_thresholds: thresholds,
                              agent_daily_limits: agentLimits,
                              default_agent_daily_limit: budgetForm.default_agent_daily_limit,
                              throttle_to_tier1_on_exceed: budgetForm.throttle_to_tier1_on_exceed,
                              alerts_enabled: budgetForm.alerts_enabled,
                            }),
                          });
                          setEditingBudget(false);
                          // Reload budget data
                          const budgetRaw: any = await customFetch("/api/v1/cost-tracker/budget", { method: "GET" }).catch(() => null);
                          const budgetData = budgetRaw?.data ?? budgetRaw;
                          if (budgetData?.config) setBudget(budgetData);
                        } catch {
                          // ignore
                        } finally {
                          setSavingBudget(false);
                        }
                      }}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition"
                    >
                      <Save className="h-3.5 w-3.5" />
                      {savingBudget ? "Saving..." : "Save"}
                    </button>
                  </div>
                </div>
              )}

              <div className="p-4 space-y-4">
                {/* Monthly progress */}
                <div>
                  <div className="flex items-center justify-between text-sm mb-1.5">
                    <span className="text-slate-600">
                      Monthly Spend: <span className="font-semibold text-slate-900">${budget.status.monthly_total.toFixed(2)}</span> / ${budget.status.monthly_budget.toFixed(2)}
                    </span>
                    <span className={`text-xs font-medium ${
                      budget.status.monthly_pct > 80 ? "text-red-600" :
                      budget.status.monthly_pct > 50 ? "text-amber-600" : "text-emerald-600"
                    }`}>
                      {budget.status.monthly_pct.toFixed(0)}%
                    </span>
                  </div>
                  <div className="h-2.5 w-full rounded-full bg-slate-100">
                    <div
                      className={`h-2.5 rounded-full transition-all ${
                        budget.status.monthly_pct > 80 ? "bg-red-500" :
                        budget.status.monthly_pct > 50 ? "bg-amber-500" : "bg-emerald-500"
                      }`}
                      style={{ width: `${Math.min(budget.status.monthly_pct, 100)}%` }}
                    />
                  </div>
                  <div className="flex justify-between mt-1 text-[10px] text-slate-400">
                    <span>Remaining: ${budget.status.remaining.toFixed(2)}</span>
                    <span>Projected: ${budget.status.projected_month_end.toFixed(2)}</span>
                    <span>Avg: ${budget.status.daily_avg.toFixed(2)}/day</span>
                  </div>
                </div>

                {/* Per-agent daily spend */}
                {budget.agent_today.length > 0 && (
                  <div>
                    <h4 className="text-xs font-semibold text-slate-700 mb-2">Agent Spend Today</h4>
                    <div className="space-y-2">
                      {budget.agent_today.map((a: any) => {
                        const limit = a.limit || 0;
                        const pct = limit > 0 ? (a.cost / limit) * 100 : 0;
                        return (
                          <div key={a.agent} className="flex items-center gap-3">
                            <span className="text-xs font-medium text-slate-700 w-28 truncate">{a.agent}</span>
                            <div className="flex-1">
                              <div className="h-2 w-full rounded-full bg-slate-100">
                                <div
                                  className={`h-2 rounded-full transition-all ${
                                    a.exceeded ? "bg-red-500" :
                                    pct > 80 ? "bg-amber-500" : "bg-emerald-500"
                                  }`}
                                  style={{ width: `${Math.min(pct, 100)}%` }}
                                />
                              </div>
                            </div>
                            <span className={`text-xs font-mono w-24 text-right ${a.exceeded ? "text-red-600 font-semibold" : "text-slate-500"}`}>
                              ${a.cost.toFixed(4)}{limit > 0 ? ` / $${limit.toFixed(2)}` : ""}
                            </span>
                            {a.exceeded && (
                              <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-700">EXCEEDED</span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Spending by Model — Leaderboard */}
          {modelUsage.length > 0 && (() => {
            const hasHistory = activity && activity.model_totals.length > 0 && activity.grand_total > 0;
            // Merge live session data with 30-day historical totals (if available)
            const merged = new Map<string, { model: string; live_cost: number; hist_cost: number; live_tokens: number; hist_tokens: number; hist_requests: number; sessions: number; agents: string[]; tier: string }>();
            for (const m of modelUsage) {
              merged.set(m.model, { model: m.model, live_cost: m.estimated_cost, hist_cost: 0, live_tokens: m.total_tokens, hist_tokens: 0, hist_requests: 0, sessions: m.session_count, agents: m.agents, tier: m.tier });
            }
            if (hasHistory) {
              for (const mt of activity!.model_totals) {
                const existing = merged.get(mt.model);
                if (existing) {
                  existing.hist_cost = mt.cost;
                  existing.hist_tokens = mt.prompt_tokens + mt.completion_tokens;
                  existing.hist_requests = mt.requests;
                } else {
                  merged.set(mt.model, { model: mt.model, live_cost: 0, hist_cost: mt.cost, live_tokens: 0, hist_tokens: mt.prompt_tokens + mt.completion_tokens, hist_requests: mt.requests, sessions: 0, agents: [], tier: mt.tier });
                }
              }
            }
            const leaderboard = [...merged.values()].sort((a, b) => {
              const aCost = hasHistory ? a.hist_cost + a.live_cost : a.live_cost;
              const bCost = hasHistory ? b.hist_cost + b.live_cost : b.live_cost;
              return bCost - aCost;
            });
            const maxCost = leaderboard.length > 0 ? (hasHistory ? leaderboard[0].hist_cost + leaderboard[0].live_cost : leaderboard[0].live_cost) : 1;

            return (
              <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
                <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-900">Model Spending Leaderboard</h3>
                    <p className="text-xs text-slate-500">
                      {hasHistory ? "30-day history + live session data" : "Live session token usage (estimated cost)"} • {leaderboard.length} models
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {liveRefreshing && <RefreshCw className="h-3 w-3 animate-spin text-slate-400" />}
                    <span className="rounded bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-700">
                      LIVE • 30s
                    </span>
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-100 text-left text-xs text-slate-500">
                        <th className="px-2 sm:px-4 py-2 w-8">#</th>
                        <th className="px-2 sm:px-4 py-2">Model</th>
                        <th className="hidden sm:table-cell px-2 sm:px-4 py-2">Tier</th>
                        {hasHistory && <th className="hidden md:table-cell px-2 sm:px-4 py-2 text-right">30d Cost</th>}
                        <th className="px-2 sm:px-4 py-2 text-right">{hasHistory ? "Cost" : "Est. Cost"}</th>
                        <th className="hidden lg:table-cell px-2 sm:px-4 py-2 text-right">Tokens</th>
                        <th className="hidden lg:table-cell px-2 sm:px-4 py-2 text-right">{hasHistory ? "Requests" : "Sessions"}</th>
                        <th className="hidden md:table-cell px-2 sm:px-4 py-2">Agents</th>
                        <th className="hidden sm:table-cell px-2 sm:px-4 py-2 w-[20%]"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {leaderboard.map((m, i) => {
                        const totalCost = hasHistory ? m.hist_cost + m.live_cost : m.live_cost;
                        const pct = maxCost > 0 ? (totalCost / maxCost) * 100 : 0;
                        const tierColor = m.tier.includes("4") ? "bg-red-500" :
                          m.tier.includes("3") ? "bg-purple-500" :
                          m.tier.includes("2") ? "bg-blue-500" : "bg-emerald-500";
                        const isTop3 = i < 3;
                        return (
                          <tr key={m.model} className={`border-b border-slate-50 hover:bg-slate-50 ${isTop3 ? "bg-slate-25" : ""}`}>
                            <td className="px-2 sm:px-4 py-2.5">
                              <span className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
                                i === 0 ? "bg-amber-100 text-amber-700" :
                                i === 1 ? "bg-slate-200 text-slate-600" :
                                i === 2 ? "bg-orange-100 text-orange-700" :
                                "text-slate-400"
                              }`}>
                                {i + 1}
                              </span>
                            </td>
                            <td className="px-2 sm:px-4 py-2.5">
                              <span className="font-mono font-medium text-slate-800 text-xs sm:text-sm">{m.model}</span>
                              <span className={`sm:hidden ml-1.5 rounded px-1 py-0.5 text-[9px] font-medium ${
                                m.tier.includes("4") ? "bg-red-100 text-red-700" :
                                m.tier.includes("3") ? "bg-purple-100 text-purple-700" :
                                m.tier.includes("2") ? "bg-blue-100 text-blue-700" :
                                "bg-emerald-100 text-emerald-700"
                              }`}>
                                {m.tier.replace("Tier ", "T").replace(" — ", " ").split(" ")[0]}
                              </span>
                            </td>
                            <td className="hidden sm:table-cell px-2 sm:px-4 py-2.5">
                              <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                                m.tier.includes("4") ? "bg-red-100 text-red-700" :
                                m.tier.includes("3") ? "bg-purple-100 text-purple-700" :
                                m.tier.includes("2") ? "bg-blue-100 text-blue-700" :
                                "bg-emerald-100 text-emerald-700"
                              }`}>
                                {m.tier.replace("Tier ", "T").replace(" — ", " ")}
                              </span>
                            </td>
                            {hasHistory && (
                              <td className="hidden md:table-cell px-2 sm:px-4 py-2.5 text-right font-mono text-xs font-semibold text-slate-900">
                                ${m.hist_cost.toFixed(4)}
                              </td>
                            )}
                            <td className={`px-2 sm:px-4 py-2.5 text-right font-mono text-xs ${hasHistory ? "text-slate-500" : "font-semibold text-slate-900"}`}>
                              {m.live_cost > 0 ? `$${m.live_cost.toFixed(4)}` : "—"}
                            </td>
                            <td className="hidden lg:table-cell px-2 sm:px-4 py-2.5 text-right font-mono text-xs text-slate-500">
                              {(m.hist_tokens + m.live_tokens).toLocaleString()}
                            </td>
                            <td className="hidden lg:table-cell px-2 sm:px-4 py-2.5 text-right font-mono text-xs text-slate-500">
                              {hasHistory && m.hist_requests > 0 ? m.hist_requests.toLocaleString() : m.sessions > 0 ? m.sessions : "—"}
                            </td>
                            <td className="hidden md:table-cell px-2 sm:px-4 py-2.5">
                              {m.agents.length > 0 ? (
                                <div className="flex flex-wrap gap-1">
                                  {m.agents.map((a) => (
                                    <span key={a} className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">{a}</span>
                                  ))}
                                </div>
                              ) : null}
                            </td>
                            <td className="hidden sm:table-cell px-2 sm:px-4 py-2.5">
                              <div className="h-2 w-full rounded-full bg-slate-100">
                                <div className={`h-2 rounded-full transition-all ${tierColor}`} style={{ width: `${Math.max(pct, 2)}%` }} />
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })()}

          {/* Historical Spending by Model — only shows if activity API returns data */}
          {activity && activity.periods.length > 0 && activity.grand_total > 0 && <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
              <div>
                <h3 className="text-sm font-semibold text-slate-900">
                  <Calendar className="mr-1.5 inline h-4 w-4" />
                  Spending History by Model
                </h3>
                <p className="text-xs text-slate-500">
                  Last 30 days from OpenRouter{activity ? ` • $${activity.grand_total.toFixed(4)} total` : ""}
                </p>
              </div>
              <div className="flex rounded-lg border border-slate-200 overflow-hidden">
                {(["daily", "weekly", "monthly"] as const).map((p) => (
                  <button
                    key={p}
                    onClick={() => {
                      setActivityPeriod(p);
                      loadActivity(p);
                    }}
                    className={`px-3 py-1.5 text-xs font-medium transition ${
                      activityPeriod === p
                        ? "bg-slate-900 text-white"
                        : "bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    {p.charAt(0).toUpperCase() + p.slice(1)}
                  </button>
                ))}
              </div>
            </div>
            {activityLoading ? (
              <p className="py-6 text-center text-sm text-slate-400">Loading history...</p>
            ) : activity && activity.periods.length > 0 ? (
              <div className="divide-y divide-slate-100">
                {/* Model totals summary row */}
                <div className="px-4 py-3 bg-slate-50">
                  <div className="flex flex-wrap gap-3">
                    {activity.model_totals.map((mt) => {
                      const pct = activity.grand_total > 0 ? (mt.cost / activity.grand_total) * 100 : 0;
                      return (
                        <div key={mt.model} className="flex items-center gap-1.5 text-xs">
                          <span className={`inline-block h-2 w-2 rounded-full ${
                            mt.tier.includes("4") ? "bg-red-500" :
                            mt.tier.includes("3") ? "bg-purple-500" :
                            mt.tier.includes("2") ? "bg-blue-500" : "bg-emerald-500"
                          }`} />
                          <span className="font-mono font-medium text-slate-700">{mt.model}</span>
                          <span className="text-slate-500">${mt.cost.toFixed(4)}</span>
                          <span className="text-slate-400">({pct.toFixed(0)}%)</span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Period rows */}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-100 text-left text-xs text-slate-500">
                        <th className="px-4 py-2">Period</th>
                        <th className="px-4 py-2 text-right">Total Cost</th>
                        <th className="px-4 py-2">Model Breakdown</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activity.periods.map((p) => (
                        <tr key={p.period} className="border-b border-slate-50 hover:bg-slate-50">
                          <td className="px-4 py-2 font-mono text-xs font-medium text-slate-700 whitespace-nowrap">
                            {p.period}
                          </td>
                          <td className="px-4 py-2 text-right font-mono text-xs font-semibold text-slate-900">
                            ${p.total_cost.toFixed(4)}
                          </td>
                          <td className="px-4 py-2">
                            <div className="flex flex-wrap gap-2">
                              {p.models.map((pm) => (
                                <span
                                  key={pm.model}
                                  className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-mono ${
                                    pm.tier.includes("4") ? "bg-red-50 text-red-700" :
                                    pm.tier.includes("3") ? "bg-purple-50 text-purple-700" :
                                    pm.tier.includes("2") ? "bg-blue-50 text-blue-700" :
                                    "bg-emerald-50 text-emerald-700"
                                  }`}
                                >
                                  {pm.model}: ${pm.cost.toFixed(4)}
                                  <span className="text-slate-400">({pm.requests} req)</span>
                                </span>
                              ))}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <p className="py-6 text-center text-sm text-slate-400">No activity data available</p>
            )}
          </div>}

          {/* Per-Agent Cost Breakdown */}
          <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-100 px-4 py-3">
              <h3 className="text-sm font-semibold text-slate-900">Agent Token Usage (This Session)</h3>
              <p className="text-xs text-slate-500">Estimated cost based on model pricing • Total: ${totalSessionCost.toFixed(4)}</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-left text-xs text-slate-500">
                    <th className="hidden sm:table-cell px-2 sm:px-4 py-2">Channel</th>
                    <th className="px-2 sm:px-4 py-2">Agent</th>
                    <th className="px-2 sm:px-4 py-2">Model</th>
                    <th className="hidden md:table-cell px-2 sm:px-4 py-2 text-right">Input</th>
                    <th className="hidden md:table-cell px-2 sm:px-4 py-2 text-right">Output</th>
                    <th className="hidden sm:table-cell px-2 sm:px-4 py-2 text-right">Total</th>
                    <th className="px-2 sm:px-4 py-2 text-right">Est. Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.map((s, i) => (
                    <tr key={i} className="border-b border-slate-50 hover:bg-slate-50">
                      <td className="hidden sm:table-cell px-2 sm:px-4 py-2 font-medium text-slate-900">{s.channel}</td>
                      <td className="px-2 sm:px-4 py-2 text-slate-600">{s.agent}</td>
                      <td className="px-2 sm:px-4 py-2">
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-mono text-slate-600">
                          {s.model}
                        </span>
                      </td>
                      <td className="hidden md:table-cell px-2 sm:px-4 py-2 text-right font-mono text-xs text-slate-500">
                        {s.inputTokens.toLocaleString()}
                      </td>
                      <td className="hidden md:table-cell px-2 sm:px-4 py-2 text-right font-mono text-xs text-slate-500">
                        {s.outputTokens.toLocaleString()}
                      </td>
                      <td className="hidden sm:table-cell px-2 sm:px-4 py-2 text-right font-mono text-xs text-slate-700">
                        {s.totalTokens.toLocaleString()}
                      </td>
                      <td className="px-2 sm:px-4 py-2 text-right font-mono text-xs font-semibold text-slate-900">
                        ${s.estimatedCost.toFixed(4)}
                      </td>
                    </tr>
                  ))}
                  {sessions.length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                        No active sessions
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Live Model Pricing */}
          <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
              <div>
                <h3 className="text-sm font-semibold text-slate-900">Model Pricing (per 1M tokens)</h3>
                <p className="text-xs text-slate-500">Live from OpenRouter {models.length > 0 ? `• ${models.length} models` : ""}</p>
              </div>
              <button
                onClick={async () => {
                  const next = !showAllModels;
                  setShowAllModels(next);
                  if (next && models.every((m) => m.configured)) {
                    const allRaw: any = await customFetch("/api/v1/cost-tracker/models?filter=all", { method: "GET" }).catch(() => null);
                    const allData = allRaw?.data ?? allRaw;
                    if (allData?.models) setModels(allData.models as ModelInfo[]);
                  }
                }}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 transition"
              >
                {showAllModels ? "Show Configured Only" : "Show All Models"}
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-left text-xs text-slate-500">
                    <th className="px-4 py-2">Model</th>
                    <th className="px-4 py-2 text-right">Prompt</th>
                    <th className="px-4 py-2 text-right">Completion</th>
                    <th className="px-4 py-2">Tier</th>
                    <th className="px-4 py-2">Used By</th>
                  </tr>
                </thead>
                <tbody>
                  {(showAllModels ? models : models.filter((m) => m.configured)).map((m) => (
                    <tr key={m.id} className={`border-b border-slate-50 hover:bg-slate-50 ${m.configured ? "" : "opacity-60"}`}>
                      <td className="px-4 py-2">
                        <div className="font-mono text-xs text-slate-700">{m.id.split("/").slice(-1)[0]}</div>
                        {m.name !== m.id && <div className="text-[10px] text-slate-400 truncate max-w-[200px]">{m.name}</div>}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-xs text-slate-600">${m.prompt_per_m.toFixed(2)}</td>
                      <td className="px-4 py-2 text-right font-mono text-xs text-slate-600">${m.completion_per_m.toFixed(2)}</td>
                      <td className="px-4 py-2">
                        <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                          m.tier.includes("4") ? "bg-red-100 text-red-700" :
                          m.tier.includes("3") ? "bg-purple-100 text-purple-700" :
                          m.tier.includes("2") ? "bg-blue-100 text-blue-700" :
                          "bg-emerald-100 text-emerald-700"
                        }`}>
                          {m.tier.replace("Tier ", "T").replace(" — ", " ")}
                        </span>
                      </td>
                      <td className="px-4 py-2">
                        {m.agents.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {m.agents.map((a) => (
                              <span key={a} className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">{a}</span>
                            ))}
                          </div>
                        ) : m.configured ? (
                          <span className="text-[10px] text-slate-400">configured</span>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                  {models.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-8 text-center text-slate-400">Loading pricing data...</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </DashboardPageLayout>
    </FeatureGate>
  );
}
