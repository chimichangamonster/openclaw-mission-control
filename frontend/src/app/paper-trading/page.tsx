"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import { BarChart3, TrendingUp, TrendingDown, DollarSign } from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { cn } from "@/lib/utils";
import { customFetch } from "@/api/mutator";

interface Portfolio {
  id: string;
  name: string;
  starting_balance: number;
  cash_balance: number;
  positions_value?: number;
  total_value?: number;
  total_return_pct?: number;
  unrealized_pnl?: number;
  open_positions?: number;
  created_at: string;
}

interface Position {
  id: string;
  symbol: string;
  asset_type: string;
  side: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  pnl_pct: number;
  status: string;
  entry_date: string;
}

interface Trade {
  id: string;
  symbol: string;
  asset_type: string;
  trade_type: string;
  quantity: number;
  price: number;
  total: number;
  fees: number;
  proposed_by: string;
  notes: string;
  executed_at: string;
}

interface Summary {
  name: string;
  starting_balance: number;
  cash_balance: number;
  total_value: number;
  total_return_pct: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_pct: number;
  best_trade: { symbol: string; pnl: number } | null;
  worst_trade: { symbol: string; pnl: number } | null;
}

export default function PaperTradingPage() {
  const { isSignedIn } = useAuth();
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [tab, setTab] = useState<"positions" | "trades" | "summary">("positions");
  const [loading, setLoading] = useState(true);

  const loadPortfolios = useCallback(async () => {
    try {
      const res: any = await customFetch("/api/v1/paper-trading/portfolios", { method: "GET" });
      const data = Array.isArray(res?.data) ? res.data : Array.isArray(res) ? res : [];
      setPortfolios(data);
      if (data.length > 0 && !selectedId) setSelectedId(data[0].id);
    } catch {
      setPortfolios([]);
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  const loadDetails = useCallback(async (pid: string) => {
    try {
      const [detailRes, posRes, tradeRes, summaryRes]: any[] = await Promise.all([
        customFetch(`/api/v1/paper-trading/portfolios/${pid}`, { method: "GET" }),
        customFetch(`/api/v1/paper-trading/portfolios/${pid}/positions?status=all`, { method: "GET" }),
        customFetch(`/api/v1/paper-trading/portfolios/${pid}/trades`, { method: "GET" }),
        customFetch(`/api/v1/paper-trading/portfolios/${pid}/summary`, { method: "GET" }),
      ]);
      const detail = detailRes?.data ?? detailRes;
      if (detail?.id) {
        setPortfolios((prev) =>
          prev.map((p) => (p.id === pid ? { ...p, ...detail } : p))
        );
      }
      setPositions(Array.isArray(posRes?.data) ? posRes.data : Array.isArray(posRes) ? posRes : []);
      setTrades(Array.isArray(tradeRes?.data) ? tradeRes.data : Array.isArray(tradeRes) ? tradeRes : []);
      setSummary(summaryRes?.data ?? summaryRes ?? null);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (isSignedIn) loadPortfolios();
  }, [isSignedIn, loadPortfolios]);

  useEffect(() => {
    if (selectedId) loadDetails(selectedId);
  }, [selectedId, loadDetails]);

  const selected = portfolios.find((p) => p.id === selectedId);

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to view paper trading portfolios.",
        forceRedirectUrl: "/paper-trading",
        signUpForceRedirectUrl: "/paper-trading",
      }}
      title="Paper Trading"
      description="Track simulated trades across stocks, sports, and prediction markets."
    >
      {loading ? (
        <div className="flex justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-blue-500" />
        </div>
      ) : portfolios.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-12 text-center">
          <BarChart3 className="mx-auto h-12 w-12 text-slate-300" />
          <h3 className="mt-4 text-lg font-semibold text-slate-800">No portfolios yet</h3>
          <p className="mt-1 text-sm text-slate-500">
            Ask an agent to paper trade, or create a portfolio via the API.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Portfolio cards */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {portfolios.map((p) => (
              <button
                key={p.id}
                onClick={() => setSelectedId(p.id)}
                className={cn(
                  "rounded-xl border p-4 text-left transition",
                  p.id === selectedId
                    ? "border-blue-500 bg-blue-50 ring-1 ring-blue-500"
                    : "border-slate-200 bg-white hover:border-slate-300"
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-slate-800">{p.name}</span>
                  <DollarSign className="h-4 w-4 text-slate-400" />
                </div>
                <div className="mt-2 text-2xl font-bold text-slate-900">
                  ${(p.total_value ?? p.cash_balance).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <div className="mt-1 flex items-center gap-1 text-sm">
                  {(p.total_return_pct ?? 0) >= 0 ? (
                    <TrendingUp className="h-3.5 w-3.5 text-emerald-500" />
                  ) : (
                    <TrendingDown className="h-3.5 w-3.5 text-red-500" />
                  )}
                  <span
                    className={cn(
                      "font-medium",
                      (p.total_return_pct ?? 0) >= 0 ? "text-emerald-600" : "text-red-600"
                    )}
                  >
                    {(p.total_return_pct ?? 0) >= 0 ? "+" : ""}
                    {(p.total_return_pct ?? 0).toFixed(2)}%
                  </span>
                  <span className="text-slate-400">from ${p.starting_balance.toLocaleString()}</span>
                </div>
              </button>
            ))}
          </div>

          {/* Tabs */}
          {selected && (
            <div>
              <div className="flex gap-1 border-b border-slate-200">
                {(["positions", "trades", "summary"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    className={cn(
                      "px-4 py-2.5 text-sm font-medium capitalize transition",
                      tab === t
                        ? "border-b-2 border-blue-500 text-blue-600"
                        : "text-slate-500 hover:text-slate-700"
                    )}
                  >
                    {t}
                  </button>
                ))}
              </div>

              <div className="mt-4">
                {tab === "positions" && (
                  <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
                    {positions.length === 0 ? (
                      <div className="p-8 text-center text-sm text-slate-500">No positions yet.</div>
                    ) : (
                      <table className="w-full text-sm">
                        <thead className="border-b border-slate-100 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                          <tr>
                            <th className="px-4 py-3">Symbol</th>
                            <th className="px-4 py-3">Type</th>
                            <th className="px-4 py-3">Side</th>
                            <th className="px-4 py-3 text-right">Qty</th>
                            <th className="px-4 py-3 text-right">Entry</th>
                            <th className="px-4 py-3 text-right">Current</th>
                            <th className="px-4 py-3 text-right">P/L</th>
                            <th className="px-4 py-3 text-right">P/L %</th>
                            <th className="px-4 py-3">Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {positions.map((pos) => (
                            <tr key={pos.id} className="hover:bg-slate-50">
                              <td className="px-4 py-3 font-medium text-slate-800">{pos.symbol}</td>
                              <td className="px-4 py-3 text-slate-500">{pos.asset_type}</td>
                              <td className="px-4 py-3">
                                <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", pos.side === "long" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700")}>
                                  {pos.side}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-right">{pos.quantity}</td>
                              <td className="px-4 py-3 text-right">${pos.entry_price.toFixed(2)}</td>
                              <td className="px-4 py-3 text-right">${pos.current_price.toFixed(2)}</td>
                              <td className={cn("px-4 py-3 text-right font-medium", pos.unrealized_pnl >= 0 ? "text-emerald-600" : "text-red-600")}>
                                {pos.unrealized_pnl >= 0 ? "+" : ""}${pos.unrealized_pnl.toFixed(2)}
                              </td>
                              <td className={cn("px-4 py-3 text-right font-medium", pos.pnl_pct >= 0 ? "text-emerald-600" : "text-red-600")}>
                                {pos.pnl_pct >= 0 ? "+" : ""}{pos.pnl_pct.toFixed(1)}%
                              </td>
                              <td className="px-4 py-3">
                                <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", pos.status === "open" ? "bg-blue-100 text-blue-700" : "bg-slate-100 text-slate-500")}>
                                  {pos.status}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}

                {tab === "trades" && (
                  <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
                    {trades.length === 0 ? (
                      <div className="p-8 text-center text-sm text-slate-500">No trades yet.</div>
                    ) : (
                      <table className="w-full text-sm">
                        <thead className="border-b border-slate-100 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                          <tr>
                            <th className="px-4 py-3">Time</th>
                            <th className="px-4 py-3">Symbol</th>
                            <th className="px-4 py-3">Action</th>
                            <th className="px-4 py-3 text-right">Qty</th>
                            <th className="px-4 py-3 text-right">Price</th>
                            <th className="px-4 py-3 text-right">Total</th>
                            <th className="px-4 py-3">Agent</th>
                            <th className="px-4 py-3">Notes</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {trades.map((t) => (
                            <tr key={t.id} className="hover:bg-slate-50">
                              <td className="px-4 py-3 text-slate-500">{new Date(t.executed_at).toLocaleString()}</td>
                              <td className="px-4 py-3 font-medium text-slate-800">{t.symbol}</td>
                              <td className="px-4 py-3">
                                <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", t.trade_type === "buy" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700")}>
                                  {t.trade_type.toUpperCase()}
                                </span>
                              </td>
                              <td className="px-4 py-3 text-right">{t.quantity}</td>
                              <td className="px-4 py-3 text-right">${t.price.toFixed(2)}</td>
                              <td className="px-4 py-3 text-right">${t.total.toFixed(2)}</td>
                              <td className="px-4 py-3 text-slate-500">{t.proposed_by}</td>
                              <td className="px-4 py-3 text-slate-500 max-w-[200px] truncate">{t.notes}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )}

                {tab === "summary" && summary && (
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                    <div className="rounded-xl border border-slate-200 bg-white p-4">
                      <div className="text-xs font-semibold uppercase text-slate-400">Total Value</div>
                      <div className="mt-1 text-xl font-bold">${summary.total_value.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-white p-4">
                      <div className="text-xs font-semibold uppercase text-slate-400">Return</div>
                      <div className={cn("mt-1 text-xl font-bold", summary.total_return_pct >= 0 ? "text-emerald-600" : "text-red-600")}>
                        {summary.total_return_pct >= 0 ? "+" : ""}{summary.total_return_pct.toFixed(2)}%
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-white p-4">
                      <div className="text-xs font-semibold uppercase text-slate-400">Win Rate</div>
                      <div className="mt-1 text-xl font-bold">{summary.win_rate_pct}%</div>
                      <div className="text-xs text-slate-400">{summary.winning_trades}W / {summary.losing_trades}L</div>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-white p-4">
                      <div className="text-xs font-semibold uppercase text-slate-400">Total Trades</div>
                      <div className="mt-1 text-xl font-bold">{summary.total_trades}</div>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-white p-4">
                      <div className="text-xs font-semibold uppercase text-slate-400">Realized P/L</div>
                      <div className={cn("mt-1 text-xl font-bold", summary.realized_pnl >= 0 ? "text-emerald-600" : "text-red-600")}>
                        {summary.realized_pnl >= 0 ? "+" : ""}${summary.realized_pnl.toFixed(2)}
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-white p-4">
                      <div className="text-xs font-semibold uppercase text-slate-400">Unrealized P/L</div>
                      <div className={cn("mt-1 text-xl font-bold", summary.unrealized_pnl >= 0 ? "text-emerald-600" : "text-red-600")}>
                        {summary.unrealized_pnl >= 0 ? "+" : ""}${summary.unrealized_pnl.toFixed(2)}
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-white p-4">
                      <div className="text-xs font-semibold uppercase text-slate-400">Cash</div>
                      <div className="mt-1 text-xl font-bold">${summary.cash_balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
                    </div>
                    {summary.best_trade && (
                      <div className="rounded-xl border border-slate-200 bg-white p-4">
                        <div className="text-xs font-semibold uppercase text-slate-400">Best Trade</div>
                        <div className="mt-1 text-xl font-bold text-emerald-600">{summary.best_trade.symbol}</div>
                        <div className="text-xs text-emerald-500">+${summary.best_trade.pnl.toFixed(2)}</div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </DashboardPageLayout>
  );
}
