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
          <h2>What it does for your industry</h2>
          <p>
            Every example below is a real capability — not a roadmap item. Your
            AI assistant reads documents, analyzes patterns, drafts outputs, and
            waits for your approval. You don&apos;t need to learn AI. You just
            describe what you need.
          </p>
        </div>

        {/* Industry sections */}
        {[
          {
            industry: "Any Small Business",
            icon: "&#127970;",
            cases: [
              {
                title: "Email triage",
                text: "AI prioritizes your inbox, summarizes threads, and drafts replies for your approval. Never miss a critical email buried under newsletters.",
              },
              {
                title: "Expense classification",
                text: "Photograph a receipt or forward an invoice. AI extracts vendor, amount, and line items, then classifies using your cost codes. No more accountant rework.",
              },
              {
                title: "Invoice generation",
                text: "Describe the work in conversation. AI generates a branded PDF invoice with line items, tax, and payment terms.",
              },
              {
                title: "Follow-up reminders",
                text: "Track who hasn't responded to proposals, invoices, or requests. AI drafts nudge emails for your approval.",
              },
              {
                title: "Meeting prep",
                text: "Research a company before a call. AI generates a brief with their background, recent news, and a tailored call agenda.",
              },
              {
                title: "Weekly summary reports",
                text: "What happened this week, what's overdue, what's coming up next — generated automatically from your activity.",
              },
              {
                title: "Social media drafting",
                text: "AI drafts posts based on your business updates. Review and approve before publishing. Never auto-posted.",
              },
              {
                title: "Customer follow-up",
                text: "3 months since their last service? AI flags it and drafts a check-in email. You review and send.",
              },
              {
                title: "Document organization",
                text: "Upload a batch of files. AI classifies each one (invoice, contract, report, receipt) and extracts key metadata.",
              },
              {
                title: "Scheduling coordination",
                text: "AI resolves contact names to emails, checks calendar availability, and drafts meeting invites with agendas.",
              },
            ],
          },
          {
            industry: "Sales & Consulting",
            icon: "&#128188;",
            cases: [
              {
                title: "Lead qualification",
                text: "Mention a prospect and the AI scores them against your ideal client profile across 8 factors. Hot, warm, cool, or not a fit — with reasoning.",
              },
              {
                title: "Proposal drafting",
                text: "AI generates a statement of work with two pricing options, scope boundaries, and an out-of-scope section to prevent scope creep.",
              },
              {
                title: "Competitor research",
                text: "Weekly scans of competitor websites, news mentions, and social media. Summarized into a brief you can act on.",
              },
              {
                title: "Pipeline tracking",
                text: "Where's each deal? What's been stale for 7+ days? AI monitors your pipeline and flags deals that need attention.",
              },
              {
                title: "Discovery call prep",
                text: "AI researches the prospect's company, tech stack, recent news, and generates a tailored call agenda with post-call notes template.",
              },
            ],
          },
          {
            industry: "Construction & Trades",
            icon: "&#127959;",
            cases: [
              {
                title: "Job cost tracking",
                text: "Expenses mapped to projects and cost codes automatically. Know your margins in real-time, not three months after the job.",
              },
              {
                title: "Field report processing",
                text: "Upload a photo or PDF from the field. AI extracts data, classifies the document, and routes it to the right workflow.",
              },
              {
                title: "Bid preparation",
                text: "AI drafts bids from project specs using your historical pricing data and material costs. You review the numbers and send.",
              },
              {
                title: "Subcontractor credential monitoring",
                text: "Track insurance, WCB, and COR expiry dates. AI alerts you before credentials lapse so you're never caught with an uncovered sub on site.",
              },
              {
                title: "Safety document classification",
                text: "Upload safety docs and the AI maps them to COR audit elements. Know exactly which compliance requirements are covered and where the gaps are.",
              },
              {
                title: "Change order detection",
                text: "Client sends a revised drawing. AI compares to the original spec and flags what changed — dimensions, materials, quantities — and estimates the cost impact.",
              },
            ],
          },
          {
            industry: "Millwork & Custom Fabrication",
            icon: "&#129692;",
            cases: [
              {
                title: "Spec sheet extraction",
                text: "Customer sends a drawing (photo, PDF, CAD screenshot). AI extracts dimensions, material, finish, hardware, and quantity into a structured cut list.",
              },
              {
                title: "Quote generation from drawings",
                text: "From the extracted spec: '4 linear feet of white oak crown, mitered corners, satin finish' — AI drafts a quote using your rate sheet and material costs.",
              },
              {
                title: "Material estimation",
                text: "AI calculates sheet goods, linear footage, and edge banding needed for a job — with waste factor included. No more manual takeoffs for standard items.",
              },
              {
                title: "Change order detection",
                text: "Revised drawing comes in. AI compares to the original: 'Door width changed from 32\" to 36\", hinge count increased, adds $X to the quote.'",
              },
              {
                title: "Shop drawing review",
                text: "Upload the shop drawing and the original spec. AI flags discrepancies: spec calls for soft-close hinges but drawing shows standard.",
              },
              {
                title: "Job status updates",
                text: "Log progress in chat. AI drafts client update emails: 'Cabinet install 60% complete, waiting on glass inserts from supplier. ETA Thursday.'",
              },
            ],
          },
          {
            industry: "Retail",
            icon: "&#128722;",
            cases: [
              {
                title: "Supplier invoice reconciliation",
                text: "Upload the invoice and the PO. AI flags discrepancies: 'They billed 24 cases but your PO was for 20.' Catch billing errors before you pay.",
              },
              {
                title: "Price comparison",
                text: "Upload a competitor's flyer (photo works). AI extracts prices, compares to yours, and flags where you're being undercut.",
              },
              {
                title: "Customer complaint analysis",
                text: "Log complaints via email or chat. AI categorizes them (product, service, wait time) and spots patterns: '60% of complaints are Friday afternoon wait times.'",
              },
              {
                title: "Staff scheduling",
                text: "'Draft next week's schedule — Sarah can't do Tuesdays, need 3 people Saturday.' AI generates it, you adjust and post.",
              },
              {
                title: "Loss prevention patterns",
                text: "Staff logs shrinkage and waste daily. AI identifies trends: 'Produce waste spikes every Monday — are weekend orders too large?'",
              },
              {
                title: "Seasonal planning",
                text: "'What did we order for Canada Day last year?' AI searches through uploaded docs and emails for historical context.",
              },
              {
                title: "Promotional content",
                text: "AI drafts social posts and email campaigns for sales events. You review and approve — nothing goes out without your say.",
              },
              {
                title: "Supplier communication",
                text: "Forward supplier emails. AI extracts pricing changes, compares to previous orders, and flags increases worth negotiating.",
              },
            ],
          },
          {
            industry: "Compliance & Safety",
            icon: "&#128737;",
            cases: [
              {
                title: "COR audit gap detection",
                text: "AI monitors readiness across 14 COR elements, identifies missing evidence, and drafts corrective actions. Safety managers review and approve.",
              },
              {
                title: "Incident pattern analysis",
                text: "AI analyzes trends across incident reports and recommends engineering or administrative controls. 'Slip/fall incidents at loading dock up 40% — recommend anti-slip coating.'",
              },
              {
                title: "Training expiry monitoring",
                text: "Who needs recertification? AI tracks expiry dates and sends alerts before credentials lapse. Draft enrollment emails for approval.",
              },
              {
                title: "Document version tracking",
                text: "AI flags when regulations change and which of your documents reference outdated versions. Prioritizes what needs updating.",
              },
            ],
          },
          {
            industry: "Healthcare & Clinics",
            icon: "&#127973;",
            cases: [
              {
                title: "Patient intake form processing",
                text: "Upload handwritten intake forms. AI extracts and structures the data — name, DOB, medications, allergies — for staff to review and confirm.",
              },
              {
                title: "Appointment reminder drafting",
                text: "AI generates personalized reminders based on appointment type and patient history. Staff reviews and sends.",
              },
              {
                title: "Insurance pre-auth documentation",
                text: "AI drafts the pre-authorization narrative from clinical notes. Clinician reviews the language and submits. Cuts documentation time significantly.",
              },
              {
                title: "Referral letter generation",
                text: "'Draft a referral to Dr. Smith for the knee issue.' AI generates a properly formatted referral letter for the physician to review and sign.",
              },
            ],
          },
          {
            industry: "Property Management",
            icon: "&#127968;",
            cases: [
              {
                title: "Tenant communication",
                text: "AI drafts responses to maintenance requests, lease inquiries, and renewal notices. Property manager reviews tone and sends.",
              },
              {
                title: "Maintenance request triage",
                text: "Tenant emails 'water under the sink.' AI categorizes as plumbing/urgent, drafts a work order with priority level and vendor suggestion.",
              },
              {
                title: "Lease document extraction",
                text: "Upload a lease. AI extracts key dates — start, end, renewal deadline, rent increase schedule — and sets calendar reminders automatically.",
              },
              {
                title: "Expense allocation",
                text: "Assign maintenance costs to the correct property and unit for tax reporting. AI categorizes from invoices and receipts.",
              },
            ],
          },
          {
            industry: "Agriculture",
            icon: "&#127806;",
            cases: [
              {
                title: "Crop log analysis",
                text: "Farmer logs observations — weather, pest sightings, yields, soil conditions. AI spots patterns across seasons that are invisible in raw data.",
              },
              {
                title: "Equipment maintenance scheduling",
                text: "Upload equipment manuals. AI tracks service intervals per machine and flags upcoming maintenance before breakdowns happen.",
              },
              {
                title: "Market price monitoring",
                text: "AI summarizes commodity price trends from public data. Flags optimal sell windows and hold recommendations based on historical patterns.",
              },
              {
                title: "Compliance documentation",
                text: "Organic certification, pesticide application logs, water usage records — AI organizes submissions and flags gaps before audit deadlines.",
              },
            ],
          },
          {
            industry: "Logistics & Trucking",
            icon: "&#128666;",
            cases: [
              {
                title: "Trip log processing",
                text: "Upload driver logs. AI validates hours of service compliance, flags potential violations, and generates summary reports for dispatch.",
              },
              {
                title: "Fuel expense analysis",
                text: "AI tracks fuel costs per route and per driver. Identifies inefficient routes, unusual consumption patterns, and cost-saving opportunities.",
              },
              {
                title: "Load documentation",
                text: "Bill of lading extraction and cross-reference with delivery confirmations. AI flags missing signatures, discrepancies, and incomplete paperwork.",
              },
              {
                title: "Carrier rate comparison",
                text: "Forward quotes from multiple carriers. AI compares rates, transit times, and reliability history to recommend the best option.",
              },
            ],
          },
          {
            industry: "Legal & Accounting Firms",
            icon: "&#9878;",
            cases: [
              {
                title: "Time entry assistance",
                text: "Describe what you worked on in plain language. AI categorizes by client and matter code, calculates duration, and drafts the time entry.",
              },
              {
                title: "Document review prep",
                text: "Upload a contract. AI flags non-standard clauses, missing sections, and unusual terms — so the lawyer knows where to focus before reading 40 pages.",
              },
              {
                title: "Client intake processing",
                text: "New client emails their situation. AI drafts a conflict check summary, intake memo, and initial matter classification.",
              },
              {
                title: "Deadline tracking",
                text: "AI monitors filing deadlines, limitation periods, and regulatory due dates extracted from uploaded documents. Alerts before anything lapses.",
              },
            ],
          },
          {
            industry: "Restaurants & Food Service",
            icon: "&#127869;",
            cases: [
              {
                title: "Menu costing",
                text: "Upload supplier invoices and your menu. AI calculates food cost percentage per dish and flags items running below your margin target.",
              },
              {
                title: "Health inspection prep",
                text: "AI generates a pre-inspection checklist based on your jurisdiction's specific requirements. Walk through it before the inspector arrives.",
              },
              {
                title: "Staff certification tracking",
                text: "Food handler cards, WHMIS, first aid — AI monitors expiry dates across all staff and drafts renewal reminder emails.",
              },
              {
                title: "Waste analysis",
                text: "Log daily waste by category. AI identifies trends: 'Soup waste spikes Wednesday — consider reducing the Thursday prep batch by 30%.'",
              },
            ],
          },
          {
            industry: "Developers & Technical Teams",
            icon: "&#128187;",
            cases: [
              {
                title: "Model A/B testing",
                text: "Run the same prompt through Claude, GPT, DeepSeek, and Gemini. Compare output quality, latency, and cost. Pick the best model for each task type.",
              },
              {
                title: "Multi-model pipelines",
                text: "Cheap model extracts data, mid-tier validates and structures, expensive model makes the final decision. Each step uses the right tool for the job.",
              },
              {
                title: "Cost simulation",
                text: "Test a workflow against 300+ model pricing tiers before deploying to production. Know what a 1,000-user deployment costs before you commit.",
              },
              {
                title: "Prompt versioning",
                text: "Skills are markdown files, version controlled in git. Roll back a bad prompt like you'd roll back code. Full history of what changed and when.",
              },
              {
                title: "Agent observability",
                text: "Every LLM call logged with model, token count, latency, and cost. Prometheus metrics and Grafana dashboards included out of the box.",
              },
            ],
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
            <div className="trust-grid">
              {section.cases.map((c) => (
                <div key={c.title} className="trust-card">
                  <h3>{c.title}</h3>
                  <p>{c.text}</p>
                </div>
              ))}
            </div>
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
              price: "$30\u201350",
              period: "/mo server",
              description: "Your own cloud server + AI API key",
              features: [
                "Your data stays on your server",
                "Cloud VPS (OVH, DigitalOcean, Vultr)",
                "AI costs: $20\u201350/mo (pay-as-you-go)",
                "Your own Discord server + AI bot",
                "We configure everything for you",
              ],
            },
            {
              tier: "Mac Mini",
              price: "$0",
              period: "/mo server",
              highlight: true,
              description: "Run it at your office on your own hardware",
              features: [
                "Docker on Mac Mini at your location",
                "Local AI for basic tasks (near-zero cost)",
                "Cloud AI only for complex reasoning",
                "No recurring server costs",
                "Your own Discord server + AI bot",
                "We set it up for you",
              ],
            },
            {
              tier: "We Host",
              price: "$500",
              period: "/mo",
              description: "We run everything on Canadian infrastructure",
              features: [
                "Dedicated Canadian server",
                "AI costs included",
                "Monitoring and maintenance included",
                "Your own Discord server + AI bot",
                "Priority support",
                "Quarterly optimization reviews",
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
