"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import { FeatureGate } from "@/components/molecules/FeatureGate";
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Target,
  Activity,
  Zap,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
} from "recharts";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { cn } from "@/lib/utils";
import { customFetch } from "@/api/mutator";

/* ---------- Types ---------- */

interface Portfolio {
  id: string;
  name: string;
  starting_balance: number;
  cash_balance: number;
  auto_trade?: boolean;
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
  company_name: string | null;
  exchange: string | null;
  sector: string | null;
  asset_type: string;
  side: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  pnl_pct: number;
  stop_loss: number | null;
  take_profit: number | null;
  source_report: string | null;
  status: string;
  entry_date: string;
  exit_date: string | null;
  exit_price: number | null;
  pnl_realized: number;
  total_fees: number;
  trade_count: number;
  hold_days: number;
  price_updated_at: string | null;
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
  avg_win: number;
  avg_loss: number;
  largest_win: number;
  largest_loss: number;
  profit_factor: number;
}

interface EquityPoint {
  date: string;
  equity: number;
  daily_pnl: number;
  cumulative_pnl: number;
}

interface Bet {
  id: string;
  sport: string;
  game: string;
  game_date: string | null;
  bet_type: string;
  selection: string;
  player: string | null;
  prop_type: string | null;
  line: number | null;
  odds: number;
  stake: number;
  kelly_pct: number | null;
  confidence: number | null;
  status: string;
  payout: number;
  pnl: number;
  settled_at: string | null;
  proposed_by: string;
  reasoning: string;
  book: string;
  created_at: string;
}

interface BetSummary {
  total_bets: number;
  pending_bets: number;
  pending_exposure: number;
  wins: number;
  losses: number;
  pushes: number;
  win_rate: number;
  total_staked: number;
  total_pnl: number;
  total_won: number;
  total_lost: number;
  roi: number;
  avg_odds: number;
  avg_stake: number;
  best_bet: { selection: string; game: string; pnl: number; odds: number } | null;
  worst_bet: { selection: string; game: string; pnl: number; odds: number } | null;
  by_sport: Record<string, { record: string; pnl: number; roi: number }>;
  by_type: Record<string, { record: string; pnl: number }>;
}

/* ---------- Helpers ---------- */

function fmtMoney(n: number, decimals = 2): string {
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (abs >= 10_000) return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}

function fmtPnl(n: number): string {
  return `${n >= 0 ? "+" : ""}${fmtMoney(n)}`;
}

function pnlColor(n: number): string {
  if (n > 0) return "text-emerald-600";
  if (n < 0) return "text-red-600";
  return "text-slate-500";
}

/* ---------- Component ---------- */

export default function PaperTradingPage() {
  const { isSignedIn } = useAuth();
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [equityCurve, setEquityCurve] = useState<EquityPoint[]>([]);
  const [bets, setBets] = useState<Bet[]>([]);
  const [betSummary, setBetSummary] = useState<BetSummary | null>(null);
  const [tab, setTab] = useState<"overview" | "positions" | "trades" | "bets">("overview");
  const [loading, setLoading] = useState(true);
  const [expandedTrade, setExpandedTrade] = useState<string | null>(null);
  const [expandedBet, setExpandedBet] = useState<string | null>(null);

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
      const [detailRes, posRes, tradeRes, summaryRes, curveRes, betsRes, betSumRes]: any[] = await Promise.all([
        customFetch(`/api/v1/paper-trading/portfolios/${pid}`, { method: "GET" }),
        customFetch(`/api/v1/paper-trading/portfolios/${pid}/positions?status=all`, { method: "GET" }),
        customFetch(`/api/v1/paper-trading/portfolios/${pid}/trades?limit=200`, { method: "GET" }),
        customFetch(`/api/v1/paper-trading/portfolios/${pid}/summary`, { method: "GET" }),
        customFetch(`/api/v1/paper-trading/portfolios/${pid}/equity-curve`, { method: "GET" }).catch(() => []),
        customFetch(`/api/v1/paper-bets/portfolios/${pid}/bets`, { method: "GET" }).catch(() => []),
        customFetch(`/api/v1/paper-bets/portfolios/${pid}/bets/summary`, { method: "GET" }).catch(() => null),
      ]);
      const detail = detailRes?.data ?? detailRes;
      if (detail?.id) {
        setPortfolios((prev) => prev.map((p) => (p.id === pid ? { ...p, ...detail } : p)));
      }
      setPositions(Array.isArray(posRes?.data) ? posRes.data : Array.isArray(posRes) ? posRes : []);
      setTrades(Array.isArray(tradeRes?.data) ? tradeRes.data : Array.isArray(tradeRes) ? tradeRes : []);
      setSummary(summaryRes?.data ?? summaryRes ?? null);
      const curve = Array.isArray(curveRes?.data) ? curveRes.data : Array.isArray(curveRes) ? curveRes : [];
      setEquityCurve(curve);
      const betsData = Array.isArray(betsRes?.data) ? betsRes.data : Array.isArray(betsRes) ? betsRes : [];
      setBets(betsData);
      setBetSummary(betSumRes?.data ?? betSumRes ?? null);
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
  const openPositions = positions.filter((p) => p.status === "open");
  const closedPositions = positions.filter((p) => p.status === "closed");

  // Derive portfolio category from name for context-specific UI
  type PortfolioCategory = "sports" | "prediction" | "trading";
  const getCategory = (name: string): PortfolioCategory => {
    const n = name.toLowerCase();
    if (n.includes("sport") || n.includes("betting") || n.includes("bet")) return "sports";
    if (n.includes("prediction") || n.includes("polymarket")) return "prediction";
    return "trading";
  };
  const category: PortfolioCategory = selected ? getCategory(selected.name) : "trading";
  const isSports = category === "sports";
  const pendingBets = bets.filter((b) => b.status === "pending");

  return (
    <FeatureGate flag="paper_trading" label="Paper Trading">
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to view paper trading portfolios.",
        forceRedirectUrl: "/paper-trading",
        signUpForceRedirectUrl: "/paper-trading",
      }}
      title="Trading Performance"
      description="Track P&L, win rates, and agent trading decisions across all portfolios."
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
          {/* ===== Strategy P&L Hero Cards ===== */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {portfolios.map((p) => {
              const totalReturn = p.total_return_pct ?? 0;
              const totalVal = p.total_value ?? p.cash_balance;
              const isSelected = p.id === selectedId;
              return (
                <button
                  key={p.id}
                  onClick={() => setSelectedId(p.id)}
                  className={cn(
                    "rounded-xl border p-5 text-left transition-all",
                    isSelected
                      ? "border-blue-500 bg-blue-50/50 ring-1 ring-blue-500 shadow-sm"
                      : "border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm"
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-slate-700">{p.name}</span>
                    <span className={cn(
                      "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold",
                      totalReturn >= 0
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-red-100 text-red-700"
                    )}>
                      {totalReturn >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
                      {totalReturn >= 0 ? "+" : ""}{totalReturn.toFixed(2)}%
                    </span>
                  </div>
                  <div className="mt-3 text-2xl font-bold text-slate-900">{fmtMoney(totalVal)}</div>
                  <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
                    <span>{getCategory(p.name) === "sports" ? "Bankroll" : "Cash"}: {fmtMoney(p.cash_balance)}</span>
                    <span>
                      {getCategory(p.name) === "sports"
                        ? `${p.id === selectedId ? pendingBets.length : (p.open_positions ?? 0)} pending bets`
                        : `${p.open_positions ?? 0} open positions`}
                    </span>
                  </div>
                  <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-2">
                    <span className="text-xs text-slate-500">Auto-trade</span>
                    <button
                      onClick={async (e) => {
                        e.stopPropagation();
                        try {
                          await customFetch(
                            `/api/v1/paper-trading/portfolios/${p.id}/auto-trade?enabled=${!p.auto_trade}`,
                            { method: "PATCH" }
                          );
                          setPortfolios((prev) =>
                            prev.map((pp) =>
                              pp.id === p.id ? { ...pp, auto_trade: !pp.auto_trade } : pp
                            )
                          );
                        } catch (err) {
                          console.error("Failed to toggle auto-trade", err);
                        }
                      }}
                      className={cn(
                        "relative inline-flex h-5 w-9 items-center rounded-full transition-colors",
                        p.auto_trade ? "bg-emerald-500" : "bg-slate-300"
                      )}
                    >
                      <span
                        className={cn(
                          "inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform",
                          p.auto_trade ? "translate-x-4" : "translate-x-0.5"
                        )}
                      />
                    </button>
                  </div>
                </button>
              );
            })}
          </div>

          {/* ===== Tabs ===== */}
          {selected && (
            <div>
              <div className="flex gap-1 border-b border-slate-200">
                {(category === "sports"
                  ? (["overview", "bets"] as const)
                  : (["overview", "positions", "trades"] as const)
                ).map((t) => (
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

              <div className="mt-5">
                {/* ===== OVERVIEW TAB ===== */}
                {tab === "overview" && summary && (
                  <div className="space-y-6">
                    {/* Key Metrics Row — context-specific */}
                    {isSports && betSummary ? (
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
                        <MetricCard label="Total P&L" value={fmtPnl(betSummary.total_pnl)} color={pnlColor(betSummary.total_pnl)} icon={<DollarSign className="h-4 w-4" />} />
                        <MetricCard label="Record" value={`${betSummary.wins}W-${betSummary.losses}L-${betSummary.pushes}P`} color="text-slate-900" icon={<Target className="h-4 w-4" />} />
                        <MetricCard label="Win Rate" value={`${betSummary.win_rate}%`} sub={`${betSummary.total_bets} total bets`} color="text-slate-900" icon={<Zap className="h-4 w-4" />} />
                        <MetricCard label="ROI" value={`${betSummary.roi >= 0 ? "+" : ""}${betSummary.roi.toFixed(1)}%`} color={pnlColor(betSummary.roi)} icon={<Activity className="h-4 w-4" />} />
                        <MetricCard label="Pending" value={`${betSummary.pending_bets}`} sub={`${fmtMoney(betSummary.pending_exposure)} exposed`} color="text-slate-900" />
                        <MetricCard label="Bankroll" value={fmtMoney(summary.cash_balance)} color="text-slate-900" />
                      </div>
                    ) : (
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
                        <MetricCard label="Total P&L" value={fmtPnl(summary.realized_pnl + summary.unrealized_pnl)} color={pnlColor(summary.realized_pnl + summary.unrealized_pnl)} icon={<DollarSign className="h-4 w-4" />} />
                        <MetricCard label="Realized" value={fmtPnl(summary.realized_pnl)} color={pnlColor(summary.realized_pnl)} icon={<Target className="h-4 w-4" />} />
                        <MetricCard label="Unrealized" value={fmtPnl(summary.unrealized_pnl)} color={pnlColor(summary.unrealized_pnl)} icon={<Activity className="h-4 w-4" />} />
                        <MetricCard label="Win Rate" value={`${summary.win_rate_pct}%`} sub={`${summary.winning_trades}W / ${summary.losing_trades}L`} color="text-slate-900" icon={<Zap className="h-4 w-4" />} />
                        <MetricCard label="Total Trades" value={String(summary.total_trades)} color="text-slate-900" />
                        <MetricCard label="Cash" value={fmtMoney(summary.cash_balance)} color="text-slate-900" />
                      </div>
                    )}

                    {/* Sport Breakdown (sports only) */}
                    {isSports && betSummary && Object.keys(betSummary.by_sport).length > 0 && (
                      <div className="rounded-xl border border-slate-200 bg-white p-5">
                        <h3 className="text-sm font-semibold text-slate-700 mb-3">By Sport</h3>
                        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                          {Object.entries(betSummary.by_sport).map(([sport, raw]) => {
                            const data = raw as { record: string; pnl: number; roi: number };
                            return (
                              <div key={sport} className="rounded-lg border border-slate-100 p-3">
                                <div className="text-xs font-semibold uppercase text-slate-500">{sport}</div>
                                <div className="mt-1 text-sm font-medium text-slate-800">{data.record}</div>
                                <div className={cn("text-xs font-medium", pnlColor(data.pnl))}>{fmtPnl(data.pnl)} ({data.roi >= 0 ? "+" : ""}{data.roi.toFixed(1)}%)</div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* Equity Curve (trading only) */}
                    {!isSports && equityCurve.length > 1 && (
                      <div className="rounded-xl border border-slate-200 bg-white p-5">
                        <h3 className="text-sm font-semibold text-slate-700">Equity Curve</h3>
                        <div className="mt-3 h-64">
                          <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={equityCurve}>
                              <defs>
                                <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.15} />
                                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                                </linearGradient>
                              </defs>
                              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                              <XAxis
                                dataKey="date"
                                tick={{ fontSize: 11, fill: "#94a3b8" }}
                                tickFormatter={(v: string) => v.slice(5)}
                              />
                              <YAxis
                                tick={{ fontSize: 11, fill: "#94a3b8" }}
                                tickFormatter={(v: number) => fmtMoney(v, 0)}
                              />
                              <Tooltip
                                contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12 }}
                                formatter={(value) => [fmtMoney(value as number), "Equity"]}
                                labelFormatter={(label) => `Date: ${label}`}
                              />
                              <Area
                                type="monotone"
                                dataKey="equity"
                                stroke="#3b82f6"
                                strokeWidth={2}
                                fill="url(#eqGrad)"
                              />
                            </AreaChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    )}

                    {/* Daily P&L Bar Chart (trading only) */}
                    {!isSports && equityCurve.length > 1 && (
                      <div className="rounded-xl border border-slate-200 bg-white p-5">
                        <h3 className="text-sm font-semibold text-slate-700">Daily P&L</h3>
                        <div className="mt-3 h-48">
                          <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={equityCurve}>
                              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                              <XAxis
                                dataKey="date"
                                tick={{ fontSize: 11, fill: "#94a3b8" }}
                                tickFormatter={(v: string) => v.slice(5)}
                              />
                              <YAxis
                                tick={{ fontSize: 11, fill: "#94a3b8" }}
                                tickFormatter={(v: number) => fmtMoney(v, 0)}
                              />
                              <Tooltip
                                contentStyle={{ borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12 }}
                                formatter={(value) => [fmtPnl(value as number), "P&L"]}
                                labelFormatter={(label) => `Date: ${label}`}
                              />
                              <Bar dataKey="daily_pnl" radius={[3, 3, 0, 0]}>
                                {equityCurve.map((entry, i) => (
                                  <Cell
                                    key={i}
                                    fill={entry.daily_pnl >= 0 ? "#10b981" : "#ef4444"}
                                    fillOpacity={0.8}
                                  />
                                ))}
                              </Bar>
                            </BarChart>
                          </ResponsiveContainer>
                        </div>
                      </div>
                    )}

                    {/* Performance Stats Grid — context-specific */}
                    {isSports && betSummary ? (
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                        <StatCard label="Total Staked" value={fmtMoney(betSummary.total_staked)} color="text-slate-900" />
                        <StatCard label="Total Won" value={fmtPnl(betSummary.total_won)} color="text-emerald-600" />
                        <StatCard label="Total Lost" value={fmtPnl(-betSummary.total_lost)} color="text-red-600" />
                        <StatCard label="Avg Stake" value={fmtMoney(betSummary.avg_stake)} color="text-slate-900" />
                        <StatCard label="Avg Odds" value={betSummary.avg_odds >= 0 ? `+${betSummary.avg_odds}` : String(betSummary.avg_odds)} color="text-slate-900" />
                        <StatCard label="Best Bet" value={betSummary.best_bet ? `${betSummary.best_bet.selection.slice(0, 15)} ${fmtPnl(betSummary.best_bet.pnl)}` : "—"} color="text-emerald-600" />
                        <StatCard label="Worst Bet" value={betSummary.worst_bet ? `${betSummary.worst_bet.selection.slice(0, 15)} ${fmtPnl(betSummary.worst_bet.pnl)}` : "—"} color="text-red-600" />
                        <StatCard label="ROI" value={`${betSummary.roi >= 0 ? "+" : ""}${betSummary.roi.toFixed(1)}%`} color={pnlColor(betSummary.roi)} />
                      </div>
                    ) : (
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                        <StatCard label="Avg Win" value={fmtPnl(summary.avg_win)} color="text-emerald-600" />
                        <StatCard label="Avg Loss" value={fmtPnl(summary.avg_loss)} color="text-red-600" />
                        <StatCard label="Best Trade" value={summary.best_trade ? `${summary.best_trade.symbol} ${fmtPnl(summary.best_trade.pnl)}` : "—"} color="text-emerald-600" />
                        <StatCard label="Worst Trade" value={summary.worst_trade ? `${summary.worst_trade.symbol} ${fmtPnl(summary.worst_trade.pnl)}` : "—"} color="text-red-600" />
                        <StatCard label="Largest Win" value={fmtPnl(summary.largest_win)} color="text-emerald-600" />
                        <StatCard label="Largest Loss" value={fmtPnl(summary.largest_loss)} color="text-red-600" />
                        <StatCard label="Profit Factor" value={summary.profit_factor > 0 ? summary.profit_factor.toFixed(2) : "—"} color="text-slate-900" />
                        <StatCard label="Return" value={`${summary.total_return_pct >= 0 ? "+" : ""}${summary.total_return_pct.toFixed(2)}%`} color={pnlColor(summary.total_return_pct)} />
                      </div>
                    )}

                    {/* Pending Bets Quick View (sports only) */}
                    {isSports && pendingBets.length > 0 && (
                      <div className="rounded-xl border border-slate-200 bg-white">
                        <div className="border-b border-slate-100 px-5 py-3">
                          <h3 className="text-sm font-semibold text-slate-700">Pending Bets ({pendingBets.length})</h3>
                        </div>
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                              <tr>
                                <th className="px-5 py-3">Selection</th>
                                <th className="px-5 py-3">Game</th>
                                <th className="px-5 py-3">Game Date</th>
                                <th className="px-5 py-3">Sport</th>
                                <th className="px-5 py-3 text-right">Odds</th>
                                <th className="px-5 py-3 text-right">Stake</th>
                                <th className="px-5 py-3 text-right">To Win</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                              {pendingBets.map((b) => {
                                const decOdds = b.odds > 0 ? b.odds / 100 + 1 : 100 / Math.abs(b.odds) + 1;
                                const toWin = b.stake * (decOdds - 1);
                                return (
                                  <tr key={b.id} className="hover:bg-slate-50/50">
                                    <td className="px-5 py-3 font-medium text-slate-800">{b.selection}</td>
                                    <td className="px-5 py-3 text-slate-500">{b.game}</td>
                                    <td className="px-5 py-3 text-slate-500 text-xs tabular-nums">
                                      {b.game_date ? new Date(b.game_date).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "—"}
                                    </td>
                                    <td className="px-5 py-3">
                                      <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700 uppercase">{b.sport}</span>
                                    </td>
                                    <td className="px-5 py-3 text-right tabular-nums font-medium">{b.odds > 0 ? `+${b.odds}` : b.odds}</td>
                                    <td className="px-5 py-3 text-right tabular-nums">{fmtMoney(b.stake)}</td>
                                    <td className="px-5 py-3 text-right tabular-nums text-emerald-600">{fmtMoney(toWin)}</td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    {/* Open Positions Quick View (trading only) */}
                    {!isSports && openPositions.length > 0 && (
                      <div className="rounded-xl border border-slate-200 bg-white">
                        <div className="border-b border-slate-100 px-5 py-3">
                          <h3 className="text-sm font-semibold text-slate-700">Open Positions ({openPositions.length})</h3>
                        </div>
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                              <tr>
                                <th className="px-5 py-3">Symbol</th>
                                <th className="px-5 py-3">Side</th>
                                <th className="px-5 py-3 text-right">Qty</th>
                                <th className="px-5 py-3 text-right">Entry</th>
                                <th className="px-5 py-3 text-right">Current</th>
                                <th className="px-5 py-3 text-right">P&L</th>
                                <th className="px-5 py-3 text-right">P&L %</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                              {openPositions.map((pos) => (
                                <tr key={pos.id} className="hover:bg-slate-50/50">
                                  <td className="px-5 py-3 font-medium text-slate-800">{pos.symbol}</td>
                                  <td className="px-5 py-3">
                                    <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", pos.side === "long" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700")}>
                                      {pos.side}
                                    </span>
                                  </td>
                                  <td className="px-5 py-3 text-right tabular-nums">{pos.quantity}</td>
                                  <td className="px-5 py-3 text-right tabular-nums">${pos.entry_price.toFixed(2)}</td>
                                  <td className="px-5 py-3 text-right tabular-nums">${pos.current_price.toFixed(2)}</td>
                                  <td className={cn("px-5 py-3 text-right font-medium tabular-nums", pnlColor(pos.unrealized_pnl))}>
                                    {fmtPnl(pos.unrealized_pnl)}
                                  </td>
                                  <td className={cn("px-5 py-3 text-right font-medium tabular-nums", pnlColor(pos.pnl_pct))}>
                                    {pos.pnl_pct >= 0 ? "+" : ""}{pos.pnl_pct.toFixed(1)}%
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* ===== POSITIONS TAB ===== */}
                {tab === "positions" && (
                  <div className="space-y-6">
                    {/* Open Positions */}
                    <PositionsTable title="Open Positions" positions={openPositions} />
                    {/* Closed Positions */}
                    <PositionsTable title="Closed Positions" positions={closedPositions} showRealized />
                  </div>
                )}

                {/* ===== TRADES TAB (Decision Log) ===== */}
                {tab === "trades" && (
                  <div className="rounded-xl border border-slate-200 bg-white">
                    <div className="border-b border-slate-100 px-5 py-3">
                      <h3 className="text-sm font-semibold text-slate-700">Decision Log</h3>
                      <p className="text-xs text-slate-400">Expandable trade entries with agent reasoning</p>
                    </div>
                    {trades.length === 0 ? (
                      <div className="p-8 text-center text-sm text-slate-500">No trades yet.</div>
                    ) : (
                      <div className="divide-y divide-slate-100">
                        {trades.map((t) => {
                          const isExpanded = expandedTrade === t.id;
                          return (
                            <div key={t.id}>
                              <button
                                onClick={() => setExpandedTrade(isExpanded ? null : t.id)}
                                className="flex w-full items-center gap-2 sm:gap-3 px-3 sm:px-5 py-3 text-left hover:bg-slate-50/50 transition flex-wrap sm:flex-nowrap"
                              >
                                {isExpanded ? (
                                  <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />
                                ) : (
                                  <ChevronRight className="h-4 w-4 shrink-0 text-slate-400" />
                                )}
                                <span className={cn(
                                  "inline-flex w-10 justify-center rounded-full px-2 py-0.5 text-xs font-semibold",
                                  t.trade_type === "buy" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"
                                )}>
                                  {t.trade_type.toUpperCase()}
                                </span>
                                <span className="font-medium text-slate-800 text-sm">{t.symbol}</span>
                                <span className="text-xs text-slate-500">{t.quantity} @ ${t.price.toFixed(2)}</span>
                                <span className="ml-auto text-xs text-slate-400 hidden sm:inline">
                                  {new Date(t.executed_at).toLocaleDateString()} {new Date(t.executed_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                                </span>
                                <span className="text-xs text-slate-500 font-medium">{fmtMoney(t.total)}</span>
                              </button>
                              {isExpanded && (() => {
                                const pos = positions.find((p) => p.symbol === t.symbol);
                                return (
                                  <div className="bg-slate-50/50 px-4 sm:px-12 pb-4 pt-1">
                                    <div className="grid grid-cols-2 gap-x-4 sm:gap-x-8 gap-y-2 text-xs sm:grid-cols-5">
                                      <div>
                                        <span className="text-slate-400">Asset</span>
                                        <div className="font-medium text-slate-700">{t.asset_type}</div>
                                        {pos?.company_name && <div className="text-slate-400 truncate">{pos.company_name}</div>}
                                      </div>
                                      <div>
                                        <span className="text-slate-400">Total Cost</span>
                                        <div className="font-medium text-slate-700">{fmtMoney(t.total)}</div>
                                        <div className="text-slate-400">Fee: {fmtMoney(t.fees)}</div>
                                      </div>
                                      <div>
                                        <span className="text-slate-400">Agent</span>
                                        <div className="font-medium text-slate-700">{t.proposed_by || "manual"}</div>
                                        {pos?.exchange && <span className="rounded bg-slate-200 px-1 py-0.5 text-[10px] font-medium text-slate-600">{pos.exchange}</span>}
                                      </div>
                                      {pos?.stop_loss && (
                                        <div>
                                          <span className="text-slate-400">Stop Loss</span>
                                          <div className="font-medium text-red-600">${pos.stop_loss.toFixed(2)}</div>
                                        </div>
                                      )}
                                      {pos?.take_profit && (
                                        <div>
                                          <span className="text-slate-400">Take Profit</span>
                                          <div className="font-medium text-emerald-600">${pos.take_profit.toFixed(2)}</div>
                                        </div>
                                      )}
                                    </div>
                                    {(t.notes || pos?.source_report) && (
                                      <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
                                        {pos?.source_report && (
                                          <div className="flex items-center gap-2 mb-2">
                                            <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold text-blue-700">SOURCE</span>
                                            <span className="text-xs text-slate-600">{pos.source_report}</span>
                                          </div>
                                        )}
                                        {t.notes && (
                                          <>
                                            <div className="text-xs font-semibold text-slate-500 mb-1">Reasoning</div>
                                            <p className="text-xs text-slate-700 whitespace-pre-wrap leading-relaxed">{t.notes}</p>
                                          </>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                );
                              })()}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}

                {/* ===== BETS TAB ===== */}
                {tab === "bets" && (
                  <div className="space-y-6">
                    {/* Bet Summary Cards */}
                    {betSummary && betSummary.total_bets > 0 && (
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
                        <MetricCard label="Record" value={`${betSummary.wins}-${betSummary.losses}-${betSummary.pushes}`} color="text-slate-900" sub={`${betSummary.win_rate}% win rate`} />
                        <MetricCard label="P&L" value={fmtPnl(betSummary.total_pnl)} color={pnlColor(betSummary.total_pnl)} />
                        <MetricCard label="ROI" value={`${betSummary.roi >= 0 ? "+" : ""}${betSummary.roi}%`} color={pnlColor(betSummary.roi)} />
                        <MetricCard label="Total Staked" value={fmtMoney(betSummary.total_staked)} color="text-slate-900" />
                        <MetricCard label="Pending" value={String(betSummary.pending_bets)} color="text-amber-600" sub={`${fmtMoney(betSummary.pending_exposure)} exposed`} />
                        <MetricCard label="Avg Stake" value={fmtMoney(betSummary.avg_stake)} color="text-slate-900" />
                      </div>
                    )}

                    {/* By Sport Breakdown */}
                    {betSummary && Object.keys(betSummary.by_sport).length > 0 && (
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                        {Object.entries(betSummary.by_sport).map(([sport, data]) => (
                          <StatCard key={sport} label={sport.toUpperCase()} value={`${data.record} (${fmtPnl(data.pnl)})`} color={pnlColor(data.pnl)} />
                        ))}
                      </div>
                    )}

                    {/* Bet List */}
                    <div className="rounded-xl border border-slate-200 bg-white">
                      <div className="border-b border-slate-100 px-5 py-3">
                        <h3 className="text-sm font-semibold text-slate-700">Bet History</h3>
                      </div>
                      {bets.length === 0 ? (
                        <div className="p-8 text-center text-sm text-slate-500">No bets yet. Ask the Sports Analyst to place paper bets.</div>
                      ) : (
                        <div className="divide-y divide-slate-100">
                          {bets.map((b) => {
                            const isExp = expandedBet === b.id;
                            return (
                              <div key={b.id}>
                                <button
                                  onClick={() => setExpandedBet(isExp ? null : b.id)}
                                  className="flex w-full items-center gap-2 sm:gap-3 px-3 sm:px-5 py-3 text-left hover:bg-slate-50/50 transition flex-wrap sm:flex-nowrap"
                                >
                                  {isExp ? (
                                    <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />
                                  ) : (
                                    <ChevronRight className="h-4 w-4 shrink-0 text-slate-400" />
                                  )}
                                  <span className={cn(
                                    "inline-flex w-16 justify-center rounded-full px-2 py-0.5 text-xs font-semibold",
                                    b.status === "won" ? "bg-emerald-100 text-emerald-700" :
                                    b.status === "lost" ? "bg-red-100 text-red-700" :
                                    b.status === "pending" ? "bg-amber-100 text-amber-700" :
                                    "bg-slate-100 text-slate-500"
                                  )}>
                                    {b.status.toUpperCase()}
                                  </span>
                                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-medium text-slate-600 uppercase">{b.sport}</span>
                                  <span className="font-medium text-slate-800 text-sm truncate">{b.selection}</span>
                                  <span className="text-xs text-slate-500 hidden sm:inline truncate">{b.game}</span>
                                  <span className="ml-auto text-xs font-mono text-slate-500">{b.odds >= 0 ? "+" : ""}{b.odds}</span>
                                  <span className="text-xs font-medium text-slate-700">{fmtMoney(b.stake)}</span>
                                  {b.status !== "pending" && (
                                    <span className={cn("text-xs font-bold tabular-nums", pnlColor(b.pnl))}>
                                      {fmtPnl(b.pnl)}
                                    </span>
                                  )}
                                </button>
                                {isExp && (
                                  <div className="bg-slate-50/50 px-4 sm:px-12 pb-4 pt-1">
                                    <div className="grid grid-cols-2 gap-x-4 sm:gap-x-8 gap-y-2 text-xs sm:grid-cols-4">
                                      <div>
                                        <span className="text-slate-400">Type</span>
                                        <div className="font-medium text-slate-700">{b.bet_type}{b.player ? ` — ${b.player}` : ""}</div>
                                      </div>
                                      <div>
                                        <span className="text-slate-400">Game Date</span>
                                        <div className="font-medium text-slate-700">{b.game_date ? new Date(b.game_date).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "—"}</div>
                                      </div>
                                      <div>
                                        <span className="text-slate-400">Line</span>
                                        <div className="font-medium text-slate-700">{b.line ?? "—"}</div>
                                      </div>
                                      <div>
                                        <span className="text-slate-400">Book</span>
                                        <div className="font-medium text-slate-700">{b.book || "—"}</div>
                                      </div>
                                      <div>
                                        <span className="text-slate-400">Agent</span>
                                        <div className="font-medium text-slate-700">{b.proposed_by || "manual"}</div>
                                      </div>
                                      {b.settled_at && (
                                        <div>
                                          <span className="text-slate-400">Settled</span>
                                          <div className="font-medium text-slate-700">{new Date(b.settled_at).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</div>
                                        </div>
                                      )}
                                      {b.kelly_pct != null && (
                                        <div>
                                          <span className="text-slate-400">Kelly %</span>
                                          <div className="font-medium text-slate-700">{b.kelly_pct.toFixed(1)}%</div>
                                        </div>
                                      )}
                                      {b.confidence != null && (
                                        <div>
                                          <span className="text-slate-400">Confidence</span>
                                          <div className="font-medium text-slate-700">{b.confidence}%</div>
                                        </div>
                                      )}
                                      {b.payout > 0 && (
                                        <div>
                                          <span className="text-slate-400">Payout</span>
                                          <div className="font-medium text-emerald-600">{fmtMoney(b.payout)}</div>
                                        </div>
                                      )}
                                    </div>
                                    {b.reasoning && (
                                      <div className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
                                        <div className="text-xs font-semibold text-slate-500 mb-1">Reasoning</div>
                                        <p className="text-xs text-slate-700 whitespace-pre-wrap">{b.reasoning}</p>
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </DashboardPageLayout>
    </FeatureGate>
  );
}

/* ---------- Sub-components ---------- */

function MetricCard({
  label,
  value,
  sub,
  color,
  icon,
}: {
  label: string;
  value: string;
  sub?: string;
  color: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-center gap-1.5 text-xs font-semibold uppercase text-slate-400">
        {icon && <span className="text-slate-300">{icon}</span>}
        {label}
      </div>
      <div className={cn("mt-1 text-xl font-bold tabular-nums", color)}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-400">{sub}</div>}
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
      <div className="text-xs font-semibold uppercase text-slate-400">{label}</div>
      <div className={cn("mt-1 text-base font-bold tabular-nums", color)}>{value}</div>
    </div>
  );
}

function PositionsTable({
  title,
  positions,
  showRealized = false,
}: {
  title: string;
  positions: Position[];
  showRealized?: boolean;
}) {
  if (positions.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
        No {title.toLowerCase()}.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-5 py-3">
        <h3 className="text-sm font-semibold text-slate-700">{title} ({positions.length})</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-3 py-3 md:px-5">Symbol</th>
              <th className="hidden sm:table-cell px-3 py-3 md:px-5">Side</th>
              <th className="px-3 py-3 md:px-5 text-right">Qty</th>
              <th className="px-3 py-3 md:px-5 text-right">Entry</th>
              <th className="px-3 py-3 md:px-5 text-right">{showRealized ? "Exit" : "Current"}</th>
              {!showRealized && <th className="hidden lg:table-cell px-3 py-3 md:px-5 text-right">Stop Loss</th>}
              {!showRealized && <th className="hidden lg:table-cell px-3 py-3 md:px-5 text-right">Target</th>}
              <th className="px-3 py-3 md:px-5 text-right">P&L</th>
              <th className="hidden sm:table-cell px-3 py-3 md:px-5 text-right">P&L %</th>
              <th className="hidden md:table-cell px-3 py-3 md:px-5 text-right">Fees</th>
              <th className="hidden md:table-cell px-3 py-3 md:px-5 text-right">Days</th>
              {showRealized && <th className="hidden sm:table-cell px-3 py-3 md:px-5">Closed</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {positions.map((pos) => {
              const pnl = showRealized ? pos.pnl_realized : pos.unrealized_pnl;
              const displayPrice = showRealized ? (pos.exit_price ?? pos.current_price) : pos.current_price;
              const slDistance = pos.stop_loss && pos.current_price ? ((pos.current_price - pos.stop_loss) / pos.current_price * 100) : null;
              const tpDistance = pos.take_profit && pos.current_price ? ((pos.take_profit - pos.current_price) / pos.current_price * 100) : null;
              return (
                <tr key={pos.id} className="hover:bg-slate-50/50">
                  <td className="px-3 py-3 md:px-5">
                    <div className="font-medium text-slate-800">{pos.symbol}</div>
                    {pos.company_name && <div className="text-xs text-slate-400 truncate max-w-[120px] md:max-w-[160px]">{pos.company_name}</div>}
                    <div className="flex gap-1 mt-0.5">
                      <span className={cn("rounded-full px-1.5 py-0.5 text-[10px] font-medium sm:hidden", pos.side === "long" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700")}>{pos.side}</span>
                      {pos.exchange && <span className="hidden sm:inline rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">{pos.exchange}</span>}
                      {pos.sector && <span className="hidden md:inline rounded bg-blue-50 px-1.5 py-0.5 text-[10px] font-medium text-blue-500">{pos.sector}</span>}
                    </div>
                  </td>
                  <td className="hidden sm:table-cell px-3 py-3 md:px-5">
                    <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", pos.side === "long" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700")}>
                      {pos.side}
                    </span>
                  </td>
                  <td className="px-3 py-3 md:px-5 text-right tabular-nums">{pos.quantity}</td>
                  <td className="px-3 py-3 md:px-5 text-right tabular-nums">${pos.entry_price.toFixed(2)}</td>
                  <td className="px-3 py-3 md:px-5 text-right">
                    <div className="tabular-nums">${displayPrice.toFixed(2)}</div>
                    {pos.price_updated_at && <div className="hidden md:block text-[10px] text-slate-400">{new Date(pos.price_updated_at).toLocaleDateString()}</div>}
                  </td>
                  {!showRealized && (
                    <td className="hidden lg:table-cell px-3 py-3 md:px-5 text-right">
                      {pos.stop_loss ? (
                        <div>
                          <div className="tabular-nums text-red-600">${pos.stop_loss.toFixed(2)}</div>
                          {slDistance !== null && <div className="text-[10px] text-slate-400">{slDistance.toFixed(1)}% away</div>}
                        </div>
                      ) : <span className="text-slate-300">—</span>}
                    </td>
                  )}
                  {!showRealized && (
                    <td className="hidden lg:table-cell px-3 py-3 md:px-5 text-right">
                      {pos.take_profit ? (
                        <div>
                          <div className="tabular-nums text-emerald-600">${pos.take_profit.toFixed(2)}</div>
                          {tpDistance !== null && <div className="text-[10px] text-slate-400">{tpDistance.toFixed(1)}% away</div>}
                        </div>
                      ) : <span className="text-slate-300">—</span>}
                    </td>
                  )}
                  <td className={cn("px-3 py-3 md:px-5 text-right font-medium tabular-nums", pnlColor(pnl))}>
                    {fmtPnl(pnl)}
                    <div className={cn("sm:hidden text-[10px] font-normal", pnlColor(pos.pnl_pct))}>
                      {pos.pnl_pct >= 0 ? "+" : ""}{pos.pnl_pct.toFixed(1)}%
                    </div>
                  </td>
                  <td className={cn("hidden sm:table-cell px-3 py-3 md:px-5 text-right font-medium tabular-nums", pnlColor(pos.pnl_pct))}>
                    {pos.pnl_pct >= 0 ? "+" : ""}{pos.pnl_pct.toFixed(1)}%
                  </td>
                  <td className="hidden md:table-cell px-3 py-3 md:px-5 text-right tabular-nums text-xs text-slate-500">
                    {pos.total_fees > 0 ? `$${pos.total_fees.toFixed(2)}` : "—"}
                    {pos.trade_count > 1 && <div className="text-[10px] text-slate-400">{pos.trade_count} trades</div>}
                  </td>
                  <td className="hidden md:table-cell px-3 py-3 md:px-5 text-right tabular-nums text-xs text-slate-500">
                    {pos.hold_days}d
                  </td>
                  {showRealized && (
                    <td className="hidden sm:table-cell px-3 py-3 md:px-5 text-xs text-slate-400">
                      {pos.exit_date ? new Date(pos.exit_date).toLocaleDateString() : "—"}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
