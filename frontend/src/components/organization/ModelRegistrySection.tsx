"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, AlertTriangle, Pin, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getModelRegistry,
  refreshModelRegistry,
  getModelPins,
  updateModelPins,
  type ModelEntry,
  type DeprecationWarning,
} from "@/lib/model-registry-api";

const TIER_LABELS: Record<number, { label: string; color: string }> = {
  1: { label: "Nano", color: "bg-slate-100 text-slate-600" },
  2: { label: "Standard", color: "bg-blue-100 text-blue-700" },
  3: { label: "Reasoning", color: "bg-amber-100 text-amber-700" },
  4: { label: "Critical", color: "bg-red-100 text-red-700" },
};

const STATUS_COLORS: Record<string, string> = {
  active: "text-emerald-600",
  deprecated: "text-amber-600",
  removed: "text-red-600",
};

const PIN_KEYS = [
  { key: "primary", label: "Primary Model", description: "Main reasoning model for agents" },
  { key: "budget", label: "Budget Model", description: "Cost-efficient model for routine tasks" },
  { key: "fallback", label: "Fallback Model", description: "Used when primary is unavailable" },
];

interface Props {
  isAdmin: boolean;
}

export function ModelRegistrySection({ isAdmin }: Props) {
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [families, setFamilies] = useState<string[]>([]);
  const [lastRefresh, setLastRefresh] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Pins
  const [pins, setPins] = useState<Record<string, string>>({});
  const [warnings, setWarnings] = useState<DeprecationWarning[]>([]);
  const [savingPins, setSavingPins] = useState(false);
  const [pinsDirty, setPinsDirty] = useState(false);

  // Expand
  const [showRegistry, setShowRegistry] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("active");

  // Toast
  const [toast, setToast] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [regData, pinsData] = await Promise.all([
        getModelRegistry(statusFilter !== "all" ? statusFilter : undefined),
        getModelPins(),
      ]);
      setModels(regData.models);
      setFamilies(regData.families);
      setLastRefresh(regData.last_refresh);
      setPins(pinsData.pins);
      setWarnings(pinsData.warnings);
    } catch {
      // Silently fail — section is optional
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const result = await refreshModelRegistry();
      setToast(`Refreshed: ${result.total_models} models (${result.new_models} new, ${result.deprecated_models} deprecated)`);
      await loadData();
    } catch {
      setToast("Failed to refresh model registry");
    } finally {
      setRefreshing(false);
    }
  };

  const handlePinChange = (key: string, value: string) => {
    setPins((prev) => {
      const next = { ...prev };
      if (value) {
        next[key] = value;
      } else {
        delete next[key];
      }
      return next;
    });
    setPinsDirty(true);
  };

  const handleSavePins = async () => {
    setSavingPins(true);
    try {
      await updateModelPins(pins);
      setToast("Model pins saved");
      setPinsDirty(false);
      // Refresh warnings
      const pinsData = await getModelPins();
      setWarnings(pinsData.warnings);
    } catch (err: any) {
      setToast(err?.message || "Failed to save pins");
    } finally {
      setSavingPins(false);
    }
  };

  const configuredModels = models.filter((m) => m.status === "active");
  const formatPrice = (p: number) => p < 1 ? `$${p.toFixed(2)}` : `$${p.toFixed(1)}`;

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      {/* Toast */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-700 shadow-lg animate-in fade-in slide-in-from-top-2">
          {toast}
        </div>
      )}

      <div className="border-b border-slate-100 px-5 py-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
            <Pin className="h-4 w-4" /> Model Registry & Pinning
          </h2>
          <p className="text-xs text-slate-500">
            Pin specific model versions to prevent unexpected behavior changes.
          </p>
        </div>
        {isAdmin && (
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50 transition"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
        )}
      </div>

      <div className="p-5 space-y-5">
        {loading ? (
          <div className="flex justify-center py-4">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-200 border-t-blue-500" />
          </div>
        ) : (
          <>
            {/* Deprecation warnings */}
            {warnings.length > 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-1.5">
                <div className="flex items-center gap-2 text-xs font-medium text-amber-700">
                  <AlertTriangle className="h-4 w-4" /> Pinned Model Warnings
                </div>
                {warnings.map((w, i) => (
                  <div key={i} className="text-xs text-amber-600">
                    <strong>{w.pin_key}:</strong> {w.pinned_model_id} is <strong>{w.status}</strong>
                    {w.suggested_replacement && (
                      <> — consider switching to <code className="bg-white px-1 py-0.5 rounded text-amber-700">{w.suggested_replacement}</code></>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Model pins */}
            {isAdmin && (
              <div>
                <h3 className="text-xs font-medium text-slate-600 mb-2">Model Version Pins</h3>
                <p className="text-[10px] text-slate-400 mb-3">
                  Pin models to specific versions. When empty, agents use the latest available version.
                  Pins are advisory — OpenRouter resolves the final model.
                </p>
                <div className="space-y-3">
                  {PIN_KEYS.map(({ key, label, description }) => (
                    <div key={key} className="grid grid-cols-3 gap-3 items-start">
                      <div>
                        <div className="text-xs font-medium text-slate-700">{label}</div>
                        <div className="text-[10px] text-slate-400">{description}</div>
                      </div>
                      <select
                        value={pins[key] || ""}
                        onChange={(e) => handlePinChange(key, e.target.value)}
                        className="col-span-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
                      >
                        <option value="">Latest (unpinned)</option>
                        {configuredModels.map((m) => (
                          <option key={m.model_id} value={m.model_id}>
                            {m.name} — {formatPrice(m.prompt_price_per_m)}/M, {(m.context_window / 1000).toFixed(0)}K ctx
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
                {pinsDirty && (
                  <div className="mt-3 flex justify-end">
                    <button
                      onClick={handleSavePins}
                      disabled={savingPins}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition"
                    >
                      {savingPins ? "Saving..." : "Save Pins"}
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Expandable registry browser */}
            <div>
              <button
                onClick={() => setShowRegistry(!showRegistry)}
                className="flex items-center gap-1.5 text-xs font-medium text-slate-600 hover:text-slate-800 transition"
              >
                {showRegistry ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                Browse Model Registry ({models.length} models)
              </button>

              {showRegistry && (
                <div className="mt-3 space-y-2">
                  {/* Status filter */}
                  <div className="flex gap-1.5">
                    {["active", "deprecated", "all"].map((s) => (
                      <button
                        key={s}
                        onClick={() => setStatusFilter(s)}
                        className={cn(
                          "rounded-full px-2.5 py-1 text-xs font-medium transition",
                          statusFilter === s
                            ? "bg-blue-100 text-blue-700"
                            : "bg-slate-100 text-slate-500 hover:bg-slate-200"
                        )}
                      >
                        {s === "all" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}
                      </button>
                    ))}
                  </div>

                  {lastRefresh && (
                    <p className="text-[10px] text-slate-400">
                      Last refreshed: {new Date(lastRefresh).toLocaleString()}
                    </p>
                  )}

                  {/* Model table */}
                  <div className="overflow-x-auto rounded-lg border border-slate-200">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-slate-50 border-b border-slate-200">
                          <th className="text-left px-3 py-2 font-medium text-slate-500">Model</th>
                          <th className="text-left px-3 py-2 font-medium text-slate-500">Provider</th>
                          <th className="text-center px-3 py-2 font-medium text-slate-500">Tier</th>
                          <th className="text-right px-3 py-2 font-medium text-slate-500">Prompt/M</th>
                          <th className="text-right px-3 py-2 font-medium text-slate-500">Context</th>
                          <th className="text-center px-3 py-2 font-medium text-slate-500">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {models.slice(0, 50).map((m) => {
                          const tier = TIER_LABELS[m.tier] || TIER_LABELS[2];
                          return (
                            <tr key={m.model_id} className="hover:bg-slate-50/50">
                              <td className="px-3 py-2">
                                <div className="font-medium text-slate-700">{m.name}</div>
                                <div className="text-[10px] text-slate-400 font-mono">{m.model_id}</div>
                              </td>
                              <td className="px-3 py-2 text-slate-600">{m.provider}</td>
                              <td className="px-3 py-2 text-center">
                                <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium", tier.color)}>
                                  {tier.label}
                                </span>
                              </td>
                              <td className="px-3 py-2 text-right font-mono text-slate-600">
                                {formatPrice(m.prompt_price_per_m)}
                              </td>
                              <td className="px-3 py-2 text-right text-slate-600">
                                {m.context_window > 0 ? `${(m.context_window / 1000).toFixed(0)}K` : "—"}
                              </td>
                              <td className={cn("px-3 py-2 text-center font-medium", STATUS_COLORS[m.status] || "text-slate-400")}>
                                {m.status}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    {models.length > 50 && (
                      <div className="px-3 py-2 text-[10px] text-slate-400 text-center border-t border-slate-200">
                        Showing 50 of {models.length} models
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
