/**
 * Ecosystem-intel API helpers — list trending repos, refresh feed, status.
 */

import { customFetch } from "@/api/mutator";

const V1 = "/api/v1";

type FetchEnvelope<T> = T | { data: T };

function unwrap<T>(res: FetchEnvelope<T>): T {
  if (res && typeof res === "object" && "data" in res) {
    return (res as { data: T }).data;
  }
  return res as T;
}

export type EcosystemCategory =
  | "all"
  | "ai_ml"
  | "swe"
  | "skills_ecosystem"
  | "trending";

export type EcosystemSort = "stars" | "forks" | "growth_24h";

export interface EcosystemRepo {
  id: string;
  full_name: string;
  owner: string;
  name: string;
  description: string | null;
  html_url: string;
  language: string | null;
  category: string;
  stars: number;
  forks: number;
  open_issues: number;
  topics: string[];
  pushed_at: string | null;
  repo_created_at: string | null;
  first_seen_at: string;
  last_synced_at: string;
  growth_24h: number;
}

export interface EcosystemStatus {
  repo_count: number;
  last_synced_at: string | null;
  has_token: boolean;
}

export interface EcosystemRefreshResult {
  fetched: number;
  upserted: number;
  snapshots: number;
  started_at: string;
  finished_at: string;
  error: string | null;
}

export async function listEcosystemRepos(opts: {
  category?: EcosystemCategory;
  sort?: EcosystemSort;
  search?: string;
  limit?: number;
} = {}): Promise<EcosystemRepo[]> {
  const params = new URLSearchParams();
  if (opts.category) params.set("category", opts.category);
  if (opts.sort) params.set("sort", opts.sort);
  if (opts.search) params.set("search", opts.search);
  if (opts.limit) params.set("limit", String(opts.limit));
  const qs = params.toString() ? `?${params.toString()}` : "";
  const res = (await customFetch(`${V1}/ecosystem-intel${qs}`, {
    method: "GET",
  })) as FetchEnvelope<EcosystemRepo[]>;
  const data = unwrap(res);
  return Array.isArray(data) ? data : [];
}

export async function getEcosystemStatus(): Promise<EcosystemStatus> {
  const res = (await customFetch(`${V1}/ecosystem-intel/status`, {
    method: "GET",
  })) as FetchEnvelope<EcosystemStatus>;
  return unwrap(res);
}

export async function refreshEcosystem(): Promise<EcosystemRefreshResult> {
  const res = (await customFetch(`${V1}/ecosystem-intel/refresh`, {
    method: "POST",
  })) as FetchEnvelope<EcosystemRefreshResult>;
  return unwrap(res);
}
