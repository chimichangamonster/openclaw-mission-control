/**
 * Personal bookkeeping (sole-prop) API helpers.
 *
 * Wraps the /personal-bookkeeping endpoints shipped in Session 2.
 * All endpoints are gated by personal_bookkeeping feature flag + personal org slug
 * on the backend — callers here assume the caller has already passed those gates.
 */

import { customFetch } from "@/api/mutator";

const V1 = "/api/v1";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Bucket =
  | "business"
  | "personal"
  | "vehicle"
  | "gift"
  | "transfer"
  | "ambiguous"
  | "income_pending";

export type Source = "TD" | "AMEX";
export type MonthStatus = "draft" | "reviewed" | "locked";

export const BUCKETS: Bucket[] = [
  "business",
  "personal",
  "vehicle",
  "gift",
  "transfer",
  "ambiguous",
  "income_pending",
];

export const BUCKET_LABELS: Record<Bucket, string> = {
  business: "Business",
  personal: "Personal",
  vehicle: "Vehicle",
  gift: "Gift",
  transfer: "Transfer",
  ambiguous: "Ambiguous",
  income_pending: "Income pending",
};

export const BUCKET_COLORS: Record<Bucket, string> = {
  business: "bg-emerald-100 text-emerald-700 border-emerald-200",
  personal: "bg-slate-100 text-slate-700 border-slate-200",
  vehicle: "bg-amber-100 text-amber-700 border-amber-200",
  gift: "bg-pink-100 text-pink-700 border-pink-200",
  transfer: "bg-blue-100 text-blue-700 border-blue-200",
  ambiguous: "bg-red-100 text-red-700 border-red-200",
  income_pending: "bg-orange-100 text-orange-700 border-orange-200",
};

export interface ReconciliationMonth {
  id: string;
  period: string;
  status: MonthStatus;
  td_line_count: number;
  amex_line_count: number;
  business_income: number;
  business_expenses: number;
  vehicle_expenses: number;
  gst_collected_informational: number;
  gst_paid_informational: number;
  flagged_line_count: number;
  locked_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface StatementFile {
  id: string;
  reconciliation_month_id: string | null;
  period: string;
  source: Source;
  original_filename: string;
  content_type: string;
  sha256: string;
  byte_size: number;
  local_path: string | null;
  retention_until: string;
  uploaded_at: string;
}

export interface StatementImportResult {
  statement_file_id: string;
  inserted_count: number;
  skipped_count: number;
  classification_summary: Record<string, number>;
}

export interface BulkImportPeriodResult {
  period: string;
  inserted_count: number;
  skipped_count: number;
  classification_summary: Record<string, number>;
  month_status: MonthStatus;
  month_locked_and_skipped: boolean;
}

export interface BulkImportResult {
  statement_file_id: string;
  source: Source;
  total_inserted: number;
  total_skipped: number;
  per_period: BulkImportPeriodResult[];
}

export interface Transaction {
  id: string;
  reconciliation_month_id: string;
  statement_file_id: string | null;
  source: Source;
  txn_date: string;
  description: string;
  amount: number;
  incoming: boolean;
  bucket: Bucket;
  t2125_line: string | null;
  category: string | null;
  needs_receipt: boolean;
  receipt_filed: boolean;
  user_note: string | null;
  classified_by: "auto" | "user";
  classified_at: string;
  original_row_hash: string;
}

export interface TransactionUpdate {
  bucket?: Bucket;
  t2125_line?: string | null;
  category?: string | null;
  needs_receipt?: boolean;
  receipt_filed?: boolean;
  user_note?: string | null;
}

export interface VendorRule {
  id: string;
  pattern: string;
  bucket: Bucket;
  t2125_line: string | null;
  category: string | null;
  needs_receipt: boolean;
  note: string | null;
  applies_to_source: Source | null;
  source_month: string;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface VendorRuleCreate {
  pattern: string;
  bucket: Bucket;
  t2125_line?: string | null;
  category?: string | null;
  needs_receipt?: boolean;
  note?: string | null;
  applies_to_source?: Source | null;
}

export interface VendorRuleUpdate {
  pattern?: string;
  bucket?: Bucket;
  t2125_line?: string | null;
  category?: string | null;
  needs_receipt?: boolean;
  note?: string | null;
  applies_to_source?: Source | null;
  active?: boolean;
}

// ---------------------------------------------------------------------------
// Month picker helpers
// ---------------------------------------------------------------------------

/** Current period in YYYY-MM local time. */
export function currentPeriod(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

/** Previous month (default picker value per monthly cadence feedback). */
export function lastMonthPeriod(): string {
  const now = new Date();
  now.setDate(1);
  now.setMonth(now.getMonth() - 1);
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

/** Enumerate periods back N months from given anchor (inclusive). */
export function periodsBack(anchor: string, count: number): string[] {
  const [y, m] = anchor.split("-").map(Number);
  const out: string[] = [];
  for (let i = 0; i < count; i++) {
    const d = new Date(y, m - 1 - i, 1);
    out.push(
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`
    );
  }
  return out;
}

// ---------------------------------------------------------------------------
// Source auto-detection by filename
// ---------------------------------------------------------------------------

/**
 * Detect TD vs AMEX by filename. TD EasyWeb exports CSVs named
 * "accountactivity.csv"; AMEX Cobalt exports are "Summary.xls". The OS may
 * append " (1)", " (2)", etc. for duplicates — still matches.
 * Returns null if filename doesn't match either pattern (user must pick).
 */
export function detectSource(file: File): Source | null {
  const name = file.name.toLowerCase();
  if (name.startsWith("accountactivity")) return "TD";
  if (name.startsWith("summary")) return "AMEX";
  return null;
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

export async function listMonths(): Promise<ReconciliationMonth[]> {
  const res: unknown = await customFetch(`${V1}/personal-bookkeeping/months`, {
    method: "GET",
  });
  const data = (res as { data?: ReconciliationMonth[] })?.data;
  return Array.isArray(data) ? data : Array.isArray(res) ? (res as ReconciliationMonth[]) : [];
}

export async function getMonth(period: string): Promise<ReconciliationMonth | null> {
  try {
    const res: unknown = await customFetch(
      `${V1}/personal-bookkeeping/months/${period}`,
      { method: "GET" }
    );
    const data = (res as { data?: ReconciliationMonth })?.data;
    return (data ?? (res as ReconciliationMonth)) || null;
  } catch (e: unknown) {
    if ((e as { status?: number })?.status === 404) return null;
    throw e;
  }
}

export async function createMonth(period: string): Promise<ReconciliationMonth> {
  const res: unknown = await customFetch(`${V1}/personal-bookkeeping/months`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ period }),
  });
  return ((res as { data?: ReconciliationMonth })?.data ?? res) as ReconciliationMonth;
}

export async function lockMonth(period: string): Promise<ReconciliationMonth> {
  const res: unknown = await customFetch(
    `${V1}/personal-bookkeeping/months/${period}/lock`,
    { method: "POST" }
  );
  return ((res as { data?: ReconciliationMonth })?.data ?? res) as ReconciliationMonth;
}

export async function listStatements(period: string): Promise<StatementFile[]> {
  const res: unknown = await customFetch(
    `${V1}/personal-bookkeeping/months/${period}/statements`,
    { method: "GET" }
  );
  const data = (res as { data?: StatementFile[] })?.data;
  return Array.isArray(data) ? data : Array.isArray(res) ? (res as StatementFile[]) : [];
}

export async function updateStatement(
  statementId: string,
  payload: { local_path?: string | null }
): Promise<StatementFile> {
  const res: unknown = await customFetch(
    `${V1}/personal-bookkeeping/statements/${statementId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  return ((res as { data?: StatementFile })?.data ?? res) as StatementFile;
}

/**
 * Upload a statement file (multipart). customFetch forces JSON Content-Type,
 * so we hand-roll the fetch with auth headers (same pattern as chat upload).
 */
export async function uploadStatement(
  period: string,
  source: Source,
  file: File
): Promise<StatementImportResult> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || "";
  const url = `${baseUrl}${V1}/personal-bookkeeping/months/${period}/statements`;
  const formData = new FormData();
  formData.append("source", source);
  formData.append("file", file);

  const headers: Record<string, string> = {};
  const localToken = typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;
  if (localToken) {
    headers["Authorization"] = `Bearer ${localToken}`;
  } else {
    const clerk = (window as unknown as {
      Clerk?: { session?: { getToken: () => Promise<string> } };
    }).Clerk;
    if (clerk?.session) {
      try {
        headers["Authorization"] = `Bearer ${await clerk.session.getToken()}`;
      } catch {
        /* ignore */
      }
    }
  }

  const res = await fetch(url, { method: "POST", headers, body: formData });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error((err as { detail?: string }).detail || `Upload failed (${res.status})`);
  }
  return (await res.json()) as StatementImportResult;
}

/**
 * Bulk-import: one file whose rows may span multiple months. Groups by period,
 * creates missing draft months, reports per-period results. Use for "I forgot
 * to reconcile monthly" catch-up; the default workflow stays monthly.
 */
export async function bulkImportStatement(
  source: Source,
  file: File
): Promise<BulkImportResult> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || "";
  const url = `${baseUrl}${V1}/personal-bookkeeping/statements/bulk-import`;
  const formData = new FormData();
  formData.append("source", source);
  formData.append("file", file);

  const headers: Record<string, string> = {};
  const localToken = typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;
  if (localToken) {
    headers["Authorization"] = `Bearer ${localToken}`;
  } else {
    const clerk = (window as unknown as {
      Clerk?: { session?: { getToken: () => Promise<string> } };
    }).Clerk;
    if (clerk?.session) {
      try {
        headers["Authorization"] = `Bearer ${await clerk.session.getToken()}`;
      } catch {
        /* ignore */
      }
    }
  }

  const res = await fetch(url, { method: "POST", headers, body: formData });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Bulk import failed" }));
    throw new Error(
      (err as { detail?: string }).detail || `Bulk import failed (${res.status})`
    );
  }
  return (await res.json()) as BulkImportResult;
}

export async function listTransactions(
  period: string,
  filters?: { bucket?: Bucket; source?: Source; needs_receipt?: boolean }
): Promise<Transaction[]> {
  const params = new URLSearchParams();
  if (filters?.bucket) params.set("bucket", filters.bucket);
  if (filters?.source) params.set("source", filters.source);
  if (filters?.needs_receipt !== undefined)
    params.set("needs_receipt", String(filters.needs_receipt));
  const qs = params.toString() ? `?${params}` : "";
  const res: unknown = await customFetch(
    `${V1}/personal-bookkeeping/months/${period}/transactions${qs}`,
    { method: "GET" }
  );
  const data = (res as { data?: Transaction[] })?.data;
  return Array.isArray(data) ? data : Array.isArray(res) ? (res as Transaction[]) : [];
}

export async function updateTransaction(
  txnId: string,
  payload: TransactionUpdate
): Promise<Transaction> {
  const res: unknown = await customFetch(
    `${V1}/personal-bookkeeping/transactions/${txnId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  return ((res as { data?: Transaction })?.data ?? res) as Transaction;
}

export async function promoteToRule(
  txnId: string,
  payload: { pattern?: string; applies_to_source?: Source | null } = {}
): Promise<VendorRule> {
  const res: unknown = await customFetch(
    `${V1}/personal-bookkeeping/transactions/${txnId}/promote-to-rule`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  return ((res as { data?: VendorRule })?.data ?? res) as VendorRule;
}

export async function listVendorRules(filters?: {
  active?: boolean;
  source_month?: string;
}): Promise<VendorRule[]> {
  const params = new URLSearchParams();
  if (filters?.active !== undefined) params.set("active", String(filters.active));
  if (filters?.source_month) params.set("source_month", filters.source_month);
  const qs = params.toString() ? `?${params}` : "";
  const res: unknown = await customFetch(
    `${V1}/personal-bookkeeping/vendor-rules${qs}`,
    { method: "GET" }
  );
  const data = (res as { data?: VendorRule[] })?.data;
  return Array.isArray(data) ? data : Array.isArray(res) ? (res as VendorRule[]) : [];
}

export async function createVendorRule(payload: VendorRuleCreate): Promise<VendorRule> {
  const res: unknown = await customFetch(`${V1}/personal-bookkeeping/vendor-rules`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return ((res as { data?: VendorRule })?.data ?? res) as VendorRule;
}

export async function updateVendorRule(
  ruleId: string,
  payload: VendorRuleUpdate
): Promise<VendorRule> {
  const res: unknown = await customFetch(
    `${V1}/personal-bookkeeping/vendor-rules/${ruleId}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  return ((res as { data?: VendorRule })?.data ?? res) as VendorRule;
}
