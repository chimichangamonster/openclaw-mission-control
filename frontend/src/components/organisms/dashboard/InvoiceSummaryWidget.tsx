"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowUpRight, FileText, Loader2 } from "lucide-react";
import { customFetch } from "@/api/mutator";

type Invoice = {
  id: string;
  status: string;
  total: number;
  currency: string;
  due_date: string | null;
};

const fmt = (n: number, currency = "CAD") =>
  new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(n);

export function InvoiceSummaryWidget() {
  const { data, isLoading, isError } = useQuery<Invoice[]>({
    queryKey: ["dashboard", "invoices-widget"],
    queryFn: async () => {
      const raw: any = await customFetch("/api/v1/invoices", {
        method: "GET",
      });
      const invoices = raw?.data ?? raw;
      return Array.isArray(invoices) ? invoices : [];
    },
    refetchInterval: 120_000,
    refetchOnMount: "always",
    retry: 2,
  });

  if (isLoading) {
    return <Shell loading />;
  }

  if (isError) {
    return <Shell error="Unable to load invoices" />;
  }

  const invoices = data ?? [];
  const outstanding = invoices.filter(
    (inv) => inv.status === "draft" || inv.status === "sent",
  );
  const paid = invoices.filter((inv) => inv.status === "paid");
  const overdue = outstanding.filter((inv) => {
    if (!inv.due_date) return false;
    return new Date(inv.due_date) < new Date();
  });

  const outstandingTotal = outstanding.reduce((s, i) => s + (i.total ?? 0), 0);
  const paidTotal = paid.reduce((s, i) => s + (i.total ?? 0), 0);

  return (
    <Shell>
      <div className="flex items-end justify-between gap-2">
        <div>
          <p className="text-2xl font-bold text-slate-900">
            {outstanding.length}
          </p>
          <p className="text-xs text-slate-500">outstanding invoices</p>
        </div>
        <div className="rounded-lg bg-emerald-50 p-2">
          <FileText className="h-4 w-4 text-emerald-600" />
        </div>
      </div>

      <div className="mt-3 space-y-1 border-t border-slate-100 pt-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-500">Outstanding</span>
          <span className="font-medium text-slate-700">
            {fmt(outstandingTotal)}
          </span>
        </div>
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-500">Paid</span>
          <span className="font-medium text-emerald-600">
            {fmt(paidTotal)}
          </span>
        </div>
        {overdue.length > 0 ? (
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-500">Overdue</span>
            <span className="font-medium text-rose-600">
              {overdue.length} invoice{overdue.length !== 1 ? "s" : ""}
            </span>
          </div>
        ) : null}
        {invoices.length === 0 ? (
          <p className="text-xs text-slate-400">No invoices yet.</p>
        ) : null}
      </div>
    </Shell>
  );
}

function Shell({
  loading,
  error,
  children,
}: {
  loading?: boolean;
  error?: string;
  children?: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-3 sm:p-4 md:p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          Invoices
        </h3>
        <Link
          href="/documents"
          className="inline-flex items-center gap-1 text-xs text-slate-400 transition hover:text-slate-600"
        >
          View
          <ArrowUpRight className="h-3 w-3" />
        </Link>
      </div>
      {loading ? (
        <div className="flex h-24 items-center justify-center text-xs text-slate-400">
          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
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
