"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Clock, CheckCircle2, XCircle, Zap, AlertTriangle } from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { type TradeProposal, fetchTradeProposals } from "@/lib/polymarket-api";
import { cn } from "@/lib/utils";

const STATUS_ICONS: Record<string, typeof Clock> = {
  pending: Clock,
  approved: CheckCircle2,
  rejected: XCircle,
  executed: Zap,
  failed: AlertTriangle,
};

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-amber-100 text-amber-800",
  approved: "bg-blue-100 text-blue-800",
  rejected: "bg-slate-100 text-slate-600",
  executed: "bg-emerald-100 text-emerald-800",
  failed: "bg-rose-100 text-rose-800",
};

export default function TradeProposalsPage() {
  const { isSignedIn } = useAuth();
  const [proposals, setProposals] = useState<TradeProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchTradeProposals(filter || undefined);
      setProposals(data);
    } catch {
      setProposals([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    if (isSignedIn) load();
  }, [isSignedIn, load]);

  const filters = ["", "pending", "approved", "executed", "rejected", "failed"];

  return (
    <DashboardPageLayout
      signedOut={{ message: "Sign in to view trades.", forceRedirectUrl: "/trading/proposals", signUpForceRedirectUrl: "/trading/proposals" }}
      title="Trade Proposals"
      description="Review and approve agent-proposed Polymarket trades."
    >
      <div className="space-y-4">
        <div className="flex gap-2 border-b border-slate-200 pb-3">
          <Link href="/trading" className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100">Markets</Link>
          <Link href="/trading/proposals" className="rounded-lg bg-blue-100 px-3 py-1.5 text-sm font-medium text-blue-800">Trade Proposals</Link>
          <Link href="/trading/positions" className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100">Positions</Link>
          <Link href="/trading/history" className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100">History</Link>
          <Link href="/trading/settings" className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100">Settings</Link>
        </div>

        <div className="flex gap-2">
          {filters.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                "rounded-lg px-3 py-1.5 text-sm transition",
                filter === f ? "bg-blue-100 font-medium text-blue-800" : "text-slate-600 hover:bg-slate-100",
              )}
            >
              {f || "All"}
            </button>
          ))}
        </div>

        {loading ? (
          <p className="py-8 text-center text-sm text-slate-500">Loading proposals...</p>
        ) : proposals.length === 0 ? (
          <p className="py-8 text-center text-sm text-slate-500">No trade proposals yet.</p>
        ) : (
          <div className="space-y-3">
            {proposals.map((p) => {
              const Icon = STATUS_ICONS[p.status] || Clock;
              return (
                <div key={p.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-start justify-between">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-slate-900">{p.market_question}</p>
                      <div className="mt-2 flex flex-wrap gap-2 text-xs">
                        <span className={cn("rounded px-2 py-0.5 font-medium", p.side === "BUY" ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700")}>
                          {p.side} {p.outcome_label}
                        </span>
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600">
                          ${p.size_usdc.toFixed(2)} @ {(p.price * 100).toFixed(1)}¢
                        </span>
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600">
                          {p.order_type}
                        </span>
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600">
                          Confidence: {p.confidence.toFixed(0)}%
                        </span>
                      </div>
                      <p className="mt-2 text-xs text-slate-500 line-clamp-2">{p.reasoning}</p>
                      {p.execution_error ? (
                        <p className="mt-1 text-xs text-rose-600">{p.execution_error}</p>
                      ) : null}
                    </div>
                    <div className="ml-4 flex flex-col items-end gap-1">
                      <span className={cn("flex items-center gap-1 rounded px-2 py-1 text-xs font-medium", STATUS_COLORS[p.status] || "bg-slate-100 text-slate-600")}>
                        <Icon className="h-3 w-3" />
                        {p.status}
                      </span>
                      <span className="text-xs text-slate-400">
                        {new Date(p.created_at).toLocaleString()}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </DashboardPageLayout>
  );
}
