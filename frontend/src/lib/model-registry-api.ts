/**
 * Model registry API helpers — browse models, refresh, manage version pins.
 */

import { customFetch } from "@/api/mutator";

const V1 = "/api/v1";

// --- Types ---

export interface ModelEntry {
  model_id: string;
  family: string;
  provider: string;
  name: string;
  context_window: number;
  prompt_price_per_m: number;
  completion_price_per_m: number;
  tier: number;
  status: string; // "active", "deprecated", "removed"
  first_seen: number;
  last_seen: number;
}

export interface DeprecationWarning {
  pinned_model_id: string;
  pin_key: string;
  status: string;
  suggested_replacement: string | null;
}

export interface RegistryResponse {
  models: ModelEntry[];
  total: number;
  last_refresh: string | null;
  families: string[];
}

export interface RefreshResult {
  total_models: number;
  new_models: number;
  deprecated_models: number;
  refresh_time_ms: number;
}

export interface ModelPinsResponse {
  pins: Record<string, string>;
  warnings: DeprecationWarning[];
}

// --- API calls ---

export async function getModelRegistry(statusFilter?: string): Promise<RegistryResponse> {
  const params = statusFilter ? `?status_filter=${statusFilter}` : "";
  const res: any = await customFetch(`${V1}/models/registry${params}`, { method: "GET" });
  return res?.data ?? res;
}

export async function refreshModelRegistry(): Promise<RefreshResult> {
  const res: any = await customFetch(`${V1}/models/registry/refresh`, { method: "POST" });
  return res?.data ?? res;
}

export async function getModelVersions(family: string): Promise<{ family: string; versions: ModelEntry[] }> {
  const res: any = await customFetch(`${V1}/models/registry/${encodeURIComponent(family)}/versions`, { method: "GET" });
  return res?.data ?? res;
}

export async function getModelPins(): Promise<ModelPinsResponse> {
  const res: any = await customFetch(`${V1}/models/pins`, { method: "GET" });
  return res?.data ?? res;
}

export async function updateModelPins(pins: Record<string, string>): Promise<any> {
  const res: any = await customFetch(`${V1}/models/pins`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pins }),
  });
  return res?.data ?? res;
}
