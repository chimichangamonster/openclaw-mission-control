/* eslint-disable @typescript-eslint/no-explicit-any */
import { customFetch } from "@/api/mutator";

export interface VectorMemory {
  id: string;
  content: string;
  source: string;
  agent_id: string | null;
  created_at: string | null;
  expires_at: string | null;
}

export interface VectorMemorySearchResult {
  id: string;
  content: string;
  source: string;
  agent_id: string | null;
  similarity: number;
  extra: Record<string, unknown>;
  created_at: string;
}

export interface VectorMemoryListResponse {
  items: VectorMemory[];
  total: number;
  limit: number;
  offset: number;
}

export interface VectorMemoryStats {
  total_memories: number;
  sources: { source: string; count: number }[];
}

export async function listVectorMemories(params?: {
  source?: string;
  limit?: number;
  offset?: number;
}): Promise<VectorMemoryListResponse> {
  const query = new URLSearchParams();
  if (params?.source) query.set("source", params.source);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset !== undefined) query.set("offset", String(params.offset));
  const qs = query.toString();
  const res: any = await customFetch(
    `/api/v1/memory/vector${qs ? `?${qs}` : ""}`,
    { method: "GET" },
  );
  return res?.data ?? res;
}

export async function searchVectorMemories(
  queryText: string,
  limit = 10,
  sourceFilter?: string,
): Promise<VectorMemorySearchResult[]> {
  const body: Record<string, unknown> = { query: queryText, limit };
  if (sourceFilter) body.source_filter = sourceFilter;
  const res: any = await customFetch("/api/v1/memory/vector/search", {
    method: "POST",
    body: JSON.stringify(body),
  });
  return res?.data ?? res;
}

export async function deleteVectorMemory(id: string): Promise<void> {
  await customFetch(`/api/v1/memory/vector/${id}`, { method: "DELETE" });
}

export async function getVectorMemoryStats(): Promise<VectorMemoryStats> {
  const res: any = await customFetch("/api/v1/memory/vector/stats", {
    method: "GET",
  });
  return res?.data ?? res;
}
