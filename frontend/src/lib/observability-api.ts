/* eslint-disable @typescript-eslint/no-explicit-any */
import { customFetch } from "@/api/mutator";

export interface LangfuseTrace {
  id: string;
  name: string;
  timestamp: string;
  metadata?: Record<string, any>;
  observations?: LangfuseObservation[];
  scores?: LangfuseScore[];
}

export interface LangfuseObservation {
  id: string;
  name: string;
  type: string;
  startTime: string;
  endTime?: string;
  metadata?: Record<string, any>;
  level?: string;
  model?: string;
}

export interface LangfuseScore {
  id: string;
  traceId: string;
  name: string;
  value: number;
  comment?: string;
  timestamp: string;
}

export interface ObservabilityStatus {
  configured: boolean;
  host: string | null;
}

export interface TraceListResponse {
  data: LangfuseTrace[];
  meta?: { totalItems?: number; page?: number; totalPages?: number };
}

export interface ScoreListResponse {
  data: LangfuseScore[];
  meta?: { totalItems?: number; page?: number; totalPages?: number };
}

export async function getObservabilityStatus(): Promise<ObservabilityStatus> {
  const res: any = await customFetch("/api/v1/observability/status", {
    method: "GET",
  });
  return res?.data ?? res;
}

export async function listTraces(params?: {
  limit?: number;
  page?: number;
  name?: string;
}): Promise<TraceListResponse> {
  const query = new URLSearchParams();
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.page) query.set("page", String(params.page));
  if (params?.name) query.set("name", params.name);
  const qs = query.toString();
  const res: any = await customFetch(
    `/api/v1/observability/traces${qs ? `?${qs}` : ""}`,
    { method: "GET" },
  );
  return res?.data ?? res;
}

export async function getTrace(traceId: string): Promise<LangfuseTrace> {
  const res: any = await customFetch(
    `/api/v1/observability/traces/${traceId}`,
    { method: "GET" },
  );
  return res?.data ?? res;
}

export async function listScores(params?: {
  limit?: number;
  page?: number;
}): Promise<ScoreListResponse> {
  const query = new URLSearchParams();
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.page) query.set("page", String(params.page));
  const qs = query.toString();
  const res: any = await customFetch(
    `/api/v1/observability/scores${qs ? `?${qs}` : ""}`,
    { method: "GET" },
  );
  return res?.data ?? res;
}
