/**
 * Org-Context Files API helpers (Phase 1).
 *
 * Wraps the /org-context endpoints. All endpoints are gated by the
 * org_context feature flag on the backend; mutating endpoints additionally
 * require admin role. Callers here assume the caller has already passed
 * those gates (FeatureGate + admin guard at the page level).
 */

import { customFetch } from "@/api/mutator";

const V1 = "/api/v1";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Visibility = "shared" | "private";

/** Suggested categories — frontend-enforced. The backend stores any string
 *  so future verticals can add new categories without a migration. */
export const CATEGORIES = [
  "customers",
  "pricing",
  "regulations",
  "brand",
  "contracts",
  "deployments",
  "prospects",
  "rules-of-engagement",
  "other",
] as const;

export type Category = (typeof CATEGORIES)[number];

/** Categories that run at MODERATE redaction (PII like phone/email is signal,
 *  not a leak). The set MUST stay in sync with `_CATEGORY_REDACTION_LEVEL` in
 *  app/api/org_context.py — surfacing this to the user prevents the
 *  surprise-redaction class of support tickets. */
export const MODERATE_CATEGORIES: ReadonlySet<string> = new Set([
  "customers",
  "pricing",
  "deployments",
  "prospects",
]);

export interface OrgContextFile {
  id: string;
  filename: string;
  category: string;
  content_type: string;
  source: string | null;
  visibility: Visibility;
  is_living_data: boolean;
  uploaded_at: string;
  last_updated: string;
  has_embedding: boolean;
  age_days: number;
}

export interface OrgContextFileDetail extends OrgContextFile {
  extracted_text: string | null;
}

export interface OrgContextStats {
  total: number;
  by_category: { category: string; count: number }[];
}

export interface UploadOptions {
  category: string;
  source?: string | null;
  visibility?: Visibility;
  is_living_data?: boolean;
}

// ---------------------------------------------------------------------------
// CRUD
// ---------------------------------------------------------------------------

export async function listFiles(category?: string): Promise<OrgContextFile[]> {
  const qs = category ? `?category=${encodeURIComponent(category)}` : "";
  const res = (await customFetch(`${V1}/org-context${qs}`, {
    method: "GET",
  })) as { data?: OrgContextFile[] } | OrgContextFile[];
  if (Array.isArray(res)) return res;
  return res.data ?? [];
}

export async function getStats(): Promise<OrgContextStats> {
  const res = (await customFetch(`${V1}/org-context/stats`, {
    method: "GET",
  })) as { data?: OrgContextStats } | OrgContextStats;
  return ((res as { data?: OrgContextStats }).data ??
    res) as OrgContextStats;
}

export async function getFile(id: string): Promise<OrgContextFileDetail> {
  const res = (await customFetch(`${V1}/org-context/${id}`, {
    method: "GET",
  })) as { data?: OrgContextFileDetail } | OrgContextFileDetail;
  return ((res as { data?: OrgContextFileDetail }).data ??
    res) as OrgContextFileDetail;
}

export async function patchFile(
  id: string,
  updates: Partial<{
    category: string;
    source: string | null;
    visibility: Visibility;
    is_living_data: boolean;
  }>
): Promise<OrgContextFile> {
  const res = (await customFetch(`${V1}/org-context/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  })) as { data?: OrgContextFile } | OrgContextFile;
  return ((res as { data?: OrgContextFile }).data ?? res) as OrgContextFile;
}

export async function deleteFile(id: string): Promise<void> {
  await customFetch(`${V1}/org-context/${id}`, { method: "DELETE" });
}

/**
 * Upload a file (multipart). customFetch forces JSON Content-Type, so we
 * hand-roll the fetch with auth headers — same pattern as the bookkeeping
 * statement upload helper.
 */
export async function uploadFile(
  file: File,
  options: UploadOptions
): Promise<OrgContextFile> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || "";
  const url = `${baseUrl}${V1}/org-context`;
  const formData = new FormData();
  formData.append("file", file);
  formData.append("category", options.category);
  if (options.source) formData.append("source", options.source);
  if (options.visibility) formData.append("visibility", options.visibility);
  formData.append(
    "is_living_data",
    options.is_living_data === false ? "false" : "true"
  );

  const headers: Record<string, string> = {};
  const localToken =
    typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;
  if (localToken) {
    headers["Authorization"] = `Bearer ${localToken}`;
  } else {
    const clerk = (
      window as unknown as {
        Clerk?: { session?: { getToken: () => Promise<string> } };
      }
    ).Clerk;
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
    const err = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(err.detail || `Upload failed (${res.status})`);
  }
  return (await res.json()) as OrgContextFile;
}
