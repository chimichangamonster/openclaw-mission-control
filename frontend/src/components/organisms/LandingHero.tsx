"use client";

import Link from "next/link";

import {
  SignInButton,
  SignedIn,
  SignedOut,
  isClerkEnabled,
} from "@/auth/clerk";

const ArrowIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 16 16"
    fill="none"
    aria-hidden="true"
  >
    <path
      d="M6 12L10 8L6 4"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

export function LandingHero() {
  const clerkEnabled = isClerkEnabled();

  return (
    <>
      {/* Hero */}
      <section className="hero">
        <div className="hero-content">
          <div className="hero-label">AI Operations for Canadian SMBs</div>
          <h1>
            Tell it to <span className="hero-highlight">do the work.</span>
            <br />
            It does.
          </h1>
          <p>
            VantageClaw is an AI assistant configured for your business. It
            reads your documents, drafts your invoices, monitors your
            competitors, manages your schedule, and waits for your approval
            before anything goes out. Your data stays on your server.
          </p>

          <div className="hero-actions">
            <SignedOut>
              {clerkEnabled ? (
                <SignInButton
                  mode="modal"
                  forceRedirectUrl="/onboarding"
                  signUpForceRedirectUrl="/onboarding"
                >
                  <button type="button" className="btn-large primary">
                    Sign In <ArrowIcon />
                  </button>
                </SignInButton>
              ) : (
                <Link href="/boards" className="btn-large primary">
                  Get Started <ArrowIcon />
                </Link>
              )}
            </SignedOut>
            <SignedIn>
              <Link href="/dashboard" className="btn-large primary">
                Dashboard <ArrowIcon />
              </Link>
            </SignedIn>
          </div>

          <div className="hero-features">
            {[
              "Your Data, Your Server",
              "Configured for Your Industry",
              "Human Approves Everything",
              "48 Business Skills",
            ].map((label) => (
              <div key={label} className="hero-feature">
                <div className="feature-icon">&#10003;</div>
                <span>{label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* What it looks like in practice */}
        <div className="command-surface">
          <div className="surface-header">
            <div className="surface-title">Your AI Assistant</div>
            <div className="live-indicator">
              <div className="live-dot" />
              LIVE
            </div>
          </div>
          <div className="surface-subtitle">
            <h3>What it actually does.</h3>
            <p>
              Not a chatbot. An assistant that does the work.
            </p>
          </div>
          <div className="metrics-row">
            {[
              { label: "Business Skills", value: "48" },
              { label: "Industry Templates", value: "4" },
              { label: "Setup Time", value: "1 day" },
            ].map((item) => (
              <div key={item.label} className="metric">
                <div className="metric-value">{item.value}</div>
                <div className="metric-label">{item.label}</div>
              </div>
            ))}
          </div>
          <div className="surface-content">
            <div className="content-section">
              <h4>You say</h4>
              {[
                "\"Invoice ABC Construction for 40 hours at $150/hr\"",
                "\"What did our competitors post this week?\"",
                "\"Process this field report\"",
                "\"Book a meeting with Sarah for Thursday\"",
              ].map((title) => (
                <div key={title} className="status-item">
                  <div className="status-icon progress">&#9670;</div>
                  <div className="status-item-content">
                    <div className="status-item-title">{title}</div>
                  </div>
                </div>
              ))}
            </div>

            <div className="content-section">
              <h4>It does</h4>
              {[
                "Generates a branded PDF invoice, ready to send",
                "Scans websites, social media, news \u2014 delivers a summary",
                "Reads the PDF, extracts data, classifies, flags issues",
                "Checks both calendars, sends the invite",
              ].map((title) => (
                <div key={title} className="status-item">
                  <div className="status-icon progress">&#9670;</div>
                  <div className="status-item-content">
                    <div className="status-item-title">{title}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* What You Get */}
      <section className="features-section" id="capabilities">
        <div className="features-grid">
          {[
            {
              title: "Your own AI assistant",
              description:
                "A dedicated AI bot in your own messaging channel, configured with your business name, your industry language, your cost codes, and your workflows. It knows your business.",
            },
            {
              title: "48 business skills, ready to go",
              description:
                "Invoicing, document processing, expense capture, scheduling, competitor intelligence, proposals, social media, bookkeeping \u2014 pre-built and configurable for your industry.",
            },
            {
              title: "You control costs",
              description:
                "Host on your own server ($30\u201350/mo) or a Mac Mini at your office. Bring your own AI API key. No markup on infrastructure. Budget caps prevent surprise bills.",
            },
            {
              title: "Documents in, data out",
              description:
                "Upload any document \u2014 PDF, photo of a receipt, spreadsheet. The AI reads it, extracts the data, classifies it, and routes it to the right workflow automatically.",
            },
            {
              title: "Your data never leaves your server",
              description:
                "Sensitive information is stripped before reaching AI models. Everything is encrypted at rest. Full audit trail. Canadian server option for data residency.",
            },
            {
              title: "AI proposes, you approve",
              description:
                "Nothing goes out without your say. Email sends, invoice deliveries, and external actions all require your explicit approval. The AI drafts \u2014 you decide.",
            },
            {
              title: "Configured for your industry",
              description:
                "Industry-specific templates for construction, waste management, staffing, and professional services. New verticals built during onboarding as needed.",
            },
            {
              title: "Runs on a schedule",
              description:
                "Morning briefings, weekly competitor scans, invoice reminders, deadline alerts \u2014 your AI works while you sleep. Unlike ChatGPT, it doesn\u2019t wait for you to ask.",
            },
          ].map((feature, idx) => (
            <div key={feature.title} className="feature-card">
              <div className="feature-number">
                {String(idx + 1).padStart(2, "0")}
              </div>
              <h3>{feature.title}</h3>
              <p>{feature.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Use Cases by Industry */}
      <section className="trust-section" id="use-cases">
        <div className="trust-header">
          <h2>What&apos;s possible for your industry</h2>
          <p>
            Included capabilities ship with your $1,000 setup — existing skills,
            just configured for your business. Custom workflows are built for
            your specific needs at $150/hr and plug directly into the same
            platform.
          </p>
        </div>

        {/* Industry sections */}
        {[
          {
            industry: "Any Small Business",
            icon: "&#127970;",
            included: [
              { title: "Email triage", text: "AI prioritizes your inbox, summarizes threads, and drafts replies for your approval. Never miss a critical email buried under newsletters." },
              { title: "Expense classification", text: "Photograph a receipt or forward an invoice. AI extracts vendor, amount, and line items, then classifies using your cost codes. No more accountant rework." },
              { title: "Invoice generation", text: "Describe the work in conversation. AI generates a branded PDF invoice with line items, tax, and payment terms." },
              { title: "Follow-up reminders", text: "Track who hasn\u2019t responded to proposals, invoices, or requests. AI drafts nudge emails for your approval." },
              { title: "Meeting prep", text: "Research a company before a call. AI generates a brief with their background, recent news, and a tailored call agenda." },
              { title: "Weekly summary reports", text: "What happened this week, what\u2019s overdue, what\u2019s coming up next \u2014 generated automatically from your activity." },
              { title: "Social media drafting", text: "AI drafts posts based on your business updates. Review and approve before publishing. Never auto-posted." },
              { title: "Customer follow-up", text: "3 months since their last service? AI flags it and drafts a check-in email. You review and send." },
              { title: "Document organization", text: "Upload a batch of files. AI classifies each one (invoice, contract, report, receipt) and extracts key metadata." },
              { title: "Scheduling coordination", text: "AI resolves contact names to emails, checks calendar availability, and drafts meeting invites with agendas." },
            ],
            custom: [],
          },
          {
            industry: "Sales & Consulting",
            icon: "&#128188;",
            included: [
              { title: "Lead qualification", text: "Mention a prospect and the AI scores them against your ideal client profile across 8 factors. Hot, warm, cool, or not a fit \u2014 with reasoning." },
              { title: "Proposal drafting", text: "AI generates a statement of work with two pricing options, scope boundaries, and an out-of-scope section to prevent scope creep." },
              { title: "Competitor research", text: "Weekly scans of competitor websites, news mentions, and social media. Summarized into a brief you can act on." },
              { title: "Pipeline tracking", text: "Where\u2019s each deal? What\u2019s been stale for 7+ days? AI monitors your pipeline and flags deals that need attention." },
              { title: "Discovery call prep", text: "AI researches the prospect\u2019s company, tech stack, recent news, and generates a tailored call agenda with post-call notes template." },
            ],
            custom: [],
          },
          {
            industry: "Construction & Trades",
            icon: "&#127959;",
            included: [
              { title: "Job cost tracking", text: "Expenses mapped to projects and cost codes automatically. Know your margins in real-time, not three months after the job." },
              { title: "Field report processing", text: "Upload a photo or PDF from the field. AI extracts data, classifies the document, and routes it to the right workflow." },
            ],
            custom: [
              { title: "Bid preparation", text: "AI reads project specs, extracts quantities and scope, and drafts bids using your historical pricing. Estimator verifies takeoff, PM reviews and submits." },
              { title: "Subcontractor credential monitoring", text: "Track insurance, WCB, and COR expiry dates. AI alerts you before credentials lapse so you\u2019re never caught with an uncovered sub on site." },
              { title: "Safety document classification", text: "Upload safety docs and the AI maps them to COR audit elements. Know exactly which compliance requirements are covered and where the gaps are." },
              { title: "Change order detection", text: "Client sends a revised drawing. AI compares to the original spec and flags what changed \u2014 dimensions, materials, quantities \u2014 and estimates the cost impact." },
            ],
          },








          {
            industry: "Developers & Technical Teams",
            icon: "&#128187;",
            included: [
              { title: "Model A/B testing", text: "Run the same prompt through Claude, GPT, DeepSeek, and Gemini. Compare output quality, latency, and cost. Pick the best model for each task type." },
              { title: "Multi-model pipelines", text: "Cheap model extracts data, mid-tier validates and structures, expensive model makes the final decision. Each step uses the right tool for the job." },
              { title: "Cost simulation", text: "Test a workflow against 300+ model pricing tiers before deploying to production. Know what a 1,000-user deployment costs before you commit." },
              { title: "Prompt versioning", text: "Skills are markdown files, version controlled in git. Roll back a bad prompt like you\u2019d roll back code. Full history of what changed and when." },
              { title: "Agent observability", text: "Every LLM call logged with model, token count, latency, and cost. Prometheus metrics and Grafana dashboards included out of the box." },
            ],
            custom: [],
          },
        ].map((section) => (
          <div key={section.industry} style={{ marginBottom: "3rem" }}>
            <h3
              style={{
                fontSize: "1.5rem",
                fontWeight: 600,
                marginBottom: "1rem",
                paddingLeft: "1rem",
                borderLeft: "3px solid var(--accent, #3b82f6)",
              }}
            >
              <span
                dangerouslySetInnerHTML={{ __html: section.icon }}
                style={{ marginRight: "0.5rem" }}
              />{" "}
              {section.industry}
            </h3>
            {section.included.length > 0 && (
              <>
                <p style={{ fontSize: "0.8rem", color: "var(--text-muted, #94a3b8)", marginBottom: "0.75rem", paddingLeft: "1rem", fontWeight: 500 }}>
                  Included in setup
                </p>
                <div className="trust-grid" style={{ marginBottom: "1.5rem" }}>
                  {section.included.map((c) => (
                    <div key={c.title} className="trust-card">
                      <h3>{c.title}</h3>
                      <p>{c.text}</p>
                    </div>
                  ))}
                </div>
              </>
            )}
            {section.custom.length > 0 && (
              <>
                <p style={{ fontSize: "0.8rem", color: "var(--accent, #3b82f6)", marginBottom: "0.75rem", paddingLeft: "1rem", fontWeight: 500 }}>
                  Custom development &mdash; $150/hr &mdash; scoped during discovery
                </p>
                <div className="trust-grid">
                  {section.custom.map((c) => (
                    <div key={c.title} className="trust-card" style={{ borderColor: "var(--accent, #3b82f6)", borderWidth: "1px", borderStyle: "solid", opacity: 0.85 }}>
                      <h3>{c.title}</h3>
                      <p>{c.text}</p>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        ))}
      </section>

      {/* How It Works */}
      <section className="pricing-section" id="pricing">
        <div className="pricing-header">
          <h2>How it works</h2>
          <p>
            You tell us about your business. We configure your AI assistant.
            You start using it.
          </p>
        </div>
        <div className="pricing-grid">
          {[
            {
              tier: "You Host",
              price: "$1,000",
              period: " setup",
              description: "Your own cloud server \u2014 you control everything",
              features: [
                "$1,000 one-time setup fee",
                "Cloud VPS: $30\u201350/mo (you pay provider directly)",
                "AI API: usage-based (you pay OpenRouter directly)",
                "Your data stays on your server",
                "Your own Discord server + AI bot",
                "Full configuration: discovery, SOUL.md, skills, integrations",
                "Optional monthly retainer for ongoing support",
              ],
            },
            {
              tier: "Mac Mini",
              price: "$1,000",
              period: " setup",
              highlight: true,
              description: "Run it at your office \u2014 near-zero recurring cost",
              features: [
                "$1,000 one-time setup fee",
                "No monthly server cost \u2014 runs on your hardware",
                "AI API: usage-based (you pay OpenRouter directly)",
                "Local AI for basic tasks (optional, near-zero cost)",
                "Your own Discord server + AI bot",
                "Full configuration: discovery, SOUL.md, skills, integrations",
                "Optional monthly retainer for ongoing support",
              ],
            },
            {
              tier: "We Host",
              price: "$250",
              period: "/mo",
              description: "We run everything on Canadian infrastructure",
              features: [
                "Setup fee included",
                "Dedicated Canadian server",
                "AI costs included in monthly price",
                "Monitoring and maintenance included",
                "Your own Discord server + AI bot",
                "Priority support",
              ],
            },
          ].map((plan) => (
            <div
              key={plan.tier}
              className={`pricing-card ${plan.highlight ? "pricing-highlight" : ""}`}
            >
              <div className="pricing-card-header">
                <h3>{plan.tier}</h3>
                <div className="pricing-amount">
                  <span className="pricing-price">{plan.price}</span>
                  <span className="pricing-period">{plan.period}</span>
                </div>
                <p className="pricing-description">{plan.description}</p>
              </div>
              <ul className="pricing-features">
                {plan.features.map((f) => (
                  <li key={f}>
                    <span className="pricing-check">&#10003;</span>
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="cta-section">
        <div className="cta-content">
          <h2>Ready to put AI to work?</h2>
          <p>
            Sign in to see the platform, or reach out to get your business
            configured — info@vantagesolutions.ca
          </p>
          <div className="cta-actions">
            <SignedOut>
              {clerkEnabled ? (
                <SignInButton
                  mode="modal"
                  forceRedirectUrl="/onboarding"
                  signUpForceRedirectUrl="/onboarding"
                >
                  <button type="button" className="btn-large white">
                    Sign In <ArrowIcon />
                  </button>
                </SignInButton>
              ) : (
                <Link href="/boards" className="btn-large white">
                  Get Started
                </Link>
              )}
            </SignedOut>
            <SignedIn>
              <Link href="/dashboard" className="btn-large white">
                Dashboard <ArrowIcon />
              </Link>
            </SignedIn>
          </div>
        </div>
      </section>
    </>
  );
}
