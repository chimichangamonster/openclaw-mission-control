/**
 * Chat project API helpers — CRUD + session assignment.
 * Chat reorganization plan Tier 1.4.
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

export interface ChatProject {
  id: string;
  name: string;
  description: string | null;
  color: string | null;
  sort_order: number;
  archived: boolean;
  session_count: number;
  created_at: string;
  updated_at: string;
}

export interface ChatProjectCreate {
  name: string;
  description?: string | null;
  color?: string | null;
  sort_order?: number;
}

export interface ChatProjectUpdate {
  name?: string;
  description?: string | null;
  color?: string | null;
  sort_order?: number;
  archived?: boolean;
}

export async function listChatProjects(
  includeArchived = false,
): Promise<ChatProject[]> {
  const qs = includeArchived ? "?include_archived=true" : "";
  const res = (await customFetch(`${V1}/chat-projects${qs}`, {
    method: "GET",
  })) as FetchEnvelope<ChatProject[]>;
  const data = unwrap(res);
  return Array.isArray(data) ? data : [];
}

export async function createChatProject(
  payload: ChatProjectCreate,
): Promise<ChatProject> {
  const res = (await customFetch(`${V1}/chat-projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })) as FetchEnvelope<ChatProject>;
  return unwrap(res);
}

export async function updateChatProject(
  projectId: string,
  payload: ChatProjectUpdate,
): Promise<ChatProject> {
  const res = (await customFetch(`${V1}/chat-projects/${projectId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })) as FetchEnvelope<ChatProject>;
  return unwrap(res);
}

export async function deleteChatProject(projectId: string): Promise<void> {
  await customFetch(`${V1}/chat-projects/${projectId}`, { method: "DELETE" });
}

export async function listSessionAssignments(): Promise<Record<string, string>> {
  const res = (await customFetch(`${V1}/chat-projects/assignments`, {
    method: "GET",
  })) as FetchEnvelope<Record<string, string>>;
  const data = unwrap(res);
  return data && typeof data === "object" ? data : {};
}

export async function assignSessionToProject(
  sessionKey: string,
  projectId: string | null,
): Promise<void> {
  const encoded = encodeURIComponent(sessionKey);
  await customFetch(`${V1}/chat-projects/assignments/${encoded}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId }),
  });
}
