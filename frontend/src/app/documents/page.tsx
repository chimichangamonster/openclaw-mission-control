"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import { Download, FileText, RefreshCw, Trash2 } from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Button } from "@/components/ui/button";
import { customFetch } from "@/api/mutator";
import { cn } from "@/lib/utils";

interface Invoice {
  id: string;
  client_id: string;
  client_name: string;
  invoice_number: string | null;
  status: string;
  subtotal: string;
  gst_amount: string;
  total: string;
  issued_date: string | null;
  due_date: string | null;
  notes: string | null;
  created_at: string;
}

interface GeneratedDoc {
  id: string;
  filename: string;
  title: string;
  doc_type: string;
  mode: string;
  engine: string;
  file_size: number;
  mime_type: string;
  download_url: string;
  onedrive_url: string | null;
  onedrive_edit_url: string | null;
  created_at: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("mc_local_auth_token") || "";
}

async function fetchInvoices(): Promise<Invoice[]> {
  const res: any = await customFetch("/api/v1/invoices", { method: "GET" });
  const data = res?.data ?? res;
  return Array.isArray(data) ? data : [];
}

async function fetchGeneratedDocs(): Promise<GeneratedDoc[]> {
  const res: any = await customFetch("/api/v1/documents/generated", { method: "GET" });
  const data = res?.data ?? res;
  return Array.isArray(data) ? data : [];
}

function getPdfUrl(invoiceId: string): string {
  const token = getToken();
  return `${API_URL}/api/v1/invoices/${invoiceId}/pdf?token=${token}&company_name=Vantage+Solutions&company_email=info@vantagesolutions.ca`;
}

function statusBadge(status: string) {
  const colors: Record<string, string> = {
    draft: "bg-slate-100 text-slate-700",
    sent: "bg-blue-100 text-blue-700",
    paid: "bg-green-100 text-green-700",
    overdue: "bg-red-100 text-red-700",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize",
        colors[status] || "bg-slate-100 text-slate-700",
      )}
    >
      {status}
    </span>
  );
}

function docTypeBadge(docType: string) {
  const colors: Record<string, string> = {
    proposal: "bg-purple-100 text-purple-700",
    report: "bg-blue-100 text-blue-700",
    "security-assessment": "bg-red-100 text-red-700",
    "rules-of-engagement": "bg-amber-100 text-amber-700",
    invoice: "bg-green-100 text-green-700",
    other: "bg-slate-100 text-slate-700",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize",
        colors[docType] || "bg-slate-100 text-slate-700",
      )}
    >
      {docType.replace(/-/g, " ")}
    </span>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentsPage() {
  const { isSignedIn } = useAuth();
  const [tab, setTab] = useState<"invoices" | "generated">("invoices");
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [generatedDocs, setGeneratedDocs] = useState<GeneratedDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadInvoices = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchInvoices();
      setInvoices(data);
    } catch (e: any) {
      setError(e?.message || "Failed to load invoices");
      setInvoices([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadGeneratedDocs = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchGeneratedDocs();
      setGeneratedDocs(data);
    } catch (e: any) {
      setError(e?.message || "Failed to load documents");
      setGeneratedDocs([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const deleteDoc = useCallback(async (id: string) => {
    try {
      await customFetch(`/api/v1/documents/generated/${id}`, { method: "DELETE" });
      setGeneratedDocs((prev) => prev.filter((d) => d.id !== id));
    } catch (e: any) {
      setError(e?.message || "Failed to delete document");
    }
  }, []);

  useEffect(() => {
    if (!isSignedIn) return;
    if (tab === "invoices") {
      loadInvoices();
    } else {
      loadGeneratedDocs();
    }
  }, [isSignedIn, tab, loadInvoices, loadGeneratedDocs]);

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to view documents.",
        forceRedirectUrl: "/documents",
        signUpForceRedirectUrl: "/documents",
      }}
      title="Documents"
      description="Invoices, reports, and generated files."
    >
      <div className="space-y-4">
        {/* Tabs */}
        <div className="flex items-center gap-1 border-b border-slate-200">
          <button
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 transition",
              tab === "invoices"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-slate-500 hover:text-slate-700",
            )}
            onClick={() => setTab("invoices")}
          >
            Invoices
          </button>
          <button
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 transition",
              tab === "generated"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-slate-500 hover:text-slate-700",
            )}
            onClick={() => setTab("generated")}
          >
            Generated Documents
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Invoices Tab */}
        {tab === "invoices" && (
          <>
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-slate-800">Invoices</h2>
              <Button variant="outline" size="sm" onClick={loadInvoices} disabled={loading}>
                <RefreshCw className={cn("mr-2 h-4 w-4", loading && "animate-spin")} />
                Refresh
              </Button>
            </div>

            {loading && invoices.length === 0 ? (
              <div className="flex items-center justify-center py-12 text-slate-500">
                Loading invoices...
              </div>
            ) : invoices.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-slate-500">
                <FileText className="mb-3 h-10 w-10 text-slate-300" />
                <p>No invoices yet</p>
                <p className="mt-1 text-xs">
                  Ask The Claw to create an invoice and it will appear here.
                </p>
              </div>
            ) : (
              <div className="overflow-hidden rounded-lg border border-slate-200">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                      <th className="px-4 py-3">Invoice</th>
                      <th className="px-4 py-3">Client</th>
                      <th className="px-4 py-3 text-right">Total</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Due Date</th>
                      <th className="px-4 py-3 text-right">PDF</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {invoices.map((inv) => (
                      <tr key={inv.id} className="hover:bg-slate-50 transition">
                        <td className="px-4 py-3 font-medium text-slate-800">
                          {inv.invoice_number || `#${inv.id.slice(0, 8)}`}
                        </td>
                        <td className="px-4 py-3 text-slate-600">{inv.client_name || "—"}</td>
                        <td className="px-4 py-3 text-right font-medium text-slate-800">
                          ${parseFloat(inv.total).toLocaleString("en-CA", { minimumFractionDigits: 2 })}
                        </td>
                        <td className="px-4 py-3">{statusBadge(inv.status)}</td>
                        <td className="px-4 py-3 text-slate-600">
                          {inv.due_date ? new Date(inv.due_date).toLocaleDateString("en-CA") : "—"}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <a
                            href={getPdfUrl(inv.id)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1.5 rounded-lg bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-100 transition"
                          >
                            <Download className="h-3.5 w-3.5" />
                            PDF
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {/* Generated Documents Tab */}
        {tab === "generated" && (
          <>
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-slate-800">Generated Documents</h2>
              <Button variant="outline" size="sm" onClick={loadGeneratedDocs} disabled={loading}>
                <RefreshCw className={cn("mr-2 h-4 w-4", loading && "animate-spin")} />
                Refresh
              </Button>
            </div>

            {loading && generatedDocs.length === 0 ? (
              <div className="flex items-center justify-center py-12 text-slate-500">
                Loading documents...
              </div>
            ) : generatedDocs.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-slate-500">
                <FileText className="mb-3 h-10 w-10 text-slate-300" />
                <p>No generated documents yet</p>
                <p className="mt-1 text-xs">
                  Documents created via doc-gen (proposals, reports, assessments) will appear here.
                </p>
              </div>
            ) : (
              <div className="overflow-hidden rounded-lg border border-slate-200">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                      <th className="px-4 py-3">Title</th>
                      <th className="px-4 py-3">Type</th>
                      <th className="px-4 py-3">Engine</th>
                      <th className="px-4 py-3 text-right">Size</th>
                      <th className="px-4 py-3">Created</th>
                      <th className="px-4 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {generatedDocs.map((doc) => (
                      <tr key={doc.id} className="hover:bg-slate-50 transition">
                        <td className="px-4 py-3">
                          <div className="font-medium text-slate-800">{doc.title || doc.filename}</div>
                          <div className="text-xs text-slate-400">{doc.filename}</div>
                        </td>
                        <td className="px-4 py-3">{docTypeBadge(doc.doc_type)}</td>
                        <td className="px-4 py-3 text-slate-600 text-xs">{doc.engine.replace(/_/g, " ")}</td>
                        <td className="px-4 py-3 text-right text-slate-600">{formatFileSize(doc.file_size)}</td>
                        <td className="px-4 py-3 text-slate-600">
                          {new Date(doc.created_at).toLocaleDateString("en-CA")}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center justify-end gap-2">
                            {doc.download_url && (
                              <a
                                href={doc.download_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1.5 rounded-lg bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-100 transition"
                              >
                                <Download className="h-3.5 w-3.5" />
                                Download
                              </a>
                            )}
                            <button
                              onClick={() => deleteDoc(doc.id)}
                              className="inline-flex items-center gap-1 rounded-lg bg-red-50 px-2 py-1.5 text-xs font-medium text-red-600 hover:bg-red-100 transition"
                              title="Delete"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </DashboardPageLayout>
  );
}
