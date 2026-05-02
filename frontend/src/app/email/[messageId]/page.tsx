"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import {
  Archive,
  ArrowLeft,
  ChevronDown,
  Download,
  Eye,
  FileSpreadsheet,
  FileText,
  Image as ImageIcon,
  Mail,
  Paperclip,
  Presentation,
  Reply,
  Star,
  Tag,
  X,
} from "lucide-react";

import { cn } from "@/lib/utils";

/* ── Triage color maps (shared with list page) ── */

const TRIAGE_STATUS_COLORS: Record<string, string> = {
  pending: "bg-amber-100 text-amber-800",
  triaged: "bg-blue-100 text-blue-700",
  actioned: "bg-green-100 text-green-700",
  ignored: "bg-slate-100 text-slate-500",
  needs_review: "bg-orange-100 text-orange-700",
  spam: "bg-red-100 text-red-600",
  archived: "bg-slate-100 text-slate-500",
};

const TRIAGE_CATEGORY_COLORS: Record<string, string> = {
  inquiry: "bg-emerald-100 text-emerald-700",
  invoice: "bg-violet-100 text-violet-700",
  regulatory: "bg-red-100 text-red-700",
  stakeholder: "bg-indigo-100 text-indigo-700",
  follow_up: "bg-amber-100 text-amber-700",
  vendor: "bg-slate-100 text-slate-600",
  scheduling: "bg-cyan-100 text-cyan-700",
  spam: "bg-red-50 text-red-500",
  fyi: "bg-slate-50 text-slate-500",
};

const TRIAGE_CATEGORIES = [
  "inquiry", "invoice", "regulatory", "stakeholder",
  "follow_up", "vendor", "scheduling", "spam", "fyi",
] as const;

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { useNotifications } from "@/components/providers/NotificationProvider";
import { Button } from "@/components/ui/button";
import {
  type EmailAttachment,
  type EmailMessage,
  fetchEmailMessage,
  fetchEmailAttachments,
  fetchAttachmentBlob,
  downloadEmailAttachment,
  archiveEmail,
  replyToEmail,
  updateEmailMessage,
} from "@/lib/email-api";
export default function EmailMessagePage() {
  const { isSignedIn } = useAuth();
  const { refreshUnreadEmailCount } = useNotifications();
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();

  const messageId = params.messageId as string;
  const accountId = searchParams.get("account") ?? "";

  const [message, setMessage] = useState<EmailMessage | null>(null);
  const [attachments, setAttachments] = useState<EmailAttachment[]>([]);
  const [loading, setLoading] = useState(true);
  const [replyOpen, setReplyOpen] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [previewAtt, setPreviewAtt] = useState<EmailAttachment | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const loadMessage = useCallback(async () => {
    if (!accountId || !messageId) return;
    try {
      setLoading(true);
      const msg = await fetchEmailMessage(accountId, messageId);
      setMessage(msg);
      if (!msg.is_read) {
        await updateEmailMessage(accountId, messageId, { is_read: true });
        refreshUnreadEmailCount();
      }
      if (msg.has_attachments) {
        try {
          const atts = await fetchEmailAttachments(accountId, messageId);
          // Filter out inline attachments — they're rendered in the email body via CID replacement
          setAttachments(atts.filter((a) => !a.is_inline));
        } catch {
          setAttachments([]);
        }
      }
    } catch {
      setMessage(null);
    } finally {
      setLoading(false);
    }
  }, [accountId, messageId, refreshUnreadEmailCount]);

  useEffect(() => {
    if (isSignedIn) loadMessage();
  }, [isSignedIn, loadMessage]);

  const isPreviewable = (att: EmailAttachment) => {
    const ct = att.content_type?.toLowerCase() ?? "";
    const fn = att.filename.toLowerCase();
    return (
      ct.startsWith("image/") ||
      ct === "application/pdf" ||
      fn.endsWith(".pdf") ||
      fn.endsWith(".jpg") || fn.endsWith(".jpeg") || fn.endsWith(".png") ||
      fn.endsWith(".gif") || fn.endsWith(".webp")
    );
  };

  const isImage = (att: EmailAttachment) => {
    const ct = att.content_type?.toLowerCase() ?? "";
    const fn = att.filename.toLowerCase();
    return ct.startsWith("image/") || /\.(jpg|jpeg|png|gif|webp|svg)$/.test(fn);
  };

  const getFileIcon = (att: EmailAttachment) => {
    const fn = att.filename.toLowerCase();
    const ct = att.content_type?.toLowerCase() ?? "";
    if (ct.startsWith("image/") || /\.(jpg|jpeg|png|gif|webp|svg)$/.test(fn))
      return <ImageIcon className="h-5 w-5 text-emerald-500" />;
    if (ct === "application/pdf" || fn.endsWith(".pdf"))
      return <FileText className="h-5 w-5 text-red-500" />;
    if (fn.endsWith(".xlsx") || fn.endsWith(".xls") || fn.endsWith(".csv") ||
        ct.includes("spreadsheet") || ct.includes("excel"))
      return <FileSpreadsheet className="h-5 w-5 text-green-600" />;
    if (fn.endsWith(".pptx") || fn.endsWith(".ppt") || ct.includes("presentation"))
      return <Presentation className="h-5 w-5 text-orange-500" />;
    if (fn.endsWith(".docx") || fn.endsWith(".doc") || ct.includes("word"))
      return <FileText className="h-5 w-5 text-blue-600" />;
    return <Paperclip className="h-5 w-5 text-slate-400" />;
  };

  const openPreview = async (att: EmailAttachment) => {
    if (!isPreviewable(att)) {
      downloadEmailAttachment(accountId, messageId, att.id, att.filename || "attachment");
      return;
    }
    setPreviewAtt(att);
    setPreviewLoading(true);
    try {
      const url = await fetchAttachmentBlob(accountId, messageId, att.id);
      setPreviewUrl(url);
    } catch {
      setPreviewUrl(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  const closePreview = () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewAtt(null);
    setPreviewUrl(null);
  };

  const handleReply = async () => {
    if (!replyText.trim() || !message) return;
    try {
      setSending(true);
      await replyToEmail(accountId, messageId, { body_text: replyText });
      setReplyOpen(false);
      setReplyText("");
    } catch {
      // error handling could be improved
    } finally {
      setSending(false);
    }
  };

  const handleArchive = async () => {
    if (!message) return;
    await archiveEmail(accountId, messageId);
    router.push("/email");
  };

  const handleTriage = async (status: string) => {
    if (!message) return;
    const updated = await updateEmailMessage(accountId, messageId, {
      triage_status: status,
    });
    setMessage(updated);
  };

  const handleToggleStar = async () => {
    if (!message) return;
    const updated = await updateEmailMessage(accountId, messageId, {
      is_starred: !message.is_starred,
    });
    setMessage(updated);
  };

  const handleRecategorize = async (newCategory: string) => {
    if (!message || newCategory === message.triage_category) return;
    const updated = await updateEmailMessage(accountId, messageId, {
      triage_category: newCategory,
      triage_status: "triaged",
    });
    setMessage(updated);
  };

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to view email.",
        forceRedirectUrl: "/email",
        signUpForceRedirectUrl: "/email",
      }}
      title={message?.subject || "Email"}
      description=""
      headerActions={
        <Button
          variant="outline"
          size="sm"
          onClick={() => router.push("/email")}
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
      }
    >
      {loading ? (
        <p className="py-8 text-center text-sm text-slate-500">
          Loading message...
        </p>
      ) : !message ? (
        <p className="py-8 text-center text-sm text-slate-500">
          Message not found.
        </p>
      ) : (
        <div className="space-y-4">
          {/* Message header */}
          <div className="rounded-xl border border-slate-200 bg-white p-6">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">
                  {message.subject || "(no subject)"}
                </h2>
                <div className="mt-2 space-y-1 text-sm text-slate-600">
                  <p>
                    <span className="font-medium">From:</span>{" "}
                    {message.sender_name
                      ? `${message.sender_name} <${message.sender_email}>`
                      : message.sender_email}
                  </p>
                  <p>
                    <span className="font-medium">To:</span>{" "}
                    {message.recipients_to
                      .map((r) => r.name || r.email)
                      .join(", ")}
                  </p>
                  {message.recipients_cc?.length ? (
                    <p>
                      <span className="font-medium">CC:</span>{" "}
                      {message.recipients_cc
                        .map((r) => r.name || r.email)
                        .join(", ")}
                    </p>
                  ) : null}
                  <p>
                    <span className="font-medium">Date:</span>{" "}
                    {new Date(message.received_at).toLocaleString()}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleToggleStar}
                  className={cn(
                    "rounded p-1 transition hover:bg-slate-100",
                    message.is_starred
                      ? "text-amber-500 hover:text-amber-600"
                      : "text-slate-400 hover:text-slate-600",
                  )}
                  title={message.is_starred ? "Unstar" : "Star"}
                >
                  <Star
                    className={cn(
                      "h-4 w-4",
                      message.is_starred && "fill-current",
                    )}
                  />
                </button>
                <span className={cn("rounded px-2 py-1 text-xs font-medium", TRIAGE_STATUS_COLORS[message.triage_status] ?? "bg-slate-100 text-slate-600")}>
                  {message.triage_status.replace("_", " ")}
                </span>
                {/* Re-categorization dropdown */}
                <span className="relative">
                  <button
                    onClick={(e) => {
                      const menu = e.currentTarget.nextElementSibling;
                      if (menu instanceof HTMLElement) menu.classList.toggle("hidden");
                    }}
                    className={cn(
                      "flex items-center gap-1 rounded px-2 py-1 text-xs font-medium transition hover:ring-1 hover:ring-slate-300",
                      message.triage_category
                        ? TRIAGE_CATEGORY_COLORS[message.triage_category] ?? "bg-blue-100 text-blue-700"
                        : "bg-slate-50 text-slate-400",
                    )}
                    title="Change category"
                  >
                    {message.triage_category
                      ? message.triage_category.replace("_", " ")
                      : "categorize"}
                    <ChevronDown className="h-3 w-3" />
                  </button>
                  <div className="absolute right-0 top-full z-50 mt-1 hidden min-w-[130px] rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
                    {TRIAGE_CATEGORIES.map((cat) => (
                      <button
                        key={cat}
                        onClick={(e) => {
                          handleRecategorize(cat);
                          const menu = e.currentTarget.parentElement;
                          if (menu instanceof HTMLElement) menu.classList.add("hidden");
                        }}
                        className={cn(
                          "block w-full px-3 py-1.5 text-left text-xs transition hover:bg-slate-50",
                          message.triage_category === cat
                            ? "font-medium text-blue-700"
                            : "text-slate-600",
                        )}
                      >
                        {cat.replace("_", " ")}
                      </button>
                    ))}
                  </div>
                </span>
              </div>
            </div>

            {/* Body */}
            <div className="mt-6 border-t border-slate-100 pt-4">
              {message.body_html ? (
                <div
                  className="prose prose-sm max-w-none text-slate-700"
                  dangerouslySetInnerHTML={{ __html: message.body_html }}
                />
              ) : (
                <pre className="whitespace-pre-wrap text-sm text-slate-700">
                  {message.body_text || "(empty)"}
                </pre>
              )}
            </div>
          </div>

          {/* Attachments */}
          {attachments.length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-700">
                <Paperclip className="h-4 w-4" />
                {attachments.length} attachment{attachments.length > 1 ? "s" : ""}
              </div>
              <div className="flex flex-wrap gap-2">
                {attachments.map((att) => {
                  const canPreview = isPreviewable(att);
                  const sizeLabel = att.size_bytes != null
                    ? att.size_bytes < 1024
                      ? `${att.size_bytes} B`
                      : att.size_bytes < 1048576
                        ? `${(att.size_bytes / 1024).toFixed(0)} KB`
                        : `${(att.size_bytes / 1048576).toFixed(1)} MB`
                    : null;
                  return (
                    <div
                      key={att.id}
                      className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700"
                    >
                      {getFileIcon(att)}
                      <span className="max-w-[200px] truncate">{att.filename || "Untitled"}</span>
                      {sizeLabel && (
                        <span className="text-xs text-slate-400">{sizeLabel}</span>
                      )}
                      <div className="ml-1 flex items-center gap-1">
                        {canPreview && (
                          <button
                            type="button"
                            onClick={() => openPreview(att)}
                            className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-600"
                            title="Preview"
                          >
                            <Eye className="h-4 w-4" />
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() =>
                            downloadEmailAttachment(accountId, messageId, att.id, att.filename || "attachment")
                          }
                          className="rounded p-1 text-slate-400 transition-colors hover:bg-slate-200 hover:text-slate-600"
                          title="Download"
                        >
                          <Download className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Attachment preview overlay */}
          {previewAtt && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
              <div className="relative flex max-h-[90vh] w-full max-w-4xl flex-col rounded-xl bg-white shadow-2xl">
                <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
                  <div className="flex items-center gap-2 text-sm font-medium text-slate-700">
                    {getFileIcon(previewAtt)}
                    <span className="truncate">{previewAtt.filename}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() =>
                        downloadEmailAttachment(accountId, messageId, previewAtt.id, previewAtt.filename || "attachment")
                      }
                      className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-100"
                      title="Download"
                    >
                      <Download className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={closePreview}
                      className="rounded p-1.5 text-slate-500 transition-colors hover:bg-slate-100"
                      title="Close"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                </div>
                <div className="flex-1 overflow-auto p-4">
                  {previewLoading ? (
                    <div className="flex h-64 items-center justify-center">
                      <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
                    </div>
                  ) : !previewUrl ? (
                    <p className="py-8 text-center text-sm text-slate-500">
                      Failed to load preview.
                    </p>
                  ) : isImage(previewAtt) ? (
                    <img
                      src={previewUrl}
                      alt={previewAtt.filename}
                      className="mx-auto max-h-[70vh] rounded object-contain"
                    />
                  ) : (
                    <iframe
                      src={previewUrl}
                      title={previewAtt.filename}
                      className="h-[70vh] w-full rounded border-0"
                    />
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setReplyOpen(!replyOpen)}
            >
              <Reply className="h-4 w-4" />
              Reply
            </Button>
            <Button variant="outline" size="sm" onClick={handleArchive}>
              <Archive className="h-4 w-4" />
              Archive
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleTriage("triaged")}
            >
              <Tag className="h-4 w-4" />
              Mark triaged
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleTriage("actioned")}
            >
              <Mail className="h-4 w-4" />
              Mark actioned
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleTriage("ignored")}
              className="text-slate-500"
            >
              Ignore
            </Button>
          </div>

          {/* Reply composer */}
          {replyOpen ? (
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <p className="text-sm font-medium text-slate-700">
                Reply to {message.sender_name || message.sender_email}
              </p>
              <textarea
                value={replyText}
                onChange={(e) => setReplyText(e.target.value)}
                placeholder="Type your reply..."
                rows={6}
                className="mt-2 w-full rounded-lg border border-slate-300 p-3 text-sm text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
              />
              <div className="mt-3 flex gap-2">
                <Button
                  size="sm"
                  onClick={handleReply}
                  disabled={sending || !replyText.trim()}
                >
                  {sending ? "Sending..." : "Send reply"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setReplyOpen(false);
                    setReplyText("");
                  }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      )}
    </DashboardPageLayout>
  );
}
