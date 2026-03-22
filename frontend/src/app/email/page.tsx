"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Archive,
  Inbox,
  Mail,
  MailOpen,
  RefreshCw,
  Send,
  Trash2,
} from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { FeatureGate } from "@/components/molecules/FeatureGate";
import { Button } from "@/components/ui/button";
import {
  type EmailAccount,
  type EmailMessage,
  fetchEmailAccounts,
  fetchEmailMessages,
  archiveEmail,
  updateEmailMessage,
  triggerEmailSync,
} from "@/lib/email-api";
import { cn } from "@/lib/utils";

type Folder = "inbox" | "sent" | "archive" | "trash";
type TriageFilter = "" | "pending" | "triaged" | "actioned" | "ignored";

export default function EmailPage() {
  const { isSignedIn } = useAuth();
  const [accounts, setAccounts] = useState<EmailAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(
    null,
  );
  const [messages, setMessages] = useState<EmailMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [folder, setFolder] = useState<Folder>("inbox");
  const [triageFilter, setTriageFilter] = useState<TriageFilter>("");

  const loadAccounts = useCallback(async () => {
    try {
      const data = await fetchEmailAccounts();
      setAccounts(data);
      if (data.length > 0 && !selectedAccountId) {
        setSelectedAccountId(data[0].id);
      }
    } catch {
      // silently fail
    }
  }, [selectedAccountId]);

  const loadMessages = useCallback(async () => {
    if (!selectedAccountId) return;
    try {
      setLoading(true);
      const data = await fetchEmailMessages(selectedAccountId, {
        folder,
        triage_status: triageFilter || undefined,
        limit: 50,
      });
      setMessages(data);
    } catch {
      setMessages([]);
    } finally {
      setLoading(false);
    }
  }, [selectedAccountId, folder, triageFilter]);

  useEffect(() => {
    if (isSignedIn) loadAccounts();
  }, [isSignedIn, loadAccounts]);

  useEffect(() => {
    if (selectedAccountId) loadMessages();
  }, [selectedAccountId, loadMessages]);

  const handleSync = async () => {
    if (!selectedAccountId) return;
    await triggerEmailSync(selectedAccountId);
    setTimeout(loadMessages, 2000);
  };

  const handleArchive = async (msg: EmailMessage) => {
    await archiveEmail(msg.email_account_id, msg.id);
    setMessages((prev) => prev.filter((m) => m.id !== msg.id));
  };

  const handleMarkRead = async (msg: EmailMessage) => {
    const updated = await updateEmailMessage(msg.email_account_id, msg.id, {
      is_read: !msg.is_read,
    });
    setMessages((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
  };

  const folders: { key: Folder; label: string; icon: typeof Inbox }[] = [
    { key: "inbox", label: "Inbox", icon: Inbox },
    { key: "sent", label: "Sent", icon: Send },
    { key: "archive", label: "Archive", icon: Archive },
    { key: "trash", label: "Trash", icon: Trash2 },
  ];

  const triageOptions: { key: TriageFilter; label: string }[] = [
    { key: "", label: "All" },
    { key: "pending", label: "Pending" },
    { key: "triaged", label: "Triaged" },
    { key: "actioned", label: "Actioned" },
    { key: "ignored", label: "Ignored" },
  ];

  return (
    <FeatureGate flag="email" label="Email">
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to view your email.",
        forceRedirectUrl: "/email",
        signUpForceRedirectUrl: "/email",
      }}
      title="Email"
      description="View and manage synced emails from connected accounts."
      headerActions={
        <Button variant="outline" size="sm" onClick={handleSync}>
          <RefreshCw className="h-4 w-4" />
          Sync
        </Button>
      }
    >
      {accounts.length === 0 && !loading ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Mail className="h-12 w-12 text-slate-300" />
          <p className="mt-4 text-sm text-slate-600">
            No email accounts connected.
          </p>
          <Link
            href="/settings"
            className="mt-2 text-sm font-medium text-blue-600 hover:text-blue-700"
          >
            Connect an account in Settings
          </Link>
        </div>
      ) : (
        <div className="flex gap-6">
          {/* Sidebar filters */}
          <div className="w-48 shrink-0 space-y-4">
            {/* Account selector */}
            {accounts.length > 1 ? (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Account
                </p>
                <div className="mt-1 space-y-1">
                  {accounts.map((acct) => (
                    <button
                      key={acct.id}
                      onClick={() => setSelectedAccountId(acct.id)}
                      className={cn(
                        "block w-full truncate rounded-lg px-3 py-2 text-left text-sm transition",
                        selectedAccountId === acct.id
                          ? "bg-blue-100 font-medium text-blue-800"
                          : "text-slate-700 hover:bg-slate-100",
                      )}
                    >
                      {acct.email_address}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {/* Folders */}
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Folders
              </p>
              <div className="mt-1 space-y-1">
                {folders.map((f) => {
                  const Icon = f.icon;
                  return (
                    <button
                      key={f.key}
                      onClick={() => setFolder(f.key)}
                      className={cn(
                        "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm transition",
                        folder === f.key
                          ? "bg-blue-100 font-medium text-blue-800"
                          : "text-slate-700 hover:bg-slate-100",
                      )}
                    >
                      <Icon className="h-4 w-4" />
                      {f.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Triage filter */}
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Triage
              </p>
              <div className="mt-1 space-y-1">
                {triageOptions.map((t) => (
                  <button
                    key={t.key}
                    onClick={() => setTriageFilter(t.key)}
                    className={cn(
                      "block w-full rounded-lg px-3 py-2 text-left text-sm transition",
                      triageFilter === t.key
                        ? "bg-blue-100 font-medium text-blue-800"
                        : "text-slate-700 hover:bg-slate-100",
                    )}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Message list */}
          <div className="min-w-0 flex-1">
            {loading ? (
              <p className="py-8 text-center text-sm text-slate-500">
                Loading messages...
              </p>
            ) : messages.length === 0 ? (
              <p className="py-8 text-center text-sm text-slate-500">
                No messages in this folder.
              </p>
            ) : (
              <div className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={cn(
                      "flex items-start gap-3 px-4 py-3 transition hover:bg-slate-50",
                      !msg.is_read && "bg-blue-50/50",
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <Link
                        href={`/email/${msg.id}?account=${msg.email_account_id}`}
                        className="block"
                      >
                        <div className="flex items-center gap-2">
                          <span
                            className={cn(
                              "truncate text-sm",
                              !msg.is_read
                                ? "font-semibold text-slate-900"
                                : "text-slate-700",
                            )}
                          >
                            {msg.sender_name || msg.sender_email}
                          </span>
                          {msg.triage_status !== "pending" ? (
                            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                              {msg.triage_status}
                            </span>
                          ) : null}
                          {msg.has_attachments ? (
                            <span className="text-xs text-slate-400">📎</span>
                          ) : null}
                        </div>
                        <p
                          className={cn(
                            "mt-0.5 truncate text-sm",
                            !msg.is_read
                              ? "font-medium text-slate-800"
                              : "text-slate-600",
                          )}
                        >
                          {msg.subject || "(no subject)"}
                        </p>
                        <p className="mt-0.5 truncate text-xs text-slate-500">
                          {msg.body_text?.slice(0, 120) || ""}
                        </p>
                      </Link>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <span className="text-xs text-slate-500">
                        {new Date(msg.received_at).toLocaleDateString()}
                      </span>
                      <div className="flex gap-1">
                        <button
                          onClick={() => handleMarkRead(msg)}
                          className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                          title={msg.is_read ? "Mark unread" : "Mark read"}
                        >
                          {msg.is_read ? (
                            <MailOpen className="h-3.5 w-3.5" />
                          ) : (
                            <Mail className="h-3.5 w-3.5" />
                          )}
                        </button>
                        <button
                          onClick={() => handleArchive(msg)}
                          className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                          title="Archive"
                        >
                          <Archive className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </DashboardPageLayout>
    </FeatureGate>
  );
}
