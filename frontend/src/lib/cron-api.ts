/**
 * Cron job API helpers for CRUD operations via gateway RPC.
 */

import { customFetch } from "@/api/mutator";

const V1 = "/api/v1";

// --- Types ---

export interface CronJob {
  id: string;
  name: string;
  description: string;
  agent_id: string;
  enabled: boolean;
  schedule_type: string;
  schedule_expr: string;
  timezone: string;
  message: string;
  thinking: string;
  timeout_seconds: number;
  session_target: string;
  announce: boolean;
  next_run: string | null;
  last_run: string | null;
  last_status: string | null;
  created_at: string;
}

export interface CronJobCreate {
  name: string;
  agent_id: string;
  schedule_type: "cron" | "every" | "at";
  schedule_expr: string;
  timezone?: string;
  message?: string;
  thinking?: string;
  timeout_seconds?: number;
  session_target?: string;
  announce?: boolean;
  enabled?: boolean;
  description?: string;
}

export interface CronJobUpdate {
  name?: string;
  agent_id?: string;
  schedule_type?: "cron" | "every" | "at";
  schedule_expr?: string;
  timezone?: string;
  message?: string;
  thinking?: string;
  timeout_seconds?: number;
  session_target?: string;
  announce?: boolean;
  enabled?: boolean;
  description?: string;
}

export interface CronRunRecord {
  run_id: string;
  job_id: string;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  error: string | null;
  duration_ms: number | null;
}

// --- API calls ---

export async function listCronJobs(): Promise<CronJob[]> {
  const res: any = await customFetch(`${V1}/cron-jobs`, { method: "GET" });
  const data = res?.data;
  return Array.isArray(data) ? data : Array.isArray(res) ? res : [];
}

export async function createCronJob(payload: CronJobCreate): Promise<any> {
  const res: any = await customFetch(`${V1}/cron-jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res?.data ?? res;
}

export async function updateCronJob(jobId: string, payload: CronJobUpdate): Promise<any> {
  const res: any = await customFetch(`${V1}/cron-jobs/${jobId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res?.data ?? res;
}

export async function deleteCronJob(jobId: string): Promise<void> {
  await customFetch(`${V1}/cron-jobs/${jobId}`, { method: "DELETE" });
}

export async function runCronJob(jobId: string): Promise<any> {
  const res: any = await customFetch(`${V1}/cron-jobs/${jobId}/run`, { method: "POST" });
  return res?.data ?? res;
}

export async function getCronJobRuns(jobId: string): Promise<CronRunRecord[]> {
  const res: any = await customFetch(`${V1}/cron-jobs/${jobId}/runs`, { method: "GET" });
  const data = res?.data;
  return Array.isArray(data) ? data : Array.isArray(res) ? res : [];
}
