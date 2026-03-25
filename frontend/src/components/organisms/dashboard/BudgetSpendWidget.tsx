"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, DollarSign } from "lucide-react";
import { customFetch } from "@/api/mutator";

type BudgetStatus = {
  monthly_total: number;
  monthly_pct: number;
  remaining: number;
  projected_month_end: number;
  daily_avg: number;
};

type AgentSpend = {
  agent: string;
  cost: number;
};

type BudgetResponse = {
  config: { monthly_budget: number };
  status: BudgetStatus;
  agent_today: AgentSpend[];
};

const fmt = (n: number) =>
  n >= 1000
    ? `$${(n / 1000).toFixed(1)}k`
    : `$${n.toFixed(2)}`;

export function BudgetSpendWidget() {
  const { data, isLoading, isError } = useQuery<BudgetResponse>({
    queryKey: ["dashboard", "budget-widget"],
    queryFn: async () => {
      const raw: any = await customFetch("/api/v1/cost-tracker/budget", {
        method: "GET",
      });
      return raw?.data ?? raw;
    },
    refetchInterval: 60_000,
    refetchOnMount: "always",
    retry: 2,
  });

  if (isLoading) {
    return <WidgetShell title="Budget" loading />;
  }

  if (isError || !data) {
    return <WidgetShell title="Budget" error="Unable to load budget data" />;
  }

  const { status, config, agent_today } = data;
  const budget = config.monthly_budget;
  const pct = Math.min(status.monthly_pct, 100);
  const barColor =
    pct >= 90 ? "bg-rose-500" : pct >= 75 ? "bg-amber-500" : "bg-blue-500";
  const topAgent = [...agent_today].sort((a, b) => b.cost - a.cost)[0];

  return (
    <WidgetShell title="Budget" href="/costs">
      <div className="flex items-end justify-between gap-2">
        <div>
          <p className="text-2xl font-bold text-slate-900">
            {fmt(status.monthly_total)}
          </p>
          <p className="text-xs text-slate-500">
            of {fmt(budget)} budget
          </p>
        </div>
        <div className="rounded-lg bg-blue-50 p-2">
          <DollarSign className="h-4 w-4 text-blue-600" />
        </div>
      </div>

      <div className="mt-3">
        <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className={`h-full rounded-full transition-all ${barColor}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="mt-1.5 flex items-center justify-between text-[11px] text-slate-500">
          <span>{pct.toFixed(0)}% used</span>
          <span>{fmt(status.remaining)} remaining</span>
        </div>
      </div>

      <div className="mt-3 space-y-1 border-t border-slate-100 pt-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-500">Projected month-end</span>
          <span
            className={`font-medium ${
              status.projected_month_end > budget
                ? "text-rose-600"
                : "text-slate-700"
            }`}
          >
            {fmt(status.projected_month_end)}
          </span>
        </div>
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-500">Daily average</span>
          <span className="font-medium text-slate-700">
            {fmt(status.daily_avg)}
          </span>
        </div>
        {topAgent ? (
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-500">Top agent today</span>
            <span className="font-medium text-slate-700">
              {topAgent.agent} ({fmt(topAgent.cost)})
            </span>
          </div>
        ) : null}
      </div>
    </WidgetShell>
  );
}

function WidgetShell({
  title,
  href,
  loading,
  error,
  children,
}: {
  title: string;
  href?: string;
  loading?: boolean;
  error?: string;
  children?: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 md:p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          {title}
        </h3>
        {href ? (
          <Link
            href={href}
            className="inline-flex items-center gap-1 text-xs text-slate-400 transition hover:text-slate-600"
          >
            View
            <ArrowUpRight className="h-3 w-3" />
          </Link>
        ) : null}
      </div>
      {loading ? (
        <div className="flex h-24 items-center justify-center text-xs text-slate-400">
          Loading...
        </div>
      ) : error ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700">
          {error}
        </div>
      ) : (
        children
      )}
    </section>
  );
}
