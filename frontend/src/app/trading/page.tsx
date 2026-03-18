"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Search, TrendingUp } from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { type MarketSearchResult, searchMarkets } from "@/lib/polymarket-api";
import { cn } from "@/lib/utils";

export default function TradingPage() {
  const { isSignedIn } = useAuth();
  const [markets, setMarkets] = useState<MarketSearchResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  const loadMarkets = useCallback(async () => {
    try {
      setLoading(true);
      const data = await searchMarkets(query, 30);
      setMarkets(data);
    } catch {
      setMarkets([]);
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    if (isSignedIn) loadMarkets();
  }, [isSignedIn, loadMarkets]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    loadMarkets();
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
              <Link
                key={market.condition_id}
                href={`/trading/markets/${market.condition_id}`}
                className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:shadow-md"
              >
                <p className="text-sm font-medium text-slate-900 line-clamp-2">
                  {market.question}
                </p>
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
                  <span className="text-xs text-slate-500">
                    ${(market.volume / 1000).toFixed(0)}k vol
                  </span>
                </div>
                {market.end_date ? (
                  <p className="mt-2 text-xs text-slate-400">
                    Ends {new Date(market.end_date).toLocaleDateString()}
                  </p>
                ) : null}
              </Link>
            ))}
          </div>
        )}
      </div>
    </DashboardPageLayout>
  );
}
