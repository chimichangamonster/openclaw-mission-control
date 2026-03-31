"use client";

export const dynamic = "force-dynamic";

import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  HelpCircle,
  Mail,
  MessageSquare,
  Shield,
  Users,
  Zap,
  FileText,
  Settings,
  Eye,
  BarChart3,
} from "lucide-react";

import { DashboardPageLayout } from "@/components/templates/DashboardPageLayout";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ */
/*  Accordion                                                          */
/* ------------------------------------------------------------------ */

function Accordion({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-[color:var(--border)] rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-[color:var(--text)] hover:bg-[color:var(--surface-muted)] transition"
      >
        {title}
        {open ? (
          <ChevronDown className="h-4 w-4 text-[color:var(--text-quiet)]" />
        ) : (
          <ChevronRight className="h-4 w-4 text-[color:var(--text-quiet)]" />
        )}
      </button>
      {open && (
        <div className="px-4 pb-4 text-sm text-[color:var(--text-muted)] leading-relaxed">
          {children}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Section card                                                       */
/* ------------------------------------------------------------------ */

function SectionCard({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-[color:var(--border)] bg-[color:var(--surface)] p-6">
      <div className="flex items-center gap-3 mb-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[color:var(--accent-soft)]">
          <Icon className="h-5 w-5 text-[color:var(--accent-strong)]" />
        </div>
        <h2 className="text-lg font-semibold text-[color:var(--text)]">{title}</h2>
      </div>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Role guide data                                                    */
/* ------------------------------------------------------------------ */

const roles = [
  {
    name: "Owner",
    who: "Business owner, CEO, GM",
    can: "Everything — settings, billing, invite members, delete org, manage API keys",
  },
  {
    name: "Admin",
    who: "Office manager, ops lead",
    can: "Org settings, API keys, invite members, manage access, connect integrations",
  },
  {
    name: "Operator",
    who: "Project manager, dispatcher",
    can: "Manage jobs, invoices, documents, day-to-day workflows",
  },
  {
    name: "Member",
    who: "Field crew, team members",
    can: "Use enabled features, chat with the AI, upload documents, view dashboards",
  },
  {
    name: "Viewer",
    who: "Accountant, external advisor",
    can: "Read-only access to dashboards and reports",
  },
];

/* ------------------------------------------------------------------ */
/*  FAQ data                                                           */
/* ------------------------------------------------------------------ */

const faqGeneral = [
  {
    q: "What is The Claw?",
    a: "The Claw is your AI business assistant. It lives in the Chat page and can help with invoicing, document processing, scheduling, competitor research, and more. It knows your cost codes, your team, and your projects. Think of it as a team member who never sleeps and never forgets.",
  },
  {
    q: "How do I talk to the AI?",
    a: "Go to the Chat page from the sidebar. Type your request in plain English — no special commands needed. You can also reach the AI through WhatsApp, Slack, or Microsoft Teams if your org has those channels configured.",
  },
  {
    q: "Is my data shared with other companies?",
    a: "No. Every organization gets a completely separate AI instance, database partition, and encryption keys. Your data is isolated and cannot be accessed by other organizations on the platform.",
  },
  {
    q: "What AI models are used? Where does my data go?",
    a: "By default, the platform uses commercial AI models through OpenRouter (e.g., Claude, DeepSeek). These providers do not train on your data. If your organization has data residency or compliance requirements, you can use your own AI provider through the BYOK (Bring Your Own Key) feature in Org Settings.",
  },
];

const faqFeatures = [
  {
    q: "How do I create an invoice?",
    a: 'In Chat, ask The Claw: "Create an invoice for [client name], [line items and amounts]." It will generate a branded PDF with your org logo and terms. You can also create invoices from the Bookkeeping section if enabled.',
  },
  {
    q: "How do I upload a document?",
    a: "In Chat, click the paperclip icon or paste an image/PDF directly. The AI will read the document, extract key data, and classify it (invoice, receipt, field report, timesheet, etc.). You can also use the Documents page.",
  },
  {
    q: "How do cost codes work?",
    a: "Cost codes are configured during onboarding and stored in your org settings. When the AI processes field reports or timesheets, it maps entries to your cost code structure automatically. Ask your admin to update cost codes in Org Settings if needed.",
  },
  {
    q: "How do I connect my email or calendar?",
    a: "Go to Org Settings. Under Email Integrations, connect your Outlook or Zoho account via OAuth. For calendar, connect Google Calendar or Outlook Calendar. Each team member can connect their own account and control visibility (shared or private).",
  },
  {
    q: "What are feature flags and why are some features hidden?",
    a: "Feature flags control which capabilities are available to your organization. Your admin enables only the features relevant to your business — this keeps the interface clean and focused. If you need a feature that's not visible, ask your org admin to enable it in Org Settings.",
  },
  {
    q: "How do equipment maintenance alerts work?",
    a: "When configured, the system tracks equipment hour meters and maintenance intervals. It alerts you before service is due based on manufacturer schedules or your mechanic's recommendations. Upload service records to keep the history current.",
  },
];

const faqAccess = [
  {
    q: "How do I invite team members?",
    a: "Go to Organization in the sidebar. Click Invite Member, enter their email, and select a role. They'll receive an invite link to create their account and join your org.",
  },
  {
    q: "What can each role do?",
    a: "Owner: full control. Admin: manage settings and members. Operator: manage workflows and data. Member: use features, chat, upload docs. Viewer: read-only access. Start everyone as Member and promote as needed.",
  },
  {
    q: "How do I change my API key?",
    a: "Go to Org Settings > API Keys. Only admins and owners can view or change API keys. Keys are encrypted at rest and never displayed in full after being saved.",
  },
  {
    q: "How is my data encrypted?",
    a: "All sensitive data (API keys, OAuth tokens, wallet keys) is encrypted at rest using AES-256-GCM — the same standard used by banks. Encryption keys are derived using HKDF-SHA256 and support rotation.",
  },
];

const faqTroubleshooting = [
  {
    q: "The AI isn't responding — what do I do?",
    a: 'First, check the system status indicator at the bottom of the sidebar. If it shows "degraded," there may be a temporary issue. Try refreshing the page. If the problem persists, the AI\'s context window may be full — click the Compact button in chat to summarize the conversation and free up space.',
  },
  {
    q: "I can't see a feature that should be there",
    a: "Features are controlled by feature flags and role permissions. If a sidebar item is missing, either: (1) the feature isn't enabled for your org — ask your admin, or (2) your role doesn't have access — check with your org owner.",
  },
  {
    q: "How do I reset the AI's conversation?",
    a: 'In Chat, click the Clear button (trash icon) to reset the conversation completely. Use Compact (compress icon) to summarize without losing context. Clear is useful when the AI seems confused or stuck on an old topic.',
  },
];

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function HelpPage() {
  const [activeTab, setActiveTab] = useState<"start" | "faq" | "contact">("start");

  const tabs = [
    { id: "start" as const, label: "Getting Started", icon: Zap },
    { id: "faq" as const, label: "FAQ", icon: HelpCircle },
    { id: "contact" as const, label: "Contact Support", icon: Mail },
  ];

  return (
    <DashboardPageLayout
      signedOut={{
        message: "Sign in to access help and support.",
        forceRedirectUrl: "/help",
        signUpForceRedirectUrl: "/help",
      }}
      title="Help & Support"
      description="Guides, answers, and support for your VantageClaw platform."
    >
      {/* Tab navigation */}
      <div className="flex gap-1 rounded-lg bg-[color:var(--surface-muted)] p-1 mb-6 w-fit">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition",
              activeTab === tab.id
                ? "bg-[color:var(--surface)] text-[color:var(--text)] shadow-sm"
                : "text-[color:var(--text-muted)] hover:text-[color:var(--text)]",
            )}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* ---- Getting Started ---- */}
      {activeTab === "start" && (
        <div className="space-y-6 max-w-4xl">
          <p className="text-sm text-[color:var(--text-muted)]">
            Quick start guides based on your role. Find what you need to get up and running.
          </p>

          <SectionCard icon={Users} title="Roles & Permissions">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[color:var(--border)]">
                    <th className="text-left py-2 pr-4 font-medium text-[color:var(--text)]">Role</th>
                    <th className="text-left py-2 pr-4 font-medium text-[color:var(--text)]">Who gets it</th>
                    <th className="text-left py-2 font-medium text-[color:var(--text)]">What they can do</th>
                  </tr>
                </thead>
                <tbody>
                  {roles.map((role) => (
                    <tr key={role.name} className="border-b border-[color:var(--border)] last:border-0">
                      <td className="py-2.5 pr-4 font-medium text-[color:var(--text)]">{role.name}</td>
                      <td className="py-2.5 pr-4 text-[color:var(--text-muted)]">{role.who}</td>
                      <td className="py-2.5 text-[color:var(--text-muted)]">{role.can}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>

          <SectionCard icon={MessageSquare} title="Using the AI Assistant">
            <div className="space-y-3 text-sm text-[color:var(--text-muted)]">
              <p>
                <strong className="text-[color:var(--text)]">Chat</strong> — Go to Chat in the sidebar. Type your request in plain English. The AI knows your org's cost codes, crew, projects, and documents.
              </p>
              <p>
                <strong className="text-[color:var(--text)]">File uploads</strong> — Click the paperclip icon in chat to attach PDFs, images, or spreadsheets. The AI will read and extract data from them automatically.
              </p>
              <p>
                <strong className="text-[color:var(--text)]">Context management</strong> — If the AI seems confused, use the Compact button to summarize the conversation, or Clear to start fresh.
              </p>
              <p>
                <strong className="text-[color:var(--text)]">Multi-channel</strong> — The same AI is available through WhatsApp, Slack, or Teams if configured. Use the web dashboard for sensitive queries; use messaging apps for team ops.
              </p>
            </div>
          </SectionCard>

          <SectionCard icon={FileText} title="Quick Start by Role">
            <div className="space-y-4">
              <div>
                <h3 className="font-medium text-[color:var(--text)] mb-1">Owners & Admins</h3>
                <ol className="list-decimal list-inside space-y-1 text-sm text-[color:var(--text-muted)]">
                  <li>Go to <strong>Organization</strong> to invite your team members</li>
                  <li>Go to <strong>Org Settings</strong> to configure API keys and enable features</li>
                  <li>Connect your email and calendar under Org Settings integrations</li>
                  <li>Try the Chat — ask The Claw to create an invoice or process a document</li>
                  <li>Review the <strong>Audit Log</strong> to see platform activity</li>
                </ol>
              </div>
              <div>
                <h3 className="font-medium text-[color:var(--text)] mb-1">Operators</h3>
                <ol className="list-decimal list-inside space-y-1 text-sm text-[color:var(--text-muted)]">
                  <li>Go to <strong>Chat</strong> — ask The Claw about your projects, costs, or schedule</li>
                  <li>Upload documents (field reports, invoices, timesheets) via the paperclip in chat</li>
                  <li>Check <strong>Boards</strong> for project tasks and workflows</li>
                  <li>Use <strong>Documents</strong> to find generated reports and files</li>
                </ol>
              </div>
              <div>
                <h3 className="font-medium text-[color:var(--text)] mb-1">Members</h3>
                <ol className="list-decimal list-inside space-y-1 text-sm text-[color:var(--text-muted)]">
                  <li>Go to <strong>Chat</strong> and say hello — The Claw will introduce itself</li>
                  <li>Upload photos of receipts, reports, or timesheets by pasting or using the paperclip</li>
                  <li>Ask questions: "What's on my schedule?", "Show project costs", "Create a report"</li>
                </ol>
              </div>
              <div>
                <h3 className="font-medium text-[color:var(--text)] mb-1">Viewers</h3>
                <ol className="list-decimal list-inside space-y-1 text-sm text-[color:var(--text-muted)]">
                  <li>Browse the <strong>Dashboard</strong> for an overview of activity</li>
                  <li>Check <strong>Boards</strong> for project status (read-only)</li>
                  <li>View <strong>Documents</strong> for generated reports and files</li>
                </ol>
              </div>
            </div>
          </SectionCard>

          <SectionCard icon={Shield} title="Security & Privacy">
            <div className="space-y-3 text-sm text-[color:var(--text-muted)]">
              <p>
                <strong className="text-[color:var(--text)]">Data isolation</strong> — Every organization has its own AI instance, database partition, and encryption keys. No data is shared between organizations.
              </p>
              <p>
                <strong className="text-[color:var(--text)]">Encryption</strong> — All sensitive data is encrypted at rest using AES-256-GCM (bank-grade). API keys, OAuth tokens, and credentials are never stored in plaintext.
              </p>
              <p>
                <strong className="text-[color:var(--text)]">Audit trail</strong> — Every action is logged. Admins and owners can review the full audit log from the sidebar.
              </p>
              <p>
                <strong className="text-[color:var(--text)]">AI data usage</strong> — Commercial AI providers used by this platform do not train on your data. Your conversations and documents remain private.
              </p>
            </div>
          </SectionCard>
        </div>
      )}

      {/* ---- FAQ ---- */}
      {activeTab === "faq" && (
        <div className="space-y-6 max-w-4xl">
          <SectionCard icon={HelpCircle} title="General">
            <div className="space-y-2">
              {faqGeneral.map((item) => (
                <Accordion key={item.q} title={item.q}>
                  <p>{item.a}</p>
                </Accordion>
              ))}
            </div>
          </SectionCard>

          <SectionCard icon={Settings} title="Features">
            <div className="space-y-2">
              {faqFeatures.map((item) => (
                <Accordion key={item.q} title={item.q}>
                  <p>{item.a}</p>
                </Accordion>
              ))}
            </div>
          </SectionCard>

          <SectionCard icon={Shield} title="Access & Security">
            <div className="space-y-2">
              {faqAccess.map((item) => (
                <Accordion key={item.q} title={item.q}>
                  <p>{item.a}</p>
                </Accordion>
              ))}
            </div>
          </SectionCard>

          <SectionCard icon={BarChart3} title="Troubleshooting">
            <div className="space-y-2">
              {faqTroubleshooting.map((item) => (
                <Accordion key={item.q} title={item.q}>
                  <p>{item.a}</p>
                </Accordion>
              ))}
            </div>
          </SectionCard>
        </div>
      )}

      {/* ---- Contact Support ---- */}
      {activeTab === "contact" && (
        <div className="space-y-6 max-w-4xl">
          <SectionCard icon={Mail} title="Contact Us">
            <div className="space-y-4 text-sm text-[color:var(--text-muted)]">
              <p>
                Need help with something not covered in the FAQ? Reach out and we'll get back to you.
              </p>

              <div className="rounded-lg border border-[color:var(--border)] bg-[color:var(--surface-muted)] p-4 space-y-3">
                <div className="flex items-center gap-3">
                  <Mail className="h-5 w-5 text-[color:var(--accent-strong)]" />
                  <div>
                    <p className="font-medium text-[color:var(--text)]">Email Support</p>
                    <a
                      href="mailto:support@vantageclaw.ai"
                      className="text-[color:var(--accent-strong)] hover:underline"
                    >
                      support@vantageclaw.ai
                    </a>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <Eye className="h-5 w-5 text-[color:var(--accent-strong)]" />
                  <div>
                    <p className="font-medium text-[color:var(--text)]">Business Hours</p>
                    <p>Monday - Friday, 8:00 AM - 5:00 PM Mountain Time (MT)</p>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <Zap className="h-5 w-5 text-[color:var(--accent-strong)]" />
                  <div>
                    <p className="font-medium text-[color:var(--text)]">Response Time</p>
                    <p>We aim to respond within 1 business day.</p>
                  </div>
                </div>
              </div>

              <div>
                <h3 className="font-medium text-[color:var(--text)] mb-2">Before reaching out, try:</h3>
                <ul className="list-disc list-inside space-y-1">
                  <li>Checking the FAQ tab above</li>
                  <li>Asking The Claw in Chat — it can help with most platform questions</li>
                  <li>Refreshing the page if something looks broken</li>
                  <li>Checking the system status indicator at the bottom of the sidebar</li>
                </ul>
              </div>

              <div>
                <h3 className="font-medium text-[color:var(--text)] mb-2">When contacting us, include:</h3>
                <ul className="list-disc list-inside space-y-1">
                  <li>Your organization name</li>
                  <li>What you were trying to do</li>
                  <li>What happened (or didn't happen)</li>
                  <li>Screenshots if applicable</li>
                </ul>
              </div>
            </div>
          </SectionCard>
        </div>
      )}
    </DashboardPageLayout>
  );
}
