"use client";

import Link from "next/link";
import { LandingShell } from "@/components/templates/LandingShell";

const CheckIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M3 8.5L6 11.5L13 4.5" stroke="#16a34a" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const ClockIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <circle cx="8" cy="8" r="6.5" stroke="#d97706" strokeWidth="1.5" />
    <path d="M8 4.5V8L10 10" stroke="#d97706" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

export default function CompliancePage() {
  return (
    <LandingShell>
      <div className="security-page">
        {/* Hero */}
        <section className="security-hero">
          <div className="security-hero-content">
            <h1>Compliance & SOC 2 Roadmap</h1>
            <p>
              VantageClaw is pursuing SOC 2 Type II certification. Our
              infrastructure implements controls across all five Trust Service
              Criteria.
            </p>
          </div>
        </section>

        {/* Trust Service Criteria */}
        <section className="security-section">
          <h2>SOC 2 Trust Service Criteria</h2>
          <p className="security-section-intro">
            We&apos;ve built SOC 2-ready infrastructure across Security,
            Availability, Confidentiality, Processing Integrity, and Privacy.
          </p>

          {/* Security */}
          <div className="compliance-criterion">
            <h3>Security (Common Criteria)</h3>
            <div className="compliance-controls">
              {[
                { control: "AES-256-GCM encryption at rest", detail: "17 encrypted fields across 7 models, HKDF-SHA256 key derivation", status: "shipped" },
                { control: "TLS encryption in transit", detail: "Caddy auto-TLS (public), Tailscale (internal), HTTPS-only API", status: "shipped" },
                { control: "RBAC access control", detail: "5 roles (viewer < member < operator < admin < owner), org-scoped isolation", status: "shipped" },
                { control: "Platform admin separation", detail: "Owner vs Operator — operators cannot access client email, chat, keys, or files", status: "shipped" },
                { control: "Input sanitization", detail: "Centralized prompt injection defense for text, PDFs, OCR, file uploads", status: "shipped" },
                { control: "Sensitive data redaction", detail: "Passwords, API keys, JWTs, credit cards, SIN/SSN stripped before LLM exposure", status: "shipped" },
                { control: "BYOK API key encryption", detail: "Per-org AES-256-GCM encrypted keys, OAuth token rejection for ToS compliance", status: "shipped" },
                { control: "Vulnerability scanning", detail: "pip-audit, npm audit, Trivy (Docker images), Bandit (Python SAST)", status: "shipped" },
                { control: "Rate limiting", detail: "600 req/min per org, keyed by org_id", status: "shipped" },
              ].map((item) => (
                <div key={item.control} className="compliance-control-row">
                  <div className="compliance-control-status">
                    {item.status === "shipped" ? <CheckIcon /> : <ClockIcon />}
                  </div>
                  <div className="compliance-control-info">
                    <div className="compliance-control-name">{item.control}</div>
                    <div className="compliance-control-detail">{item.detail}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Availability */}
          <div className="compliance-criterion">
            <h3>Availability</h3>
            <div className="compliance-controls">
              {[
                { control: "Circuit breakers", detail: "OpenRouter (5 failures/60s), Gateway RPC (3 failures/30s) with automatic recovery", status: "shipped" },
                { control: "System health monitoring", detail: "Aggregated healthy/degraded/down status endpoint, Prometheus metrics", status: "shipped" },
                { control: "Session auto-compaction", detail: "Invisible context management — agents never hit token limits", status: "shipped" },
                { control: "Cron watchdog", detail: "10-minute stale task detection with automated alerts", status: "shipped" },
                { control: "Grafana alerting", detail: "Backup missing (26h), log ingestion stopped (10m), audit write failures (>3 in 5m)", status: "shipped" },
              ].map((item) => (
                <div key={item.control} className="compliance-control-row">
                  <div className="compliance-control-status">
                    {item.status === "shipped" ? <CheckIcon /> : <ClockIcon />}
                  </div>
                  <div className="compliance-control-info">
                    <div className="compliance-control-name">{item.control}</div>
                    <div className="compliance-control-detail">{item.detail}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Confidentiality */}
          <div className="compliance-criterion">
            <h3>Confidentiality</h3>
            <div className="compliance-controls">
              {[
                { control: "Multi-tenant isolation", detail: "Per-org gateway containers, workspace isolation, org-scoped database queries", status: "shipped" },
                { control: "Data policy controls", detail: "Per-org redaction level, LLM input logging toggle, content filter region", status: "shipped" },
                { control: "Email visibility scoping", detail: "Shared/private per-user email accounts, RBAC-enforced access", status: "shipped" },
                { control: "Content filtering", detail: "CAC-compliant output filtering for regulated deployments", status: "shipped" },
                { control: "Docker-image delivery", detail: "No source code access for clients — sealed containers only", status: "shipped" },
              ].map((item) => (
                <div key={item.control} className="compliance-control-row">
                  <div className="compliance-control-status">
                    {item.status === "shipped" ? <CheckIcon /> : <ClockIcon />}
                  </div>
                  <div className="compliance-control-info">
                    <div className="compliance-control-name">{item.control}</div>
                    <div className="compliance-control-detail">{item.detail}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Processing Integrity */}
          <div className="compliance-criterion">
            <h3>Processing Integrity</h3>
            <div className="compliance-controls">
              {[
                { control: "Dual-write audit logging", detail: "PostgreSQL + Loki — tamper-independent second copy, labeled log_type: audit", status: "shipped" },
                { control: "Anti-backdating", detail: "Loki 14-day reject_old_samples_max_age prevents log tampering", status: "shipped" },
                { control: "Backup verification", detail: "Weekly automated restore test — checksum, decrypt, restore, sanity query", status: "shipped" },
                { control: "Backup encryption", detail: "Daily pg_dump | gzip | gpg AES-256 with SHA-256 checksums, 30-day retention", status: "shipped" },
                { control: "Data retention policies", detail: "Configurable per-org retention periods with batched cleanup", status: "shipped" },
              ].map((item) => (
                <div key={item.control} className="compliance-control-row">
                  <div className="compliance-control-status">
                    {item.status === "shipped" ? <CheckIcon /> : <ClockIcon />}
                  </div>
                  <div className="compliance-control-info">
                    <div className="compliance-control-name">{item.control}</div>
                    <div className="compliance-control-detail">{item.detail}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Privacy */}
          <div className="compliance-criterion">
            <h3>Privacy</h3>
            <div className="compliance-controls">
              {[
                { control: "Terms of Service", detail: "Versioned acceptance tracking, POST /auth/accept-terms", status: "shipped" },
                { control: "Privacy Policy", detail: "Served at /api/v1/legal/privacy", status: "shipped" },
                { control: "Data Processing Agreement", detail: "Template with client placeholders for DPA execution", status: "shipped" },
                { control: "Per-org data policy", detail: "Redaction level, email content to LLM toggle, retention overrides", status: "shipped" },
              ].map((item) => (
                <div key={item.control} className="compliance-control-row">
                  <div className="compliance-control-status">
                    {item.status === "shipped" ? <CheckIcon /> : <ClockIcon />}
                  </div>
                  <div className="compliance-control-info">
                    <div className="compliance-control-name">{item.control}</div>
                    <div className="compliance-control-detail">{item.detail}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Remaining */}
        <section className="security-section alt">
          <h2>What&apos;s remaining</h2>
          <p className="security-section-intro">
            The following items are in progress toward formal SOC 2 Type I
            certification.
          </p>
          <div className="compliance-controls">
            {[
              { control: "SOC 2 auditor engagement", detail: "Select and engage audit firm for Type I assessment", status: "pending" },
              { control: "Third-party penetration test", detail: "External pen test by accredited firm", status: "pending" },
              { control: "Formal access review process", detail: "Documented quarterly access review", status: "pending" },
              { control: "Change management evidence", detail: "Documented approval trail for production changes", status: "pending" },
              { control: "Legal review", detail: "Canadian lawyer review of Terms, Privacy Policy, and DPA", status: "pending" },
              { control: "Off-site backup", detail: "Geographic redundancy via secondary storage location", status: "pending" },
            ].map((item) => (
              <div key={item.control} className="compliance-control-row">
                <div className="compliance-control-status">
                  <ClockIcon />
                </div>
                <div className="compliance-control-info">
                  <div className="compliance-control-name">{item.control}</div>
                  <div className="compliance-control-detail">{item.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Timeline */}
        <section className="security-section">
          <h2>Certification timeline</h2>
          <div className="compliance-timeline">
            <div className="compliance-timeline-item active">
              <div className="compliance-timeline-marker active" />
              <div className="compliance-timeline-content">
                <h3>Phase 1 — Infrastructure (Current)</h3>
                <p>All technical controls implemented and operational across five Trust Service Criteria.</p>
              </div>
            </div>
            <div className="compliance-timeline-item">
              <div className="compliance-timeline-marker" />
              <div className="compliance-timeline-content">
                <h3>Phase 2 — Type I Assessment</h3>
                <p>Engage auditor for point-in-time evaluation of control design and implementation.</p>
              </div>
            </div>
            <div className="compliance-timeline-item">
              <div className="compliance-timeline-marker" />
              <div className="compliance-timeline-content">
                <h3>Phase 3 — Type II Certification</h3>
                <p>6+ months of operating effectiveness evidence, resulting in full SOC 2 Type II report.</p>
              </div>
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="security-cta">
          <h2>Need a security questionnaire completed?</h2>
          <p>
            We&apos;re happy to provide detailed responses to your security and
            compliance requirements.
          </p>
          <div className="security-cta-actions">
            <Link
              href="https://vantageclaw.ai/consultation"
              target="_blank"
              rel="noreferrer"
              className="btn-large primary"
            >
              Contact Us
            </Link>
            <Link href="/security" className="btn-large secondary">
              View Security Details
            </Link>
          </div>
        </section>
      </div>
    </LandingShell>
  );
}
