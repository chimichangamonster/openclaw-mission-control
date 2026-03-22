"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import {
  Star,
  AlertTriangle,
  Eye,
  ShoppingCart,
  Trash2,
  RefreshCw,
} from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { FeatureGate } from "@/components/molecules/FeatureGate";
import { cn } from "@/lib/utils";
import { customFetch } from "@/api/mutator";

/* ---------- Types ---------- */

interface WatchlistItem {
  id: string;
  portfolio_id: string;
  symbol: string;
  yahoo_ticker: string;
  company_name: string | null;
  exchange: string | null;
  sector: string | null;
  source_report: string;
  report_rating: string | null;
  expected_low: number | null;
  expected_high: number | null;
  current_price: number | null;
  rsi: number | null;
  volume_ratio: number | null;
  sentiment: string | null;
  sentiment_confidence: number | null;
  status: string;
  alert_reason: string | null;
  notes: string | null;
  price_updated_at: string | null;
  created_at: string;
  updated_at: string;
}

interface WatchlistSummary {
  watching: number;
  alerting: number;
  bought: number;
  total: number;
  alerts: WatchlistItem[];
}

/* ---------- Helpers ---------- */

const PORTFOLIO_ID = "59a1445b-3993-4bd3-8f3b-e49c02664be0";

function ratingColor(rating: string | null): string {
  if (!rating) return "text-slate-500";
  if (rating.includes("Strong")) return "text-emerald-600 font-semibold";
  if (rating.includes("Speculative")) return "text-amber-600";
  return "text-blue-600";
}

function statusBadge(status: string) {
  switch (status) {
    case "alerting":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
          <AlertTriangle className="h-3 w-3" /> Alert
        </span>
      );
    case "bought":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800">
          <ShoppingCart className="h-3 w-3" /> Bought
        </span>
      );
    case "removed":
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
          Removed
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
          <Eye className="h-3 w-3" /> Watching
        </span>
      );
  }
}

function rsiIndicator(rsi: number | null) {
  if (rsi === null) return <span className="text-slate-400">-</span>;
  const color =
    rsi < 30
      ? "text-emerald-600 font-semibold"
      : rsi < 40
        ? "text-emerald-500"
        : rsi > 70
          ? "text-red-600 font-semibold"
          : "text-slate-600";
  return <span className={color}>{rsi.toFixed(1)}</span>;
}

function volumeIndicator(ratio: number | null) {
  if (ratio === null) return <span className="text-slate-400">-</span>;
  const color =
    ratio > 2.0
      ? "text-amber-600 font-semibold"
      : ratio > 1.5
        ? "text-amber-500"
        : "text-slate-600";
  return <span className={color}>{ratio.toFixed(1)}x</span>;
}

/* ---------- Component ---------- */

export default function WatchlistPage() {
  const { isSignedIn } = useAuth();
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [summary, setSummary] = useState<WatchlistSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("all");

  const loadData = useCallback(async () => {
    try {
      const [itemsRes, summaryRes]: any[] = await Promise.all([
        customFetch(
          `/api/v1/watchlist/portfolios/${PORTFOLIO_ID}/items?status=${statusFilter}`,
          { method: "GET" },
        ),
        customFetch(
          `/api/v1/watchlist/portfolios/${PORTFOLIO_ID}/items/summary`,
          { method: "GET" },
        ),
      ]);
      const itemsData = Array.isArray(itemsRes?.data)
        ? itemsRes.data
        : Array.isArray(itemsRes)
          ? itemsRes
          : [];
      setItems(itemsData);
      setSummary(
        summaryRes?.data ? summaryRes.data : summaryRes ? summaryRes : null,
      );
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    if (isSignedIn) loadData();
  }, [isSignedIn, loadData]);

  const removeItem = async (itemId: string) => {
    try {
      await customFetch(
        `/api/v1/watchlist/portfolios/${PORTFOLIO_ID}/items/${itemId}`,
        { method: "DELETE" },
      );
      setItems((prev) => prev.filter((i) => i.id !== itemId));
    } catch {
      // ignore
    }
  };

  const alertCount = summary?.alerting ?? 0;

  return (
    <FeatureGate flag="watchlist" label="Watchlist">
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to view your watchlist.",
        forceRedirectUrl: "/watchlist",
        signUpForceRedirectUrl: "/watchlist",
      }}
      title="Stock Watchlist"
      description="Track report tickers and monitor for buy signals"
    >
      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 mb-6">
          <div className="rounded-xl border bg-white p-4">
            <p className="text-xs font-medium text-slate-500">Watching</p>
            <p className="mt-1 text-2xl font-bold text-blue-600">
              {summary.watching}
            </p>
          </div>
          <div
            className={cn(
              "rounded-xl border p-4",
              alertCount > 0 ? "bg-amber-50 border-amber-200" : "bg-white",
            )}
          >
            <p className="text-xs font-medium text-slate-500">Alerts</p>
            <p
              className={cn(
                "mt-1 text-2xl font-bold",
                alertCount > 0 ? "text-amber-600" : "text-slate-400",
              )}
            >
              {alertCount}
            </p>
          </div>
          <div className="rounded-xl border bg-white p-4">
            <p className="text-xs font-medium text-slate-500">Bought</p>
            <p className="mt-1 text-2xl font-bold text-emerald-600">
              {summary.bought}
            </p>
          </div>
          <div className="rounded-xl border bg-white p-4">
            <p className="text-xs font-medium text-slate-500">Total</p>
            <p className="mt-1 text-2xl font-bold text-slate-700">
              {summary.total}
            </p>
          </div>
        </div>
      )}

      {/* Alert Banner */}
      {summary && summary.alerts.length > 0 && (
        <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-amber-800">
            <AlertTriangle className="h-4 w-4" /> Active Buy Signals
          </h3>
          <div className="mt-2 space-y-1">
            {summary.alerts.map((a) => (
              <p key={a.id} className="text-sm text-amber-700">
                <span className="font-semibold">{a.symbol}</span> —{" "}
                {a.alert_reason || "Buy criteria met"}
                {a.rsi !== null && ` | RSI: ${a.rsi.toFixed(1)}`}
                {a.volume_ratio !== null &&
                  a.volume_ratio > 1.5 &&
                  ` | Vol: ${a.volume_ratio.toFixed(1)}x`}
              </p>
            ))}
          </div>
        </div>
      )}

      {/* Filter Tabs */}
      <div className="mb-4 flex gap-2">
        {["all", "watching", "alerting", "bought"].map((f) => (
          <button
            key={f}
            onClick={() => setStatusFilter(f)}
            className={cn(
              "rounded-lg px-3 py-1.5 text-sm font-medium transition",
              statusFilter === f
                ? "bg-blue-600 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200",
            )}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
        <button
          onClick={() => {
            setLoading(true);
            loadData();
          }}
          className="ml-auto rounded-lg bg-slate-100 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-200"
        >
          <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
        </button>
      </div>

      {/* Watchlist Table */}
      {loading ? (
        <div className="flex h-40 items-center justify-center text-slate-400">
          Loading watchlist...
        </div>
      ) : items.length === 0 ? (
        <div className="flex h-40 flex-col items-center justify-center text-slate-400">
          <Star className="mb-2 h-8 w-8" />
          <p className="text-sm">No watchlist items</p>
          <p className="text-xs">
            Items are added when the Stock Analyst scans reports
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b bg-slate-50">
              <tr>
                <th className="px-4 py-3 font-medium text-slate-500">
                  Symbol
                </th>
                <th className="px-4 py-3 font-medium text-slate-500">
                  Rating
                </th>
                <th className="px-4 py-3 font-medium text-slate-500 text-right">
                  Price
                </th>
                <th className="px-4 py-3 font-medium text-slate-500 text-right">
                  Range
                </th>
                <th className="px-4 py-3 font-medium text-slate-500 text-right">
                  RSI
                </th>
                <th className="px-4 py-3 font-medium text-slate-500 text-right">
                  Volume
                </th>
                <th className="px-4 py-3 font-medium text-slate-500">
                  Sentiment
                </th>
                <th className="px-4 py-3 font-medium text-slate-500">
                  Status
                </th>
                <th className="px-4 py-3 font-medium text-slate-500"></th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {items.map((item) => {
                const inRange =
                  item.current_price !== null &&
                  item.expected_low !== null &&
                  item.expected_high !== null;
                const belowRange =
                  inRange && item.current_price! < item.expected_low!;
                const aboveRange =
                  inRange && item.current_price! > item.expected_high!;

                return (
                  <tr
                    key={item.id}
                    className={cn(
                      "hover:bg-slate-50 transition",
                      item.status === "alerting" && "bg-amber-50/50",
                    )}
                  >
                    <td className="px-4 py-3">
                      <div>
                        <span className="font-semibold text-slate-800">
                          {item.symbol}
                        </span>
                        {item.exchange && (
                          <span className="ml-1 text-xs text-slate-400">
                            {item.exchange}
                          </span>
                        )}
                      </div>
                      {item.company_name && (
                        <p className="text-xs text-slate-400 truncate max-w-[160px]">
                          {item.company_name}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={ratingColor(item.report_rating)}>
                        {item.report_rating || "-"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-mono">
                      {item.current_price !== null ? (
                        <span
                          className={cn(
                            belowRange
                              ? "text-emerald-600"
                              : aboveRange
                                ? "text-red-500"
                                : "text-slate-700",
                          )}
                        >
                          ${item.current_price.toFixed(2)}
                        </span>
                      ) : (
                        <span className="text-slate-400">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right text-xs text-slate-500 font-mono">
                      {item.expected_low !== null &&
                      item.expected_high !== null ? (
                        <>
                          ${item.expected_low.toFixed(2)} - $
                          {item.expected_high.toFixed(2)}
                        </>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {rsiIndicator(item.rsi)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {volumeIndicator(item.volume_ratio)}
                    </td>
                    <td className="px-4 py-3">
                      {item.sentiment ? (
                        <span
                          className={cn(
                            "text-xs font-medium",
                            item.sentiment.includes("BULLISH")
                              ? "text-emerald-600"
                              : item.sentiment.includes("BEARISH")
                                ? "text-red-500"
                                : "text-slate-500",
                          )}
                        >
                          {item.sentiment}
                          {item.sentiment_confidence !== null && (
                            <span className="text-slate-400 ml-1">
                              ({item.sentiment_confidence}/10)
                            </span>
                          )}
                        </span>
                      ) : (
                        <span className="text-slate-400 text-xs">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3">{statusBadge(item.status)}</td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => removeItem(item.id)}
                        className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-500 transition"
                        title="Remove from watchlist"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Last Updated */}
      {items.length > 0 && (
        <p className="mt-3 text-xs text-slate-400">
          Prices updated by Stock Analyst morning scan.{" "}
          {items[0]?.price_updated_at
            ? `Last: ${new Date(items[0].price_updated_at).toLocaleString()}`
            : "No price data yet."}
        </p>
      )}
    </DashboardPageLayout>
    </FeatureGate>
  );
}
