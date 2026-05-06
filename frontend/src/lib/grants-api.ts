/**
 * Grants tracker API helpers (item 107 v2 Phase 2).
 *
 * Mirrors the regulatory-api.ts shape — same `customFetch` envelope unwrap
 * pattern, same Read/Create/Update split per entity, plus a nested
 * `GrantReadDetail` for the detail-drawer endpoint.
 *
 * Backend gates: `grants_tracker` feature flag (see
 * `app/api/grants.py:79`). Read endpoints require member+; mutations
 * require operator+ (grant create/edit, draws, deadlines, prerequisites);
 * grant DELETE requires admin+.
 *
 * Determinism posture per `feedback_determinism_first_for_high_liability.md`:
 * zero LLM in path. All amounts/dates/statuses operator-typed.
 */

import { customFetch } from "@/api/mutator";

const V1 = "/api/v1";

// ---------------------------------------------------------------------------
// Types — mirror app/schemas/grants.py
//
// NOTE: Decimal fields arrive as strings from FastAPI/Pydantic JSON
// serialization. Page-side parsing uses `Number(field ?? "0")` for sums
// and treats null as 0. Keep this contract stable — backend tests lock the
// string shape.
// ---------------------------------------------------------------------------

export interface Grant {
  id: string;
  organization_id: string;
  granting_body: string;
  program_name: string;
  application_template_slug: string | null;
  application_status: string;
  submitted_at: string | null;
  decision_at: string | null;
  awarded_amount: string | null;
  matched_funding_amount: string | null;
  total_project_value: string | null;
  currency: string;
  project_start_date: string | null;
  project_end_date: string | null;
  incorporation_required_entity: string | null;
  cash_coinvestment_required_pct: string | null;
  cash_coinvestment_source: string | null;
  contact_person: string | null;
  contact_email: string | null;
  owner_user_id: string | null;
  program_url: string | null;
  notes_md: string | null;
  created_at: string;
  updated_at: string;
}

export interface GrantDraw {
  id: string;
  grant_id: string;
  milestone_label: string;
  target_date: string | null;
  target_amount: string;
  drawn_at: string | null;
  drawn_amount: string | null;
  status: string;
  sort_order: number;
  notes_md: string | null;
  created_at: string;
  updated_at: string;
}

export interface GrantDeadline {
  id: string;
  grant_id: string;
  deadline_date: string;
  deadline_type: string;
  description: string | null;
  status: string;
  submitted_at: string | null;
  submitted_artifact_url: string | null;
  sort_order: number;
  notes_md: string | null;
  created_at: string;
  updated_at: string;
}

export interface GrantPrerequisite {
  grant_id: string;
  regulatory_task_id: string;
  label_override: string | null;
  is_critical: boolean;
  created_at: string;
  task_body: string | null;
  task_completed: boolean | null;
}

export interface GrantPrerequisiteStatus {
  total: number;
  complete: number;
  blocking_critical: number;
  percent: number;
}

export interface GrantDetail extends Grant {
  draws: GrantDraw[];
  deadlines: GrantDeadline[];
  prerequisites: GrantPrerequisite[];
}

export interface GrantCreate {
  granting_body: string;
  program_name: string;
  application_template_slug?: string | null;
  application_status?: string;
  submitted_at?: string | null;
  decision_at?: string | null;
  awarded_amount?: string | null;
  matched_funding_amount?: string | null;
  total_project_value?: string | null;
  currency?: string;
  project_start_date?: string | null;
  project_end_date?: string | null;
  incorporation_required_entity?: string | null;
  cash_coinvestment_required_pct?: string | null;
  cash_coinvestment_source?: string | null;
  contact_person?: string | null;
  contact_email?: string | null;
  owner_user_id?: string | null;
  program_url?: string | null;
  notes_md?: string | null;
}

export interface GrantUpdate {
  granting_body?: string;
  program_name?: string;
  application_template_slug?: string | null;
  application_status?: string;
  submitted_at?: string | null;
  decision_at?: string | null;
  awarded_amount?: string | null;
  matched_funding_amount?: string | null;
  total_project_value?: string | null;
  currency?: string;
  project_start_date?: string | null;
  project_end_date?: string | null;
  incorporation_required_entity?: string | null;
  cash_coinvestment_required_pct?: string | null;
  cash_coinvestment_source?: string | null;
  contact_person?: string | null;
  contact_email?: string | null;
  owner_user_id?: string | null;
  program_url?: string | null;
  notes_md?: string | null;
}

export interface GrantDrawCreate {
  milestone_label: string;
  target_date?: string | null;
  target_amount: string;
  drawn_at?: string | null;
  drawn_amount?: string | null;
  status?: string;
  sort_order?: number;
  notes_md?: string | null;
}

export interface GrantDrawUpdate {
  milestone_label?: string;
  target_date?: string | null;
  target_amount?: string;
  drawn_at?: string | null;
  drawn_amount?: string | null;
  status?: string;
  sort_order?: number;
  notes_md?: string | null;
}

export interface GrantDeadlineCreate {
  deadline_date: string;
  deadline_type?: string;
  description?: string | null;
  status?: string;
  submitted_at?: string | null;
  submitted_artifact_url?: string | null;
  sort_order?: number;
  notes_md?: string | null;
}

export interface GrantDeadlineUpdate {
  deadline_date?: string;
  deadline_type?: string;
  description?: string | null;
  status?: string;
  submitted_at?: string | null;
  submitted_artifact_url?: string | null;
  sort_order?: number;
  notes_md?: string | null;
}

export interface GrantPrerequisiteCreate {
  regulatory_task_id: string;
  label_override?: string | null;
  is_critical?: boolean;
}

// ---------------------------------------------------------------------------
// Internal — unwrap customFetch's {data, status, headers} envelope
// ---------------------------------------------------------------------------

const unwrap = <T,>(res: unknown): T => {
  if (res && typeof res === "object" && "data" in (res as Record<string, unknown>)) {
    return (res as { data: T }).data;
  }
  return res as T;
};

const jsonHeaders = { "Content-Type": "application/json" } as const;

// ---------------------------------------------------------------------------
// Grant CRUD
// ---------------------------------------------------------------------------

export async function listGrants(): Promise<Grant[]> {
  const res = await customFetch(`${V1}/grants`, { method: "GET" });
  return unwrap<Grant[]>(res);
}

export async function getGrantDetail(grantId: string): Promise<GrantDetail> {
  const res = await customFetch(`${V1}/grants/${grantId}`, { method: "GET" });
  return unwrap<GrantDetail>(res);
}

export async function createGrant(payload: GrantCreate): Promise<Grant> {
  const res = await customFetch(`${V1}/grants`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
  return unwrap<Grant>(res);
}

export async function updateGrant(
  grantId: string,
  payload: GrantUpdate,
): Promise<Grant> {
  const res = await customFetch(`${V1}/grants/${grantId}`, {
    method: "PATCH",
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
  return unwrap<Grant>(res);
}

export async function deleteGrant(grantId: string): Promise<void> {
  await customFetch(`${V1}/grants/${grantId}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Draw schedule (operator+)
// ---------------------------------------------------------------------------

export async function createDraw(
  grantId: string,
  payload: GrantDrawCreate,
): Promise<GrantDraw> {
  const res = await customFetch(`${V1}/grants/${grantId}/draws`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
  return unwrap<GrantDraw>(res);
}

export async function updateDraw(
  drawId: string,
  payload: GrantDrawUpdate,
): Promise<GrantDraw> {
  const res = await customFetch(`${V1}/grants/draws/${drawId}`, {
    method: "PATCH",
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
  return unwrap<GrantDraw>(res);
}

export async function deleteDraw(drawId: string): Promise<void> {
  await customFetch(`${V1}/grants/draws/${drawId}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Reporting deadlines (operator+)
// ---------------------------------------------------------------------------

export async function createDeadline(
  grantId: string,
  payload: GrantDeadlineCreate,
): Promise<GrantDeadline> {
  const res = await customFetch(`${V1}/grants/${grantId}/deadlines`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
  return unwrap<GrantDeadline>(res);
}

export async function updateDeadline(
  deadlineId: string,
  payload: GrantDeadlineUpdate,
): Promise<GrantDeadline> {
  const res = await customFetch(`${V1}/grants/deadlines/${deadlineId}`, {
    method: "PATCH",
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
  return unwrap<GrantDeadline>(res);
}

export async function deleteDeadline(deadlineId: string): Promise<void> {
  await customFetch(`${V1}/grants/deadlines/${deadlineId}`, {
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// Prerequisites — M2M to RegulatoryTask (operator+)
// ---------------------------------------------------------------------------

export async function addPrerequisite(
  grantId: string,
  payload: GrantPrerequisiteCreate,
): Promise<GrantPrerequisite> {
  const res = await customFetch(`${V1}/grants/${grantId}/prerequisites`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });
  return unwrap<GrantPrerequisite>(res);
}

export async function removePrerequisite(
  grantId: string,
  taskId: string,
): Promise<void> {
  await customFetch(`${V1}/grants/${grantId}/prerequisites/${taskId}`, {
    method: "DELETE",
  });
}

export async function getPrerequisiteStatus(
  grantId: string,
): Promise<GrantPrerequisiteStatus> {
  const res = await customFetch(
    `${V1}/grants/${grantId}/prerequisites/status`,
    { method: "GET" },
  );
  return unwrap<GrantPrerequisiteStatus>(res);
}
