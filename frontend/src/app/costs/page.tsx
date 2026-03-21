"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import { DollarSign, TrendingUp, AlertTriangle, Zap, BarChart3 } from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
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
  const [showAllModels, setShowAllModels] = useState(false);
  const [loading, setLoading] = useState(true);

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
  }, []);

  useEffect(() => {
    if (isSignedIn) loadData();
  }, [isSignedIn, loadData]);

  const usagePct = usage ? ((usage.total_usage / usage.total_credits) * 100) : 0;
  const totalSessionCost = sessions.reduce((sum, s) => sum + s.estimatedCost, 0);

  return (
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
                    <th className="px-4 py-2">Channel</th>
                    <th className="px-4 py-2">Agent</th>
                    <th className="px-4 py-2">Model</th>
                    <th className="px-4 py-2 text-right">Input</th>
                    <th className="px-4 py-2 text-right">Output</th>
                    <th className="px-4 py-2 text-right">Total</th>
                    <th className="px-4 py-2 text-right">Est. Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.map((s, i) => (
                    <tr key={i} className="border-b border-slate-50 hover:bg-slate-50">
                      <td className="px-4 py-2 font-medium text-slate-900">{s.channel}</td>
                      <td className="px-4 py-2 text-slate-600">{s.agent}</td>
                      <td className="px-4 py-2">
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-mono text-slate-600">
                          {s.model}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-xs text-slate-500">
                        {s.inputTokens.toLocaleString()}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-xs text-slate-500">
                        {s.outputTokens.toLocaleString()}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-xs text-slate-700">
                        {s.totalTokens.toLocaleString()}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-xs font-semibold text-slate-900">
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
  );
}
