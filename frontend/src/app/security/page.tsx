"use client";

import Link from "next/link";
import { LandingShell } from "@/components/templates/LandingShell";

const CheckIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M3 8.5L6 11.5L13 4.5" stroke="#16a34a" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const ShieldIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export default function SecurityPage() {
  return (
    <LandingShell>
      <div className="security-page">
        {/* Hero */}
        <section className="security-hero">
          <div className="security-hero-content">
            <div className="security-hero-icon"><ShieldIcon /></div>
            <h1>Security at VantageClaw</h1>
            <p>
              When AI agents handle your invoicing, email, and client data,
              security isn&apos;t optional — it&apos;s the foundation.
            </p>
          </div>
        </section>

        {/* Why Curated Skills */}
        <section className="security-section">
          <h2>Curated skills, not an open marketplace</h2>
          <p className="security-section-intro">
            Open skill marketplaces are a major prompt injection surface. Skills are
            instruction files loaded directly into agent context as trusted
            instructions — making them a prime attack vector.
          </p>
          <div className="security-comparison">
            <div className="security-comparison-card bad">
              <h3>Open Marketplaces (ClawHub)</h3>
              <ul>
                <li>820+ malicious skills discovered in ClawHavoc incident</li>
                <li>8% poisoning rate across ~10,700 skills</li>
                <li>Anyone can publish — no review process</li>
                <li>Supply chain attacks via community submissions</li>
                <li>Skills can exfiltrate API keys, override system prompts</li>
              </ul>
            </div>
            <div className="security-comparison-card good">
              <h3>VantageClaw (Curated Library)</h3>
              <ul>
                <li><CheckIcon /> 48 skills built and maintained in-house</li>
                <li><CheckIcon /> Every skill reviewed and tested before deployment</li>
                <li><CheckIcon /> Admin-gated installation — only org admins can modify</li>
                <li><CheckIcon /> Read-only mounting — skills can&apos;t be modified at runtime</li>
                <li><CheckIcon /> No ClawHub dependency — zero third-party skill code</li>
              </ul>
            </div>
          </div>
        </section>

        {/* Encryption */}
        <section className="security-section alt">
          <h2>Encryption & data protection</h2>
          <div className="security-grid">
            <div className="security-card">
              <h3>AES-256-GCM at rest</h3>
              <p>
                All secrets and API keys encrypted with authenticated encryption.
                HKDF-SHA256 key derivation with versioned wire format supports key
                rotation without downtime. 17 encrypted fields across 7 data models.
              </p>
            </div>
            <div className="security-card">
              <h3>TLS everywhere in transit</h3>
              <p>
                Caddy auto-TLS for the public domain. Tailscale for internal admin
                access. All API communication over HTTPS. No plaintext data
                transmission.
              </p>
            </div>
            <div className="security-card">
              <h3>Input sanitization</h3>
              <p>
                All user and document text passes through centralized sanitization
                before reaching AI agents. Single source of truth for prompt
                injection defense across text, PDFs, OCR, and file uploads.
              </p>
            </div>
            <div className="security-card">
              <h3>Sensitive data redaction</h3>
              <p>
                Passwords, API keys, JWTs, credit card numbers, and SIN/SSN
                automatically stripped before data reaches AI models. Configurable
                redaction levels per organization.
              </p>
            </div>
          </div>
        </section>

        {/* Isolation */}
        <section className="security-section">
          <h2>Per-organization isolation</h2>
          <p className="security-section-intro">
            Every client organization gets its own dedicated infrastructure.
            No shared resources. No cross-tenant data leakage.
          </p>
          <div className="security-grid">
            <div className="security-card">
              <h3>Dedicated gateway containers</h3>
              <p>
                Each organization runs in its own Docker container with isolated
                workspace, agent memory, skill set, and cron configuration.
              </p>
            </div>
            <div className="security-card">
              <h3>RBAC with 5 role levels</h3>
              <p>
                Viewer, Member, Operator, Admin, Owner — each with granular
                permissions. Platform admin roles (Owner vs Operator) further
                restrict cross-org access.
              </p>
            </div>
            <div className="security-card">
              <h3>BYOK API keys</h3>
              <p>
                Clients provide their own AI provider keys, encrypted with
                AES-256-GCM. OAuth token rejection ensures LLM provider ToS
                compliance.
              </p>
            </div>
            <div className="security-card">
              <h3>Org-scoped rate limiting</h3>
              <p>
                600 requests per minute per organization, keyed by org ID.
                Prevents any single client from impacting platform availability.
              </p>
            </div>
          </div>
        </section>

        {/* Audit */}
        <section className="security-section alt">
          <h2>Audit & monitoring</h2>
          <div className="security-grid">
            <div className="security-card">
              <h3>Dual-write audit logging</h3>
              <p>
                Every audit event written to both PostgreSQL and centralized log
                aggregation — tamper-independent copies. Anti-backdating prevents
                log manipulation.
              </p>
            </div>
            <div className="security-card">
              <h3>Encrypted backups</h3>
              <p>
                Daily GPG AES-256 encrypted database dumps with SHA-256 checksums.
                Weekly automated restore verification. 30-day retention.
              </p>
            </div>
            <div className="security-card">
              <h3>Vulnerability scanning</h3>
              <p>
                Automated scanning across all dependencies and Docker images:
                pip-audit, npm audit, Trivy, and Bandit (Python SAST).
              </p>
            </div>
            <div className="security-card">
              <h3>Real-time alerting</h3>
              <p>
                Grafana alerts for backup failures, log ingestion stops, and
                audit write failures. Circuit breakers on all external API calls
                with automatic recovery.
              </p>
            </div>
          </div>
        </section>

        {/* Human Oversight */}
        <section className="security-section">
          <h2>Human oversight on AI actions</h2>
          <p className="security-section-intro">
            AI agents propose. Humans decide. Every consequential action goes
            through an approval gate.
          </p>
          <div className="security-oversight-list">
            {[
              { action: "Sending emails", gate: "Human-in-the-loop approval required" },
              { action: "Financial transactions", gate: "Review step before execution" },
              { action: "Skill behavior changes", gate: "Developer reviews and approves proposed updates" },
              { action: "High-risk decisions", gate: "Risk Reviewer agent provides independent second opinion" },
              { action: "Content publishing", gate: "Manual review before posting to any platform" },
            ].map((item) => (
              <div key={item.action} className="security-oversight-item">
                <div className="security-oversight-action">{item.action}</div>
                <div className="security-oversight-gate">
                  <CheckIcon /> {item.gate}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Risks & Limitations — placeholder for post-Angela content */}
        <section className="security-section alt">
          <h2>Risks & limitations</h2>
          <p className="security-section-intro">
            We believe transparency builds trust. Here&apos;s what you should know
            about the current state of the platform.
          </p>
          <div className="security-grid">
            <div className="security-card">
              <h3>AI can make mistakes</h3>
              <p>
                AI agents may draft incorrect invoice amounts, suggest inaccurate
                competitor data, or produce imperfect content. All consequential
                actions require human approval before execution.
              </p>
            </div>
            <div className="security-card">
              <h3>Cross-border data flow</h3>
              <p>
                AI conversations are routed through OpenRouter (US-based servers)
                unless you use our self-hosted LLM option. Enterprise tier clients
                can keep all data on their own infrastructure.
              </p>
            </div>
            <div className="security-card">
              <h3>Model updates</h3>
              <p>
                When AI providers update their models, agent behavior may change.
                We are building model version pinning to give clients control over
                when updates are applied. Contact us for current status.
              </p>
            </div>
            <div className="security-card">
              <h3>Not a replacement for professionals</h3>
              <p>
                VantageClaw is a workflow automation tool, not a substitute for
                legal, medical, financial, or engineering professionals. AI
                recommendations should always be reviewed by qualified humans.
              </p>
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="security-cta">
          <h2>Questions about our security?</h2>
          <p>
            We&apos;re happy to answer detailed security questionnaires and discuss
            your specific compliance requirements.
          </p>
          <div className="security-cta-actions">
            <Link
              href="https://vantageclaw.ai/consultation"
              target="_blank"
              rel="noreferrer"
              className="btn-large primary"
            >
              Book a Security Discussion
            </Link>
            <Link href="/compliance" className="btn-large secondary">
              View Compliance Roadmap
            </Link>
          </div>
        </section>
      </div>
    </LandingShell>
  );
}
