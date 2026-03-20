"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Search, TrendingUp, BarChart3 } from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { type MarketSearchResult, searchMarkets } from "@/lib/polymarket-api";
import { cn } from "@/lib/utils";

const CATEGORIES = [
  { label: "Top", tag: "" },
  { label: "Politics", tag: "elections" },
  { label: "Crypto", tag: "crypto" },
  { label: "Sports", tag: "sports" },
  { label: "Finance", tag: "finance" },
  { label: "Science", tag: "science" },
  { label: "Culture", tag: "pop-culture" },
];

function formatVolume(vol: number): string {
  if (vol >= 1_000_000) return `$${(vol / 1_000_000).toFixed(1)}M`;
  if (vol >= 1_000) return `$${(vol / 1_000).toFixed(0)}k`;
  return `$${vol.toFixed(0)}`;
}

export default function TradingPage() {
  const { isSignedIn } = useAuth();
  const [markets, setMarkets] = useState<MarketSearchResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState("");

  const loadMarkets = useCallback(async (searchQuery?: string, tag?: string) => {
    try {
      setLoading(true);
      const q = searchQuery ?? query;
      const effectiveQuery = tag ? tag : q;
      const data = await searchMarkets(effectiveQuery, 30);
      setMarkets(Array.isArray(data) ? data : []);
    } catch {
      setMarkets([]);
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    if (isSignedIn) loadMarkets("", "");
  }, [isSignedIn]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setActiveCategory("");
    loadMarkets(query);
  };

  const handleCategory = (tag: string) => {
    setActiveCategory(tag);
    setQuery("");
    loadMarkets("", tag);
  };

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to browse prediction markets.",
        forceRedirectUrl: "/trading",
        signUpForceRedirectUrl: "/trading",
      }}
      title="Prediction Markets"
      description="Browse Polymarket markets. Agents propose trades — you approve."
    >
      <div className="space-y-4">
        {/* Navigation tabs */}
        <div className="flex gap-2 border-b border-slate-200 pb-3">
          <Link href="/trading" className="rounded-lg bg-blue-100 px-3 py-1.5 text-sm font-medium text-blue-800">
            Markets
          </Link>
          <Link href="/trading/proposals" className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100">
            Trade Proposals
          </Link>
          <Link href="/trading/positions" className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100">
            Positions
          </Link>
          <Link href="/trading/history" className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100">
            History
          </Link>
          <Link href="/trading/settings" className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100">
            Settings
          </Link>
        </div>

        {/* Category filters */}
        <div className="flex flex-wrap gap-2">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.tag}
              onClick={() => handleCategory(cat.tag)}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-medium transition",
                activeCategory === cat.tag
                  ? "bg-blue-600 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              )}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {/* Search */}
        <form onSubmit={handleSearch} className="flex gap-2">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search markets..."
            className="max-w-md"
          />
          <Button type="submit" variant="outline" size="sm">
            <Search className="h-4 w-4" />
          </Button>
        </form>

        {/* Markets grid */}
        {loading ? (
          <p className="py-8 text-center text-sm text-slate-500">Loading markets...</p>
        ) : markets.length === 0 ? (
          <p className="py-8 text-center text-sm text-slate-500">No markets found.</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {markets.map((market) => (
              <div
                key={market.condition_id}
                className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:shadow-md"
              >
                <a
                  href={`https://polymarket.com/event/${market.slug}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <p className="text-sm font-medium text-slate-900 line-clamp-2">
                    {market.question}
                  </p>
                </a>
                <div className="mt-3 flex items-center justify-between">
                  <div className="flex gap-3">
                    {market.yes_price !== null ? (
                      <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                        Yes {(market.yes_price * 100).toFixed(0)}¢
                      </span>
                    ) : null}
                    {market.no_price !== null ? (
                      <span className="rounded bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-700">
                        No {(market.no_price * 100).toFixed(0)}¢
                      </span>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-500">
                      {formatVolume(market.volume)} vol
                    </span>
                    <span className="text-xs text-slate-400">
                      {formatVolume(market.liquidity)} liq
                    </span>
                  </div>
                </div>
                {market.end_date ? (
                  <p className="mt-2 text-xs text-slate-400">
                    Ends {new Date(market.end_date).toLocaleDateString()}
                  </p>
                ) : null}
                <div className="mt-3 flex gap-2 border-t border-slate-100 pt-3">
                  <button
                    onClick={async (e) => {
                      e.stopPropagation();
                      try {
                        const apiUrl = process.env.NEXT_PUBLIC_API_URL || "";
                        const token = typeof window !== "undefined" ? localStorage.getItem("mc_local_auth_token") || "" : "";
                        const res = await fetch(`${apiUrl}/api/v1/paper-trading/portfolios`, {
                          headers: { Authorization: `Bearer ${token}` },
                        });
                        const portfolios = await res.json();
                        const pmPortfolio = Array.isArray(portfolios) ? portfolios.find((p: { name: string }) => p.name.toLowerCase().includes("prediction")) : null;
                        if (!pmPortfolio) {
                          alert("No prediction markets portfolio found. Create one first.");
                          return;
                        }
                        const tradeRes = await fetch(`${apiUrl}/api/v1/paper-trading/portfolios/${pmPortfolio.id}/trades`, {
                          method: "POST",
                          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
                          body: JSON.stringify({
                            symbol: market.question.slice(0, 60),
                            asset_type: "prediction",
                            trade_type: "buy",
                            quantity: 100,
                            price: market.yes_price ?? 0.5,
                            notes: `Buy Yes on "${market.question}" via MC`,
                            proposed_by: "mission-control",
                          }),
                        });
                        if (tradeRes.ok) {
                          alert(`Paper trade placed: Buy 100 Yes @ ${((market.yes_price ?? 0) * 100).toFixed(0)}¢`);
                        } else {
                          const err = await tradeRes.json().catch(() => ({}));
                          alert(`Trade failed: ${err.detail || tradeRes.statusText}`);
                        }
                      } catch (err) {
                        alert(`Error: ${err}`);
                      }
                    }}
                    className="flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-100 transition"
                  >
                    <BarChart3 className="h-3 w-3" /> Paper Buy Yes
                  </button>
                  <button
                    onClick={async (e) => {
                      e.stopPropagation();
                      try {
                        const apiUrl = process.env.NEXT_PUBLIC_API_URL || "";
                        const token = typeof window !== "undefined" ? localStorage.getItem("mc_local_auth_token") || "" : "";
                        const res = await fetch(`${apiUrl}/api/v1/paper-trading/portfolios`, {
                          headers: { Authorization: `Bearer ${token}` },
                        });
                        const portfolios = await res.json();
                        const pmPortfolio = Array.isArray(portfolios) ? portfolios.find((p: { name: string }) => p.name.toLowerCase().includes("prediction")) : null;
                        if (!pmPortfolio) {
                          alert("No prediction markets portfolio found. Create one first.");
                          return;
                        }
                        const tradeRes = await fetch(`${apiUrl}/api/v1/paper-trading/portfolios/${pmPortfolio.id}/trades`, {
                          method: "POST",
                          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
                          body: JSON.stringify({
                            symbol: market.question.slice(0, 60),
                            asset_type: "prediction",
                            trade_type: "buy",
                            quantity: 100,
                            price: market.no_price ?? 0.5,
                            notes: `Buy No on "${market.question}" via MC`,
                            proposed_by: "mission-control",
                          }),
                        });
                        if (tradeRes.ok) {
                          alert(`Paper trade placed: Buy 100 No @ ${((market.no_price ?? 0) * 100).toFixed(0)}¢`);
                        } else {
                          const err = await tradeRes.json().catch(() => ({}));
                          alert(`Trade failed: ${err.detail || tradeRes.statusText}`);
                        }
                      } catch (err) {
                        alert(`Error: ${err}`);
                      }
                    }}
                    className="flex items-center gap-1 rounded-md bg-rose-50 px-2 py-1 text-xs font-medium text-rose-700 hover:bg-rose-100 transition"
                  >
                    <BarChart3 className="h-3 w-3" /> Paper Buy No
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </DashboardPageLayout>
  );
}
