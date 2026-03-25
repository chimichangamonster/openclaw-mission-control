"use client";

import Image from "next/image";
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
      <section className="hero">
        <div className="hero-content">
          <Image
            src="/logo.png"
            alt="VantageClaw"
            width={120}
            height={120}
            className="mx-auto mb-6 rounded-2xl shadow-lg"
          />
          <div className="hero-label">VantageClaw Mission Control</div>
          <h1>
            Command <span className="hero-highlight">autonomous work.</span>
            <br />
            Keep human oversight.
          </h1>
          <p>
            Track tasks, approvals, and agent health in one unified command
            center. Get real-time signals when work changes, without losing the
            thread of execution.
          </p>

          <div className="hero-actions">
            <SignedOut>
              {clerkEnabled ? (
                <>
                  <Link
                    href="https://vantageclaw.ai/consultation"
                    target="_blank"
                    rel="noreferrer"
                    className="btn-large primary"
                  >
                    Book a Demo <ArrowIcon />
                  </Link>
                  <SignInButton
                    mode="modal"
                    forceRedirectUrl="/onboarding"
                    signUpForceRedirectUrl="/onboarding"
                  >
                    <button type="button" className="btn-large secondary">
                      Sign In
                    </button>
                  </SignInButton>
                </>
              ) : (
                <>
                  <Link href="/boards" className="btn-large primary">
                    Get Started <ArrowIcon />
                  </Link>
                  <Link href="/boards/new" className="btn-large secondary">
                    Create Board
                  </Link>
                </>
              )}
            </SignedOut>

            <SignedIn>
              <Link href="/boards" className="btn-large primary">
                Open Boards <ArrowIcon />
              </Link>
              <Link href="/boards/new" className="btn-large secondary">
                Create Board
              </Link>
            </SignedIn>
          </div>

          <div className="hero-features">
            {["Agent-First Operations", "Approval Queues", "Live Signals"].map(
              (label) => (
                <div key={label} className="hero-feature">
                  <div className="feature-icon">✓</div>
                  <span>{label}</span>
                </div>
              ),
            )}
          </div>
        </div>

        <div className="command-surface">
          <div className="surface-header">
            <div className="surface-title">Command Surface</div>
            <div className="live-indicator">
              <div className="live-dot" />
              LIVE
            </div>
          </div>
          <div className="surface-subtitle">
            <h3>Ship work without losing the thread.</h3>
            <p>
              Tasks, approvals, and agent status stay synced across the board.
            </p>
          </div>
          <div className="metrics-row">
            {[
              { label: "Boards", value: "12" },
              { label: "Agents", value: "08" },
              { label: "Tasks", value: "46" },
            ].map((item) => (
              <div key={item.label} className="metric">
                <div className="metric-value">{item.value}</div>
                <div className="metric-label">{item.label}</div>
              </div>
            ))}
          </div>
          <div className="surface-content">
            <div className="content-section">
              <h4>Board — In Progress</h4>
              {[
                "Cut release candidate",
                "Triage approvals backlog",
                "Stabilize agent handoffs",
              ].map((title) => (
                <div key={title} className="status-item">
                  <div className="status-icon progress">⊙</div>
                  <div className="status-item-content">
                    <div className="status-item-title">{title}</div>
                  </div>
                </div>
              ))}
            </div>

            <div className="content-section">
              <h4>Approvals — 3 Pending</h4>
              {[
                { title: "Deploy window confirmed", status: "ready" as const },
                { title: "Copy reviewed", status: "waiting" as const },
                { title: "Security sign-off", status: "waiting" as const },
              ].map((item) => (
                <div key={item.title} className="approval-item">
                  <div className="approval-title">{item.title}</div>
                  <div className={`approval-badge ${item.status}`}>
                    {item.status}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div
            style={{
              padding: "2rem",
              borderTop: "1px solid var(--neutral-200)",
            }}
          >
            <div className="content-section">
              <h4>Signals — Updated Moments Ago</h4>
              {[
                { text: "Agent Delta moved task to review", time: "Now" },
                { text: "Growth Ops hit WIP limit", time: "5m" },
                { text: "Release pipeline stabilized", time: "12m" },
              ].map((signal) => (
                <div key={signal.text} className="signal-item">
                  <div className="signal-text">{signal.text}</div>
                  <div className="signal-time">{signal.time}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="features-section" id="capabilities">
        <div className="features-grid">
          {[
            {
              title: "Multi-agent fleet",
              description:
                "Specialized AI agents for every domain — each with the right model, tools, and knowledge for its job.",
            },
            {
              title: "48+ skills, no code",
              description:
                "Document intake, invoicing, scheduling, competitor intel, email triage — all configurable without writing code.",
            },
            {
              title: "Model orchestration",
              description:
                "Route each sub-task to the cheapest model that can handle it. Cut AI costs 60-80% without losing quality.",
            },
            {
              title: "Approvals that move",
              description:
                "Human-in-the-loop approval queues. Agents propose, humans decide. No unsupervised actions.",
            },
            {
              title: "Per-org isolation",
              description:
                "Each client gets their own gateway, workspace, and encrypted data store. No cross-tenant leakage.",
            },
            {
              title: "Realtime monitoring",
              description:
                "Live agent status, cost tracking, session health, and audit trails — all in one dashboard.",
            },
            {
              title: "Industry templates",
              description:
                "Construction, waste management, staffing, professional services — pre-built workflows for your vertical.",
            },
            {
              title: "Audit trail built in",
              description:
                "Every agent decision leaves a trail. SOC 2-ready infrastructure with encrypted backups.",
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

      <section className="trust-section" id="security">
        <div className="trust-header">
          <h2>Built for trust. Engineered for compliance.</h2>
          <p>
            When AI agents handle your invoicing, email, and client data, security
            isn't optional — it's the foundation.
          </p>
        </div>
        <div className="trust-grid">
          <div className="trust-card">
            <div className="trust-icon">&#x1F6E1;</div>
            <h3>Curated skills, not a marketplace</h3>
            <p>
              Open skill marketplaces like ClawHub saw 820+ malicious skills in a
              single incident. VantageClaw maintains 48 skills in-house — every one
              reviewed, tested, and mounted read-only. No community uploads. No
              supply chain risk.
            </p>
          </div>
          <div className="trust-card">
            <div className="trust-icon">&#x1F512;</div>
            <h3>AES-256-GCM encryption</h3>
            <p>
              All secrets and API keys encrypted at rest with authenticated
              encryption. HKDF-SHA256 key derivation with versioned wire format
              supports key rotation without downtime.
            </p>
          </div>
          <div className="trust-card">
            <div className="trust-icon">&#x1F50D;</div>
            <h3>Audit trail with dual-write</h3>
            <p>
              Every action logged to both PostgreSQL and centralized log aggregation
              — tamper-independent copies. Anti-backdating prevents log manipulation.
              Full audit history for compliance reviews.
            </p>
          </div>
          <div className="trust-card">
            <div className="trust-icon">&#x1F3E2;</div>
            <h3>Per-org gateway isolation</h3>
            <p>
              Each client organization gets its own gateway container, workspace,
              encrypted data store, and skill set. No cross-tenant data leakage.
              RBAC with 5 role levels.
            </p>
          </div>
        </div>
        <div className="soc2-banner">
          <div className="soc2-content">
            <h3>SOC 2-ready infrastructure</h3>
            <p>
              VantageClaw has implemented controls across all five SOC 2 Trust
              Service Criteria — Security, Availability, Confidentiality, Processing
              Integrity, and Privacy. Formal Type I certification is in progress.
            </p>
            <div className="soc2-controls">
              {[
                "Encrypted backups with automated verification",
                "Vulnerability scanning (pip-audit, Trivy, Bandit)",
                "Platform admin role separation (owner vs operator)",
                "Per-org data retention policies",
                "Input sanitization and sensitive data redaction",
                "Content filtering for regulated deployments",
              ].map((control) => (
                <div key={control} className="soc2-control">
                  <span className="soc2-check">&#10003;</span>
                  {control}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="pricing-section" id="pricing">
        <div className="pricing-header">
          <h2>Simple, transparent pricing</h2>
          <p>Start managed. Scale to dedicated. Go enterprise when you need full control.</p>
        </div>
        <div className="pricing-grid">
          {[
            {
              tier: "Managed",
              price: "$299",
              period: "/mo",
              description: "We run it. You use it.",
              features: [
                "Hosted on our infrastructure",
                "Up to 3 agents",
                "Email + calendar integration",
                "Document processing",
                "Onboarding + 30-day setup",
              ],
            },
            {
              tier: "Dedicated",
              price: "$799",
              period: "/mo",
              highlight: true,
              description: "Your infrastructure, our management.",
              features: [
                "Everything in Managed",
                "Unlimited agents",
                "BYOK API keys",
                "Custom LLM endpoints",
                "Priority support",
                "Custom skill development",
              ],
            },
            {
              tier: "Enterprise",
              price: "Custom",
              period: "",
              description: "Self-hosted. Data never leaves your network.",
              features: [
                "Everything in Dedicated",
                "Source license",
                "On-prem or private cloud",
                "SLA + dedicated support",
                "Regional compliance (CAC, GDPR)",
                "White-label option",
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
                  {plan.period ? (
                    <span className="pricing-period">{plan.period}</span>
                  ) : null}
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

      <section className="cta-section">
        <div className="cta-content">
          <h2>Ready to automate your business operations?</h2>
          <p>
            Book a free consultation. We&apos;ll audit your workflows and show you
            exactly which tasks your AI agents will handle from day one.
          </p>
          <div className="cta-actions">
            <SignedOut>
              {clerkEnabled ? (
                <>
                  <Link
                    href="https://vantageclaw.ai/consultation"
                    target="_blank"
                    rel="noreferrer"
                    className="btn-large white"
                  >
                    Book a Demo <ArrowIcon />
                  </Link>
                  <SignInButton
                    mode="modal"
                    forceRedirectUrl="/onboarding"
                    signUpForceRedirectUrl="/onboarding"
                  >
                    <button type="button" className="btn-large outline">
                      Sign In
                    </button>
                  </SignInButton>
                </>
              ) : (
                <>
                  <Link href="/boards/new" className="btn-large white">
                    Get Started
                  </Link>
                  <Link href="/boards" className="btn-large outline">
                    View Boards
                  </Link>
                </>
              )}
            </SignedOut>

            <SignedIn>
              <Link href="/boards/new" className="btn-large white">
                Create Board
              </Link>
              <Link href="/boards" className="btn-large outline">
                View Boards
              </Link>
            </SignedIn>
          </div>
        </div>
      </section>
    </>
  );
}
