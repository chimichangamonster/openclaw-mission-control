"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Pencil, Plus, Star, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmActionDialog } from "@/components/ui/confirm-action-dialog";
import {
  type EmailSignature,
  createEmailSignature,
  deleteEmailSignature,
  fetchEmailSignatures,
  updateEmailSignature,
} from "@/lib/email-api";

interface EmailSignaturesPanelProps {
  accountId: string;
  emailAddress: string;
  canManage: boolean;
}

export function EmailSignaturesPanel({
  accountId,
  emailAddress,
  canManage,
}: EmailSignaturesPanelProps) {
  const [signatures, setSignatures] = useState<EmailSignature[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<EmailSignature | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<EmailSignature | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchEmailSignatures(accountId);
      setSignatures(data);
      setError(null);
    } catch {
      setError("Failed to load signatures.");
    } finally {
      setLoading(false);
    }
  }, [accountId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleSave = async (
    name: string,
    bodyHtml: string,
    isDefault: boolean,
  ) => {
    try {
      if (editing) {
        const updated = await updateEmailSignature(accountId, editing.id, {
          name,
          body_html: bodyHtml,
          is_default: isDefault,
        });
        setSignatures((prev) =>
          prev.map((s) => {
            if (s.id === updated.id) return updated;
            // Mirror the server-side single-default invariant in local state.
            if (isDefault && s.is_default) return { ...s, is_default: false };
            return s;
          }),
        );
      } else {
        const created = await createEmailSignature(accountId, {
          name,
          body_html: bodyHtml,
          is_default: isDefault,
        });
        setSignatures((prev) => {
          const next = isDefault
            ? prev.map((s) => ({ ...s, is_default: false }))
            : prev;
          return [...next, created];
        });
      }
      setEditorOpen(false);
      setEditing(null);
    } catch {
      setError("Failed to save signature.");
    }
  };

  const handleSetDefault = async (sig: EmailSignature) => {
    try {
      const updated = await updateEmailSignature(accountId, sig.id, {
        is_default: true,
      });
      setSignatures((prev) =>
        prev.map((s) => {
          if (s.id === updated.id) return updated;
          return { ...s, is_default: false };
        }),
      );
    } catch {
      setError("Failed to set default.");
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      setDeleting(true);
      await deleteEmailSignature(accountId, deleteTarget.id);
      setSignatures((prev) => prev.filter((s) => s.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch {
      setError("Failed to delete signature.");
    } finally {
      setDeleting(false);
    }
  };

  if (!canManage && signatures.length === 0) {
    return null;
  }

  return (
    <div className="mt-3 rounded-lg border border-dashed border-slate-200 bg-slate-50 p-3">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-xs font-semibold text-slate-700">
            Signatures
          </h4>
          <p className="text-xs text-slate-500">
            Auto-appended to messages sent from this account.
          </p>
        </div>
        {canManage ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setEditing(null);
              setEditorOpen(true);
            }}
          >
            <Plus className="h-3.5 w-3.5" />
            Add
          </Button>
        ) : null}
      </div>

      {error ? (
        <p className="mt-2 text-xs text-rose-600">{error}</p>
      ) : null}

      {loading ? (
        <p className="mt-2 text-xs text-slate-500">Loading…</p>
      ) : signatures.length === 0 ? (
        <p className="mt-2 text-xs text-slate-500">
          No signatures yet. Sent messages will go out without one.
        </p>
      ) : (
        <ul className="mt-2 space-y-1.5">
          {signatures.map((sig) => (
            <li
              key={sig.id}
              className="flex items-center justify-between rounded border border-slate-200 bg-white px-3 py-2"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-xs font-medium text-slate-900">
                    {sig.name}
                  </span>
                  {sig.is_default ? (
                    <span className="inline-flex items-center gap-1 rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700">
                      <CheckCircle2 className="h-3 w-3" />
                      Default
                    </span>
                  ) : null}
                </div>
              </div>
              {canManage ? (
                <div className="flex items-center gap-1">
                  {!sig.is_default ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleSetDefault(sig)}
                      title="Set as default"
                    >
                      <Star className="h-3 w-3" />
                    </Button>
                  ) : null}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setEditing(sig);
                      setEditorOpen(true);
                    }}
                    title="Edit"
                  >
                    <Pencil className="h-3 w-3" />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setDeleteTarget(sig)}
                    title="Delete"
                    className="text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {editorOpen ? (
        <SignatureEditor
          initial={editing}
          accountLabel={emailAddress}
          existingDefaultName={
            signatures.find(
              (s) => s.is_default && (!editing || s.id !== editing.id),
            )?.name ?? null
          }
          onCancel={() => {
            setEditorOpen(false);
            setEditing(null);
          }}
          onSave={handleSave}
        />
      ) : null}

      <ConfirmActionDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title="Delete signature?"
        description={`This will remove "${deleteTarget?.name ?? ""}" from ${emailAddress}. Messages already sent are unaffected.`}
        onConfirm={handleDelete}
        isConfirming={deleting}
        confirmLabel="Delete"
        confirmingLabel="Deleting…"
        ariaLabel="Delete signature confirmation"
      />
    </div>
  );
}

interface SignatureEditorProps {
  initial: EmailSignature | null;
  accountLabel: string;
  existingDefaultName: string | null;
  onCancel: () => void;
  onSave: (name: string, bodyHtml: string, isDefault: boolean) => void;
}

function SignatureEditor({
  initial,
  accountLabel,
  existingDefaultName,
  onCancel,
  onSave,
}: SignatureEditorProps) {
  const [name, setName] = useState(initial?.name ?? "");
  const [bodyHtml, setBodyHtml] = useState(initial?.body_html ?? "");
  const [isDefault, setIsDefault] = useState(initial?.is_default ?? false);

  const trimmedName = name.trim();
  const trimmedBody = bodyHtml.trim();
  const valid = trimmedName.length > 0 && trimmedBody.length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <div className="w-full max-w-2xl rounded-xl border border-slate-200 bg-white p-5 shadow-lg">
        <div className="mb-3">
          <h3 className="text-sm font-semibold text-slate-900">
            {initial ? "Edit signature" : "New signature"}
          </h3>
          <p className="text-xs text-slate-500">For {accountLabel}</p>
        </div>

        <label className="block text-xs font-medium text-slate-700">
          Name
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Full formal, Short reply"
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
        />

        <label className="mt-3 block text-xs font-medium text-slate-700">
          HTML
        </label>
        <textarea
          value={bodyHtml}
          onChange={(e) => setBodyHtml(e.target.value)}
          placeholder='<p>--<br>Henry Chin<br>VantageClaw<br><a href="mailto:...">...</a></p>'
          spellCheck={false}
          className="mt-1 h-40 w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-xs focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500"
        />

        <label className="mt-3 block text-xs font-medium text-slate-700">
          Preview
        </label>
        <div
          className="mt-1 min-h-[60px] rounded-md border border-slate-200 bg-slate-50 p-3 text-sm"
          // The textarea is the source of truth; preview reflects what gets sent.
          dangerouslySetInnerHTML={{ __html: bodyHtml || "&nbsp;" }}
        />

        <label className="mt-3 flex items-center gap-2 text-xs text-slate-700">
          <input
            type="checkbox"
            checked={isDefault}
            onChange={(e) => setIsDefault(e.target.checked)}
          />
          Use as default for this account
        </label>
        {isDefault && existingDefaultName ? (
          <p className="mt-1 text-xs text-amber-700">
            Replaces &quot;{existingDefaultName}&quot; as the current default.
          </p>
        ) : null}

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            size="sm"
            disabled={!valid}
            onClick={() => onSave(trimmedName, bodyHtml, isDefault)}
          >
            {initial ? "Save" : "Create"}
          </Button>
        </div>
      </div>
    </div>
  );
}
