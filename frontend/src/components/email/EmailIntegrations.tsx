"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Bot,
  BotOff,
  Eye,
  EyeOff,
  Mail,
  Power,
  PowerOff,
  RefreshCw,
  Trash2,
} from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { useOrganizationMembership } from "@/lib/use-organization-membership";

import { Button } from "@/components/ui/button";
import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";
import {
  type EmailAccount,
  deleteEmailAccount,
  fetchEmailAccounts,
  getOAuthUrl,
  triggerEmailSync,
  updateEmailAccount,
} from "@/lib/email-api";

export function EmailIntegrations() {
  const { isSignedIn } = useAuth();
  const { member, isAdmin } = useOrganizationMembership(isSignedIn);
  const [accounts, setAccounts] = useState<EmailAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connectingProvider, setConnectingProvider] = useState<string | null>(
    null,
  );
  const [deleteTarget, setDeleteTarget] = useState<EmailAccount | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const loadAccounts = useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchEmailAccounts();
      setAccounts(data);
      setError(null);
    } catch (err) {
      setError("Failed to load email accounts.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  const handleConnect = async (provider: "zoho" | "microsoft" | "google") => {
    try {
      setConnectingProvider(provider);
      const { authorization_url } = await getOAuthUrl(provider);
      window.location.href = authorization_url;
    } catch {
      setError(`Failed to start ${provider} OAuth flow.`);
      setConnectingProvider(null);
    }
  };

  const handleToggleSync = async (account: EmailAccount) => {
    try {
      const updated = await updateEmailAccount(account.id, {
        sync_enabled: !account.sync_enabled,
      });
      setAccounts((prev) =>
        prev.map((a) => (a.id === updated.id ? updated : a)),
      );
    } catch {
      setError("Failed to update sync setting.");
    }
  };

  const handleSync = async (account: EmailAccount) => {
    try {
      await triggerEmailSync(account.id);
    } catch {
      setError("Failed to trigger sync.");
    }
  };

  const handleToggleVisibility = async (account: EmailAccount) => {
    try {
      const newVisibility = account.visibility === "shared" ? "private" : "shared";
      const updated = await updateEmailAccount(account.id, {
        visibility: newVisibility,
      });
      setAccounts((prev) =>
        prev.map((a) => (a.id === updated.id ? updated : a)),
      );
    } catch {
      setError("Failed to update visibility.");
    }
  };

  const handleToggleAgentAccess = async (account: EmailAccount) => {
    try {
      const newAccess =
        account.agent_access === "enabled" ? "disabled" : "enabled";
      const updated = await updateEmailAccount(account.id, {
        agent_access: newAccess,
      });
      setAccounts((prev) =>
        prev.map((a) => (a.id === updated.id ? updated : a)),
      );
    } catch {
      setError("Failed to update AI processing.");
    }
  };

  const canToggleVisibility = (account: EmailAccount) =>
    isAdmin || account.user_id === member?.user_id;

  // Same gate as visibility — only owner or admin can change AI processing.
  const canToggleAgentAccess = canToggleVisibility;

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      setDeleting(true);
      await deleteEmailAccount(deleteTarget.id);
      setAccounts((prev) => prev.filter((a) => a.id !== deleteTarget.id));
      setDeleteDialogOpen(false);
      setDeleteTarget(null);
    } catch {
      setError("Failed to disconnect account.");
    } finally {
      setDeleting(false);
    }
  };

  const providerLabel = (p: string) =>
    p === "zoho"
      ? "Zoho Mail"
      : p === "microsoft"
        ? "Microsoft Outlook"
        : p === "google"
          ? "Google Workspace"
          : p;

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-base font-semibold text-slate-900">
        Email Integrations
      </h2>
      <p className="mt-1 text-sm text-slate-500">
        Connect your email accounts so OpenClaw agents can manage your inbox.
      </p>

      {error ? (
        <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {error}
        </div>
      ) : null}

      <div className="mt-5 flex flex-wrap gap-3">
        <Button
          variant="outline"
          onClick={() => handleConnect("microsoft")}
          disabled={connectingProvider !== null}
        >
          <Mail className="h-4 w-4" />
          {connectingProvider === "microsoft"
            ? "Redirecting..."
            : "Connect Outlook"}
        </Button>
        <Button
          variant="outline"
          onClick={() => handleConnect("google")}
          disabled={connectingProvider !== null}
        >
          <Mail className="h-4 w-4" />
          {connectingProvider === "google"
            ? "Redirecting..."
            : "Connect Google Workspace"}
        </Button>
        <Button
          variant="outline"
          onClick={() => handleConnect("zoho")}
          disabled={connectingProvider !== null}
        >
          <Mail className="h-4 w-4" />
          {connectingProvider === "zoho"
            ? "Redirecting..."
            : "Connect Zoho Mail"}
        </Button>
      </div>

      {loading ? (
        <p className="mt-4 text-sm text-slate-500">Loading accounts...</p>
      ) : accounts.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">
          No email accounts connected yet.
        </p>
      ) : (
        <div className="mt-5 space-y-3">
          {accounts.map((account) => (
            <div
              key={account.id}
              className="flex items-center justify-between rounded-lg border border-slate-200 p-4"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-slate-900">
                    {account.email_address}
                  </span>
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
                    {providerLabel(account.provider)}
                  </span>
                  {account.sync_enabled ? (
                    <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-700">
                      Syncing
                    </span>
                  ) : (
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500">
                      Paused
                    </span>
                  )}
                  {account.visibility === "private" ? (
                    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700">
                      Private
                    </span>
                  ) : (
                    <span className="rounded bg-sky-100 px-1.5 py-0.5 text-xs text-sky-700">
                      Shared
                    </span>
                  )}
                  {account.agent_access === "disabled" ? (
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
                      AI off
                    </span>
                  ) : (
                    <span className="rounded bg-violet-100 px-1.5 py-0.5 text-xs text-violet-700">
                      AI on
                    </span>
                  )}
                </div>
                {account.last_sync_at ? (
                  <p className="mt-1 text-xs text-slate-500">
                    Last sync:{" "}
                    {new Date(account.last_sync_at).toLocaleString()}
                  </p>
                ) : null}
                {account.last_sync_error ? (
                  <p className="mt-1 text-xs text-rose-600">
                    {account.last_sync_error}
                  </p>
                ) : null}
              </div>
              <div className="flex items-center gap-2">
                {canToggleVisibility(account) ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleToggleVisibility(account)}
                    title={
                      account.visibility === "shared"
                        ? "Make private (only you and admins can see)"
                        : "Make shared (all org members can see)"
                    }
                  >
                    {account.visibility === "shared" ? (
                      <Eye className="h-3.5 w-3.5" />
                    ) : (
                      <EyeOff className="h-3.5 w-3.5" />
                    )}
                  </Button>
                ) : null}
                {canToggleAgentAccess(account) ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleToggleAgentAccess(account)}
                    title={
                      account.agent_access === "enabled"
                        ? "Turn off AI processing (agents won't read this inbox)"
                        : "Turn on AI processing (agents can triage and act on this inbox)"
                    }
                  >
                    {account.agent_access === "enabled" ? (
                      <Bot className="h-3.5 w-3.5" />
                    ) : (
                      <BotOff className="h-3.5 w-3.5" />
                    )}
                  </Button>
                ) : null}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleSync(account)}
                  title="Sync now"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleToggleSync(account)}
                  title={account.sync_enabled ? "Pause sync" : "Resume sync"}
                >
                  {account.sync_enabled ? (
                    <PowerOff className="h-3.5 w-3.5" />
                  ) : (
                    <Power className="h-3.5 w-3.5" />
                  )}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setDeleteTarget(account);
                    setDeleteDialogOpen(true);
                  }}
                  title="Disconnect"
                  className="text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <ConfirmActionDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        title="Disconnect email account?"
        description={`This will remove ${deleteTarget?.email_address ?? "this account"} and delete all synced messages.`}
        onConfirm={handleDelete}
        isConfirming={deleting}
        confirmLabel="Disconnect"
        confirmingLabel="Disconnecting..."
        ariaLabel="Disconnect email account confirmation"
      />
    </section>
  );
}
