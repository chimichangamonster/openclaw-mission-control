/**
 * Manual email API helpers until Orval is regenerated.
 *
 * These call the email endpoints added to the backend.
 * After running `npx orval`, replace these with the auto-generated hooks.
 */

import { customFetch } from "@/api/mutator";

const V1 = "/api/v1";

// --- Types ---

export interface EmailAccount {
  id: string;
  organization_id: string;
  user_id: string;
  provider: "zoho" | "microsoft";
  email_address: string;
  display_name: string | null;
  sync_enabled: boolean;
  visibility: "shared" | "private";
  last_sync_at: string | null;
  last_sync_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmailMessage {
  id: string;
  organization_id: string;
  email_account_id: string;
  provider_message_id: string;
  thread_id: string | null;
  subject: string | null;
  sender_email: string;
  sender_name: string | null;
  recipients_to: { email: string; name: string }[];
  recipients_cc: { email: string; name: string }[] | null;
  body_text: string | null;
  body_html: string | null;
  received_at: string;
  is_read: boolean;
  is_starred: boolean;
  folder: string;
  labels: string[] | null;
  has_attachments: boolean;
  triage_status: string;
  triage_category: string | null;
  linked_task_id: string | null;
  synced_at: string;
  created_at: string;
}

// --- Account APIs ---

export async function fetchEmailAccounts(): Promise<EmailAccount[]> {
  const res = await customFetch<{ data: EmailAccount[] }>(
    `${V1}/email/accounts`,
    { method: "GET" },
  );
  return res.data;
}

export async function deleteEmailAccount(accountId: string): Promise<void> {
  await customFetch(`${V1}/email/accounts/${accountId}`, {
    method: "DELETE",
  });
}

export async function updateEmailAccount(
  accountId: string,
  data: { sync_enabled?: boolean; display_name?: string; visibility?: "shared" | "private" },
): Promise<EmailAccount> {
  const res = await customFetch<{ data: EmailAccount }>(
    `${V1}/email/accounts/${accountId}`,
    { method: "PATCH", body: JSON.stringify(data) },
  );
  return res.data;
}

export async function triggerEmailSync(
  accountId: string,
): Promise<{ ok: boolean; enqueued: boolean }> {
  const res = await customFetch<{
    data: { ok: boolean; enqueued: boolean };
  }>(`${V1}/email/accounts/${accountId}/sync`, { method: "POST" });
  return res.data;
}

export async function getOAuthUrl(
  provider: "zoho" | "microsoft",
): Promise<{ authorization_url: string }> {
  const res = await customFetch<{
    data: { authorization_url: string; state: string };
  }>(`${V1}/email/oauth/${provider}/authorize`, { method: "GET" });
  return res.data;
}

// --- Message APIs ---

export async function fetchEmailMessages(
  accountId: string,
  params?: {
    folder?: string;
    triage_status?: string;
    is_read?: boolean;
    limit?: number;
    offset?: number;
  },
): Promise<EmailMessage[]> {
  const searchParams = new URLSearchParams();
  if (params?.folder) searchParams.set("folder", params.folder);
  if (params?.triage_status)
    searchParams.set("triage_status", params.triage_status);
  if (params?.is_read !== undefined)
    searchParams.set("is_read", String(params.is_read));
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.offset) searchParams.set("offset", String(params.offset));

  const qs = searchParams.toString();
  const res = await customFetch<{ data: EmailMessage[] }>(
    `${V1}/email/accounts/${accountId}/messages${qs ? `?${qs}` : ""}`,
    { method: "GET" },
  );
  return res.data;
}

export async function fetchEmailMessage(
  accountId: string,
  messageId: string,
): Promise<EmailMessage> {
  const res = await customFetch<{ data: EmailMessage }>(
    `${V1}/email/accounts/${accountId}/messages/${messageId}`,
    { method: "GET" },
  );
  return res.data;
}

export async function updateEmailMessage(
  accountId: string,
  messageId: string,
  data: {
    is_read?: boolean;
    triage_status?: string;
    triage_category?: string;
    linked_task_id?: string;
  },
): Promise<EmailMessage> {
  const res = await customFetch<{ data: EmailMessage }>(
    `${V1}/email/accounts/${accountId}/messages/${messageId}`,
    { method: "PATCH", body: JSON.stringify(data) },
  );
  return res.data;
}

export async function replyToEmail(
  accountId: string,
  messageId: string,
  data: { body_text: string },
): Promise<void> {
  await customFetch(
    `${V1}/email/accounts/${accountId}/messages/${messageId}/reply`,
    { method: "POST", body: JSON.stringify(data) },
  );
}

// --- Attachment APIs ---

export interface EmailAttachment {
  id: string;
  email_message_id: string;
  filename: string;
  content_type: string | null;
  size_bytes: number | null;
  is_inline: boolean;
  created_at: string;
}

export async function fetchEmailAttachments(
  accountId: string,
  messageId: string,
): Promise<EmailAttachment[]> {
  const res = await customFetch<{ data: EmailAttachment[] }>(
    `${V1}/email/accounts/${accountId}/messages/${messageId}/attachments`,
    { method: "GET" },
  );
  return res.data;
}

async function _authHeaders(): Promise<Record<string, string>> {
  const { getLocalAuthToken, isLocalAuthMode } = await import("@/auth/localAuth");
  const { getWeChatAuthToken } = await import("@/auth/wechatAuth");

  const headers: Record<string, string> = {};
  if (isLocalAuthMode()) {
    const token = getLocalAuthToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  if (!headers["Authorization"]) {
    const wechatToken = getWeChatAuthToken();
    if (wechatToken) headers["Authorization"] = `Bearer ${wechatToken}`;
  }
  if (!headers["Authorization"]) {
    const clerk = (window as unknown as { Clerk?: { session?: { getToken: () => Promise<string> } } }).Clerk;
    if (clerk?.session) {
      try {
        const token = await clerk.session.getToken();
        headers["Authorization"] = `Bearer ${token}`;
      } catch { /* ignore */ }
    }
  }
  return headers;
}

function _attachmentUrl(accountId: string, messageId: string, attachmentId: string): string {
  return `${V1}/email/accounts/${accountId}/messages/${messageId}/attachments/${attachmentId}/download`;
}

export async function fetchAttachmentBlob(
  accountId: string,
  messageId: string,
  attachmentId: string,
): Promise<string> {
  const { getApiBaseUrl } = await import("@/lib/api-base");
  const baseUrl = getApiBaseUrl();
  const headers = await _authHeaders();
  const resp = await fetch(`${baseUrl}${_attachmentUrl(accountId, messageId, attachmentId)}`, { headers });
  if (!resp.ok) throw new Error("Failed to fetch attachment");
  const blob = await resp.blob();
  return URL.createObjectURL(blob);
}

export async function downloadEmailAttachment(
  accountId: string,
  messageId: string,
  attachmentId: string,
  filename: string,
): Promise<void> {
  const blobUrl = await fetchAttachmentBlob(accountId, messageId, attachmentId);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(blobUrl);
}

export async function archiveEmail(
  accountId: string,
  messageId: string,
): Promise<void> {
  await customFetch(
    `${V1}/email/accounts/${accountId}/messages/${messageId}/archive`,
    { method: "POST" },
  );
}
