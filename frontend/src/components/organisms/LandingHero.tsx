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
              { label: "Industries", value: "17" },
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
                "A dedicated AI bot in your own Discord server, configured with your business name, your industry language, your cost codes, and your workflows. It knows your business.",
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
                "17 industry-specific templates: construction, waste management, staffing, healthcare, professional services, manufacturing, agriculture, and more.",
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
            industry: "Millwork & Custom Fabrication",
            icon: "&#129692;",
            included: [
              { title: "Job status updates", text: "Log progress in chat. AI drafts client update emails: \u2018Cabinet install 60% complete, waiting on glass inserts from supplier. ETA Thursday.\u2019" },
            ],
            custom: [
              { title: "Spec sheet extraction", text: "Customer sends a drawing (photo, PDF, CAD screenshot). AI extracts dimensions, material, finish, hardware, and quantity into a structured cut list." },
              { title: "Quote generation from drawings", text: "From the extracted spec: \u20184 linear feet of white oak crown, mitered corners, satin finish\u2019 \u2014 AI drafts a quote using your rate sheet and material costs." },
              { title: "Material estimation", text: "AI calculates sheet goods, linear footage, and edge banding needed for a job \u2014 with waste factor included. No more manual takeoffs for standard items." },
              { title: "Change order detection", text: "Revised drawing comes in. AI compares to the original: \u2018Door width changed from 32\" to 36\", hinge count increased, adds $X to the quote.\u2019" },
              { title: "Shop drawing review", text: "Upload the shop drawing and the original spec. AI flags discrepancies: spec calls for soft-close hinges but drawing shows standard." },
            ],
          },
          {
            industry: "Retail",
            icon: "&#128722;",
            included: [
              { title: "Staff scheduling", text: "\u2018Draft next week\u2019s schedule \u2014 Sarah can\u2019t do Tuesdays, need 3 people Saturday.\u2019 AI generates it, you adjust and post." },
              { title: "Seasonal planning", text: "\u2018What did we order for Canada Day last year?\u2019 AI searches through uploaded docs and emails for historical context." },
              { title: "Promotional content", text: "AI drafts social posts and email campaigns for sales events. You review and approve \u2014 nothing goes out without your say." },
              { title: "Supplier communication", text: "Forward supplier emails. AI extracts pricing changes, compares to previous orders, and flags increases worth negotiating." },
            ],
            custom: [
              { title: "Supplier invoice reconciliation", text: "Upload the invoice and the PO. AI flags discrepancies: \u2018They billed 24 cases but your PO was for 20.\u2019 Catch billing errors before you pay." },
              { title: "Price comparison", text: "Upload a competitor\u2019s flyer (photo works). AI extracts prices, compares to yours, and flags where you\u2019re being undercut." },
              { title: "Customer complaint analysis", text: "Log complaints via email or chat. AI categorizes them (product, service, wait time) and spots patterns: \u201860% of complaints are Friday afternoon wait times.\u2019" },
              { title: "Loss prevention patterns", text: "Staff logs shrinkage and waste daily. AI identifies trends: \u2018Produce waste spikes every Monday \u2014 are weekend orders too large?\u2019" },
            ],
          },
          {
            industry: "Property Management",
            icon: "&#127968;",
            included: [
              { title: "Tenant communication", text: "AI drafts responses to maintenance requests, lease inquiries, and renewal notices. Property manager reviews tone and sends." },
              { title: "Maintenance request triage", text: "Tenant emails \u2018water under the sink.\u2019 AI categorizes as plumbing/urgent, drafts a work order with priority level and vendor suggestion." },
              { title: "Lease document extraction", text: "Upload a lease. AI extracts key dates \u2014 start, end, renewal deadline, rent increase schedule \u2014 and sets calendar reminders automatically." },
              { title: "Expense allocation", text: "Assign maintenance costs to the correct property and unit for tax reporting. AI categorizes from invoices and receipts." },
            ],
            custom: [],
          },
          {
            industry: "Healthcare & Clinics",
            icon: "&#127973;",
            included: [
              { title: "Appointment reminder drafting", text: "AI generates personalized reminders based on appointment type and patient history. Staff reviews and sends." },
              { title: "Referral letter generation", text: "\u2018Draft a referral to Dr. Smith for the knee issue.\u2019 AI generates a properly formatted referral letter for the physician to review and sign." },
            ],
            custom: [
              { title: "Patient intake form processing", text: "Upload handwritten intake forms. AI extracts and structures the data \u2014 name, DOB, medications, allergies \u2014 for staff to review and confirm." },
              { title: "Insurance pre-auth documentation", text: "AI drafts the pre-authorization narrative from clinical notes. Clinician reviews the language and submits. Cuts documentation time significantly." },
            ],
          },
          {
            industry: "Logistics & Trucking",
            icon: "&#128666;",
            included: [
              { title: "Carrier rate comparison", text: "Forward quotes from multiple carriers. AI compares rates, transit times, and reliability history to recommend the best option." },
            ],
            custom: [
              { title: "Trip log processing", text: "Upload driver logs. AI validates hours of service compliance, flags potential violations, and generates summary reports for dispatch." },
              { title: "Fuel expense analysis", text: "AI tracks fuel costs per route and per driver. Identifies inefficient routes, unusual consumption patterns, and cost-saving opportunities." },
              { title: "Load documentation", text: "Bill of lading extraction and cross-reference with delivery confirmations. AI flags missing signatures, discrepancies, and incomplete paperwork." },
            ],
          },
          {
            industry: "Restaurants & Food Service",
            icon: "&#127869;",
            included: [
              { title: "Health inspection prep", text: "AI generates a pre-inspection checklist based on your jurisdiction\u2019s specific requirements. Walk through it before the inspector arrives." },
              { title: "Staff certification tracking", text: "Food handler cards, WHMIS, first aid \u2014 AI monitors expiry dates across all staff and drafts renewal reminder emails." },
            ],
            custom: [
              { title: "Menu costing", text: "Upload supplier invoices and your menu. AI calculates food cost percentage per dish and flags items running below your margin target." },
              { title: "Waste analysis", text: "Log daily waste by category. AI identifies trends: \u2018Soup waste spikes Wednesday \u2014 consider reducing the Thursday prep batch by 30%.\u2019" },
            ],
          },
          {
            industry: "Agriculture",
            icon: "&#127806;",
            included: [
              { title: "Equipment maintenance scheduling", text: "Upload equipment manuals. AI tracks service intervals per machine and flags upcoming maintenance before breakdowns happen." },
              { title: "Compliance documentation", text: "Organic certification, pesticide application logs, water usage records \u2014 AI organizes submissions and flags gaps before audit deadlines." },
            ],
            custom: [
              { title: "Crop log analysis", text: "Farmer logs observations \u2014 weather, pest sightings, yields, soil conditions. AI spots patterns across seasons that are invisible in raw data." },
              { title: "Market price monitoring", text: "AI summarizes commodity price trends from public data. Flags optimal sell windows and hold recommendations based on historical patterns." },
            ],
          },
          {
            industry: "Legal & Accounting Firms",
            icon: "&#9878;",
            included: [
              { title: "Time entry assistance", text: "Describe what you worked on in plain language. AI categorizes by client and matter code, calculates duration, and drafts the time entry." },
              { title: "Client intake processing", text: "New client emails their situation. AI drafts a conflict check summary, intake memo, and initial matter classification." },
            ],
            custom: [
              { title: "Document review prep", text: "Upload a contract. AI flags non-standard clauses, missing sections, and unusual terms \u2014 so the lawyer knows where to focus before reading 40 pages." },
              { title: "Deadline tracking", text: "AI monitors filing deadlines, limitation periods, and regulatory due dates extracted from uploaded documents. Alerts before anything lapses." },
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
                  Custom development &mdash; $150/hr
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
            configured — henry@vantagesolutions.ca
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
