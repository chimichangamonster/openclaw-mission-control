"use client";

export const dynamic = "force-dynamic";

import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import {
  Archive,
  ArrowLeft,
  Mail,
  Reply,
  Tag,
} from "lucide-react";

import { useAuth } from "@/auth/clerk";
import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { Button } from "@/components/ui/button";
import {
  type EmailMessage,
  fetchEmailMessage,
  archiveEmail,
  replyToEmail,
  updateEmailMessage,
} from "@/lib/email-api";
export default function EmailMessagePage() {
  const { isSignedIn } = useAuth();
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();

  const messageId = params.messageId as string;
  const accountId = searchParams.get("account") ?? "";

  const [message, setMessage] = useState<EmailMessage | null>(null);
  const [loading, setLoading] = useState(true);
  const [replyOpen, setReplyOpen] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);

  const loadMessage = useCallback(async () => {
    if (!accountId || !messageId) return;
    try {
      setLoading(true);
      const msg = await fetchEmailMessage(accountId, messageId);
      setMessage(msg);
      if (!msg.is_read) {
        await updateEmailMessage(accountId, messageId, { is_read: true });
      }
    } catch {
      setMessage(null);
    } finally {
      setLoading(false);
    }
  }, [accountId, messageId]);

  useEffect(() => {
    if (isSignedIn) loadMessage();
  }, [isSignedIn, loadMessage]);

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
                <span className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600">
                  {message.triage_status}
                </span>
                {message.triage_category ? (
                  <span className="rounded bg-blue-100 px-2 py-1 text-xs font-medium text-blue-700">
                    {message.triage_category}
                  </span>
                ) : null}
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
