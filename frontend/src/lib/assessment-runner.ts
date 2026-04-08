/**
 * Assessment Runner — deterministic scan orchestration engine.
 * Frontend chains proxy endpoint calls sequentially.
 * LLM only analyzes results after all scans complete.
 */

import {
  triggerWifiScan,
  triggerBleScan,
  triggerRfScan,
  triggerSdrSpectrumScan,
  triggerPortScan,
  triggerServiceEnum,
  triggerSslAudit,
  triggerOsintRecon,
  triggerDnsEnum,
  triggerVulnScan,
  triggerWebScan,
  triggerCredentialAudit,
  triggerWifiFullScanAssessment,
  generateScanReport,
  type ScanResult,
  type ScanReport,
  type AnalysisMode,
} from "@/lib/pentest-api";

// Analysis modes that skip the live LLM call entirely — scans persist, but
// the operator analyzes the data offline at home.
export const TAKE_HOME_ANALYSIS_MODES: readonly AnalysisMode[] = [
  "none",
  "cloud_take_home",
  "local_take_home",
] as const;

export function isTakeHomeMode(mode: AnalysisMode | undefined): boolean {
  return mode !== undefined && (TAKE_HOME_ANALYSIS_MODES as readonly string[]).includes(mode);
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AssessmentType =
  | "passive_recon"
  | "network"
  | "external_recon"
  | "vuln_assessment"
  | "credential_audit"
  | "wifi_security"
  | "tscm_sweep"
  | "full"
  | "custom";
export type StepStatus = "pending" | "running" | "complete" | "failed" | "skipped";
export type AssessmentPhase = "configure" | "pre_flight" | "running" | "review" | "analyzing" | "complete" | "error";

export interface PreFlightResult {
  capability: string;
  label: string;
  required: boolean;
  status: "pass" | "fail";
  detail: string;
}

export interface StepDefinition {
  id: string;
  label: string;
  scanType: string;
  fn: (opts: StepRunOptions) => Promise<ScanResult>;
}

export interface StepRunOptions {
  target?: string;
  profileKey?: string;
}

export interface AssessmentStep {
  id: string;
  label: string;
  scanType: string;
  status: StepStatus;
  startedAt?: number;
  completedAt?: number;
  durationMs?: number;
  result?: ScanResult;
  report?: ScanReport;
  error?: string;
}

export interface AssessmentState {
  phase: AssessmentPhase;
  type: AssessmentType;
  steps: AssessmentStep[];
  currentStepIndex: number;
  profileKey?: string;
  target?: string;
  startedAt?: number;
  completedAt?: number;
  analysisMessage?: string;
  analysisError?: string;
  preFlightResults?: PreFlightResult[];
  preFlightPassed?: boolean;
  // Take-home analysis workflow — controls whether scans trigger a live LLM
  // analysis or stop at scan completion for offline analysis at home
  analysisMode?: AnalysisMode;
  // Subject Area label for live_sanitized mode (TSCM sweeps) — goes into the
  // LLM prompt instead of real room names
  subjectArea?: string;
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

export type AssessmentAction =
  | {
      type: "CONFIGURE";
      assessmentType: AssessmentType;
      steps: StepDefinition[];
      profileKey?: string;
      target?: string;
      analysisMode?: AnalysisMode;
      subjectArea?: string;
    }
  | { type: "PRE_FLIGHT_START" }
  | { type: "PRE_FLIGHT_COMPLETE"; results: PreFlightResult[]; passed: boolean }
  | { type: "START" }
  | { type: "STEP_RUNNING"; stepId: string }
  | { type: "STEP_COMPLETE"; stepId: string; result: ScanResult; report?: ScanReport; durationMs: number }
  | { type: "STEP_FAILED"; stepId: string; error: string; durationMs: number }
  | { type: "STEP_SKIPPED"; stepId: string }
  | { type: "RETRY_STEP"; stepId: string }
  | { type: "SCANS_DONE" }
  | { type: "PROCEED_TO_ANALYSIS" }
  | { type: "ANALYSIS_STARTED" }
  | { type: "ANALYSIS_COMPLETE"; message: string }
  | { type: "ANALYSIS_FAILED"; error: string }
  | { type: "CANCEL" }
  | { type: "RESET" };

export const INITIAL_STATE: AssessmentState = {
  phase: "configure",
  type: "passive_recon",
  steps: [],
  currentStepIndex: -1,
};

function updateStep(steps: AssessmentStep[], stepId: string, update: Partial<AssessmentStep>): AssessmentStep[] {
  return steps.map((s) => (s.id === stepId ? { ...s, ...update } : s));
}

export function assessmentReducer(state: AssessmentState, action: AssessmentAction): AssessmentState {
  switch (action.type) {
    case "CONFIGURE":
      return {
        ...INITIAL_STATE,
        phase: "configure",
        type: action.assessmentType,
        profileKey: action.profileKey,
        target: action.target,
        analysisMode: action.analysisMode,
        subjectArea: action.subjectArea,
        steps: action.steps.map((d) => ({
          id: d.id,
          label: d.label,
          scanType: d.scanType,
          status: "pending" as StepStatus,
        })),
      };
    case "PRE_FLIGHT_START":
      return { ...state, phase: "pre_flight", preFlightResults: undefined, preFlightPassed: undefined };
    case "PRE_FLIGHT_COMPLETE":
      return { ...state, preFlightResults: action.results, preFlightPassed: action.passed };
    case "START":
      return { ...state, phase: "running", currentStepIndex: 0, startedAt: Date.now() };
    case "STEP_RUNNING":
      return {
        ...state,
        steps: updateStep(state.steps, action.stepId, { status: "running", startedAt: Date.now() }),
      };
    case "STEP_COMPLETE": {
      const newSteps = updateStep(state.steps, action.stepId, {
        status: "complete",
        completedAt: Date.now(),
        durationMs: action.durationMs,
        result: action.result,
        report: action.report,
      });
      const nextIdx = state.currentStepIndex + 1;
      return { ...state, steps: newSteps, currentStepIndex: nextIdx };
    }
    case "STEP_FAILED": {
      const newSteps = updateStep(state.steps, action.stepId, {
        status: "failed",
        completedAt: Date.now(),
        durationMs: action.durationMs,
        error: action.error,
      });
      const nextIdx = state.currentStepIndex + 1;
      return { ...state, steps: newSteps, currentStepIndex: nextIdx };
    }
    case "STEP_SKIPPED":
      return {
        ...state,
        steps: updateStep(state.steps, action.stepId, { status: "skipped" }),
        currentStepIndex: state.currentStepIndex + 1,
      };
    case "RETRY_STEP": {
      const stepIdx = state.steps.findIndex((s) => s.id === action.stepId);
      if (stepIdx < 0) return state;
      const retrySteps = updateStep(state.steps, action.stepId, {
        status: "pending",
        error: undefined,
        result: undefined,
        report: undefined,
        durationMs: undefined,
        startedAt: undefined,
        completedAt: undefined,
      });
      return { ...state, phase: "running", steps: retrySteps, currentStepIndex: stepIdx };
    }
    case "SCANS_DONE": {
      const hasFailed = state.steps.some((s) => s.status === "failed");
      if (hasFailed) {
        return { ...state, phase: "review" };
      }
      // Take-home modes skip the live LLM call — scans are persisted, but the
      // operator analyzes the data offline at home. Jump straight to complete
      // with a take-home status message instead of entering analyzing phase.
      if (isTakeHomeMode(state.analysisMode)) {
        return {
          ...state,
          phase: "complete",
          completedAt: Date.now(),
          analysisMessage: takeHomeCompletionMessage(state.analysisMode),
        };
      }
      return { ...state, phase: "analyzing" };
    }
    case "PROCEED_TO_ANALYSIS":
      return { ...state, phase: "analyzing" };
    case "ANALYSIS_STARTED":
      return { ...state, phase: "analyzing" };
    case "ANALYSIS_COMPLETE":
      return { ...state, phase: "complete", completedAt: Date.now(), analysisMessage: action.message };
    case "ANALYSIS_FAILED":
      return { ...state, phase: "complete", completedAt: Date.now(), analysisError: action.error };
    case "CANCEL": {
      const cancelled = state.steps.map((s) =>
        s.status === "pending" ? { ...s, status: "skipped" as StepStatus } : s,
      );
      return { ...state, phase: "complete", steps: cancelled, completedAt: Date.now() };
    }
    case "RESET":
      return INITIAL_STATE;
    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Preset definitions
// ---------------------------------------------------------------------------

const PASSIVE_STEPS: StepDefinition[] = [
  {
    id: "wifi_scan",
    label: "WiFi AP Scan",
    scanType: "WiFi Quick Scan",
    fn: () => triggerWifiScan(),
  },
  {
    id: "ble_scan",
    label: "BLE Device Scan",
    scanType: "BLE Scan (Pi)",
    fn: () => triggerBleScan(15),
  },
  {
    id: "rf_scan",
    label: "Sub-GHz RF Scan (433 MHz)",
    scanType: "Sub-GHz Scan",
    fn: () => triggerRfScan(15),
  },
  {
    id: "sdr_spectrum",
    label: "SDR Spectrum Sweep (ISM 400-500 MHz)",
    scanType: "SDR Spectrum",
    fn: (opts) =>
      triggerSdrSpectrumScan({
        freq_start: "400M",
        freq_end: "500M",
        bin_size: "1M",
        gain: 40,
        duration: 10,
        profile_key: opts.profileKey,
      }),
  },
];

const NETWORK_STEPS: StepDefinition[] = [
  {
    id: "port_scan",
    label: "Port Scan",
    scanType: "Port Scan (LAN)",
    fn: (opts) => triggerPortScan({ target: opts.target || "192.168.1.0/24", ports: "1-1024" }),
  },
  {
    id: "service_enum",
    label: "Service Enumeration",
    scanType: "Service Enumeration",
    fn: (opts) => triggerServiceEnum({ target: opts.target || "192.168.1.0/24", timeout: 180 }),
  },
  {
    id: "ssl_audit",
    label: "SSL/TLS Audit",
    scanType: "SSL Audit",
    fn: (opts) => triggerSslAudit({ target: opts.target || "192.168.1.1" }),
  },
];

const EXTERNAL_RECON_STEPS: StepDefinition[] = [
  {
    id: "osint_recon",
    label: "OSINT Recon",
    scanType: "OSINT Recon",
    fn: (opts) => triggerOsintRecon({ domain: opts.target || "example.com" }),
  },
  {
    id: "dns_enum",
    label: "DNS Enumeration",
    scanType: "DNS Enumeration",
    fn: (opts) => triggerDnsEnum({ domain: opts.target || "example.com" }),
  },
  {
    id: "ssl_audit_ext",
    label: "SSL/TLS Audit",
    scanType: "SSL Audit",
    fn: (opts) => triggerSslAudit({ target: opts.target || "example.com" }),
  },
];

const VULN_ASSESSMENT_STEPS: StepDefinition[] = [
  {
    id: "port_scan_vuln",
    label: "Port Scan",
    scanType: "Port Scan (LAN)",
    fn: (opts) => triggerPortScan({ target: opts.target || "192.168.1.0/24", ports: "1-10000" }),
  },
  {
    id: "service_enum_vuln",
    label: "Service Enumeration",
    scanType: "Service Enumeration",
    fn: (opts) => triggerServiceEnum({ target: opts.target || "192.168.1.0/24", timeout: 180 }),
  },
  {
    id: "vuln_scan",
    label: "Vulnerability Scan",
    scanType: "Vulnerability Scan",
    fn: (opts) => triggerVulnScan({ target: opts.target || "192.168.1.0/24", timeout: 300 }),
  },
  {
    id: "web_scan",
    label: "Web Application Scan",
    scanType: "Web Application Scan",
    fn: (opts) => triggerWebScan({ target_url: `http://${opts.target || "192.168.1.1"}`, timeout: 300 }),
  },
];

const CREDENTIAL_AUDIT_STEPS: StepDefinition[] = [
  {
    id: "port_scan_cred",
    label: "Port Scan (Service Discovery)",
    scanType: "Port Scan (LAN)",
    fn: (opts) => triggerPortScan({ target: opts.target || "192.168.1.0/24", ports: "22,23,80,443,445,3306,3389,5900,8080,8443" }),
  },
  {
    id: "credential_test_ssh",
    label: "Default Credential Test (SSH)",
    scanType: "Credential Test",
    fn: (opts) => triggerCredentialAudit({ target: opts.target || "192.168.1.1", service: "ssh" }),
  },
  {
    id: "credential_test_http",
    label: "Default Credential Test (HTTP)",
    scanType: "Credential Test",
    fn: (opts) => triggerCredentialAudit({ target: opts.target || "192.168.1.1", service: "http" }),
  },
];

const WIFI_SECURITY_STEPS: StepDefinition[] = [
  {
    id: "wifi_full_scan",
    label: "WiFi Full Scan (Monitor Mode)",
    scanType: "WiFi Full Scan",
    fn: () => triggerWifiFullScanAssessment(15),
  },
  {
    id: "wifi_scan_basic",
    label: "WiFi AP Discovery",
    scanType: "WiFi Quick Scan",
    fn: () => triggerWifiScan(),
  },
];

// TSCM sweep — broader SDR spectrum coverage + Sub-GHz + BLE + WiFi discovery
// for finding hidden surveillance devices. Linear methodology per Subject Area.
// Scan chain differs from passive_recon: wider SDR sweep (100 MHz-1.75 GHz
// range instead of just 400-500 MHz ISM), longer Sub-GHz dwell, passive WiFi
// AP discovery for rogue bugs, BLE active scan for trackers. NLJD sweep and
// physical search are operator-driven and captured separately in the TSCM
// Workspace (they are not automated scan steps).
const TSCM_SWEEP_STEPS: StepDefinition[] = [
  {
    id: "sdr_tscm_lowband",
    label: "SDR Low-Band Sweep (300-500 MHz, Sub-GHz bugs)",
    scanType: "SDR Spectrum",
    fn: (opts) =>
      triggerSdrSpectrumScan({
        freq_start: "300M",
        freq_end: "500M",
        bin_size: "500k",
        gain: 40,
        duration: 15,
        profile_key: opts.profileKey,
      }),
  },
  {
    id: "sdr_tscm_midband",
    label: "SDR Mid-Band Sweep (800-1000 MHz, cellular bugs)",
    scanType: "SDR Spectrum",
    fn: (opts) =>
      triggerSdrSpectrumScan({
        freq_start: "800M",
        freq_end: "1000M",
        bin_size: "500k",
        gain: 40,
        duration: 15,
        profile_key: opts.profileKey,
      }),
  },
  {
    id: "sdr_tscm_highband",
    label: "SDR High-Band Sweep (1200-1750 MHz, DECT/GPS)",
    scanType: "SDR Spectrum",
    fn: (opts) =>
      triggerSdrSpectrumScan({
        freq_start: "1200M",
        freq_end: "1750M",
        bin_size: "1M",
        gain: 40,
        duration: 15,
        profile_key: opts.profileKey,
      }),
  },
  {
    id: "subghz_tscm",
    label: "Sub-GHz Active Scan (audio bug frequencies)",
    scanType: "Sub-GHz Scan",
    fn: () => triggerRfScan(30),
  },
  {
    id: "ble_tscm",
    label: "BLE Active Scan (trackers, beacons)",
    scanType: "BLE Scan (Pi)",
    fn: () => triggerBleScan(30),
  },
  {
    id: "wifi_tscm",
    label: "WiFi AP Discovery (rogue AP check)",
    scanType: "WiFi Quick Scan",
    fn: () => triggerWifiScan(),
  },
];

export const ASSESSMENT_PRESETS: Record<Exclude<AssessmentType, "custom">, { label: string; description: string; steps: StepDefinition[] }> = {
  passive_recon: {
    label: "Passive Recon",
    description: "WiFi, BLE, RF, and SDR spectrum scanning. Receive-only, no active attacks.",
    steps: PASSIVE_STEPS,
  },
  external_recon: {
    label: "External Recon",
    description: "OSINT, DNS enumeration, and TLS audit against a domain. Passive — no direct target probing.",
    steps: EXTERNAL_RECON_STEPS,
  },
  network: {
    label: "Network Assessment",
    description: "Port scanning, service enumeration, and TLS audit. Private IPs only.",
    steps: NETWORK_STEPS,
  },
  vuln_assessment: {
    label: "Vulnerability Assessment",
    description: "Port scan + service enum + CVE identification + web app scan. Active but non-destructive.",
    steps: VULN_ASSESSMENT_STEPS,
  },
  credential_audit: {
    label: "Credential Audit",
    description: "Discover services then test default credentials. Proves access risk. Requires authorized TX mode.",
    steps: CREDENTIAL_AUDIT_STEPS,
  },
  wifi_security: {
    label: "WiFi Security Audit",
    description: "Full WiFi scan with monitor mode + AP discovery. Requires Alfa adapter. Authorized TX mode.",
    steps: WIFI_SECURITY_STEPS,
  },
  tscm_sweep: {
    label: "TSCM Sweep",
    description:
      "Technical Surveillance Counter-Measures sweep — wide SDR spectrum coverage, Sub-GHz, BLE, and WiFi rogue AP discovery. Run per Subject Area. Pairs with NLJD + physical search in the TSCM Workspace.",
    steps: TSCM_SWEEP_STEPS,
  },
  full: {
    label: "Full Assessment",
    description: "Passive recon + network + vulnerability assessment combined.",
    steps: [...PASSIVE_STEPS, ...NETWORK_STEPS, ...VULN_ASSESSMENT_STEPS],
  },
};

export function getStepsForType(type: AssessmentType, customStepIds?: string[]): StepDefinition[] {
  if (type === "custom" && customStepIds) {
    const all = [
      ...PASSIVE_STEPS,
      ...NETWORK_STEPS,
      ...EXTERNAL_RECON_STEPS,
      ...VULN_ASSESSMENT_STEPS,
      ...CREDENTIAL_AUDIT_STEPS,
      ...WIFI_SECURITY_STEPS,
      ...TSCM_SWEEP_STEPS,
    ];
    return all.filter((s) => customStepIds.includes(s.id));
  }
  return ASSESSMENT_PRESETS[type as keyof typeof ASSESSMENT_PRESETS]?.steps ?? [];
}

// ---------------------------------------------------------------------------
// Execution — run a single step
// ---------------------------------------------------------------------------

export async function executeStep(
  step: StepDefinition,
  opts: StepRunOptions,
): Promise<{ result: ScanResult; report?: ScanReport; durationMs: number }> {
  const start = Date.now();
  const result = await step.fn(opts);
  const durationMs = Date.now() - start;

  // Generate risk report (best-effort)
  let report: ScanReport | undefined;
  try {
    report = await generateScanReport({
      scan_type: step.scanType,
      scan_result: result as Record<string, unknown>,
    });
  } catch {
    // Report generation is best-effort
  }

  return { result, report, durationMs };
}

// ---------------------------------------------------------------------------
// LLM analysis prompt builder
// ---------------------------------------------------------------------------

/**
 * Completion message displayed when scans finish in a take-home analysis mode.
 * This is the operator-facing explanation of what to do next.
 */
export function takeHomeCompletionMessage(mode: AnalysisMode | undefined): string {
  switch (mode) {
    case "none":
      return `## Scans Complete — Manual Analysis Mode

All scan results have been persisted to scan history. This profile is configured for **pure manual analysis** — no AI will review this data in any phase.

**Next steps:**
1. Open **Scan History** to review the raw findings
2. Use the **Export** button on the profile to bundle all scan records
3. Write the final report by hand in your controlled environment
4. No cloud AI service will see any of this data`;
    case "cloud_take_home":
      return `## Scans Complete — Take-Home Analysis Mode

All scan results have been persisted to scan history. This profile is configured for **take-home analysis with Cloud Claude + manual sanitization** (the default for network, web, and wireless pentests).

**Next steps:**
1. Transport the Pi rig home (Faraday bag, wireless off)
2. Use the **Export** button to bundle all scan records as an encrypted archive
3. Analyze at home with Cloud Claude — manually sanitize each finding using \`[Host A]\`, \`[Host B]\` placeholders before pasting
4. Substitute real values back into the final report

See \`docs/operations/pentest-engagement-workflow.md\` for the full runbook.`;
    case "local_take_home":
      return `## Scans Complete — Local LLM Analysis Mode

All scan results have been persisted to scan history. This profile is configured for **take-home analysis on a local LLM** (the default for government, defense, and regulated engagements).

**Next steps:**
1. Transport the Pi rig home (Faraday bag, wireless off)
2. Use the **Export** button to bundle all scan records
3. Analyze at home on your local Qwen 2.5 / Llama 3.3 instance — no cloud LLM exposure
4. Bring current threat intel to the prompt yourself (local model knowledge cutoffs)`;
    default:
      return "Scans complete. Review findings in scan history.";
  }
}

export function buildAnalysisPrompt(state: AssessmentState): string {
  const completedSteps = state.steps.filter((s) => s.status === "complete");
  const failedSteps = state.steps.filter((s) => s.status === "failed");

  const scanSections = completedSteps
    .map((s, i) => {
      const riskLevel = s.report?.overall_risk ?? "unknown";
      const findingCount = s.report?.finding_count ?? 0;
      const findings = s.report?.findings ?? [];
      const findingsText = findings.length > 0
        ? findings.map((f) => `  - [${f.risk.toUpperCase()}] ${f.title}: ${f.detail}`).join("\n")
        : "  No significant findings";

      return `--- SCAN ${i + 1}: ${s.label} (${((s.durationMs ?? 0) / 1000).toFixed(1)}s) ---
Risk: ${riskLevel.toUpperCase()} | Findings: ${findingCount}
${findingsText}

Raw data summary: ${JSON.stringify(summarizeScanResult(s.result), null, 2)}`;
    })
    .join("\n\n");

  const failedText = failedSteps.length > 0
    ? `\n\nFailed scans (${failedSteps.length}):\n${failedSteps.map((s) => `- ${s.label}: ${s.error}`).join("\n")}`
    : "";

  // In live_sanitized mode (TSCM default), use a generic Subject Area label
  // instead of client-identifying location info. The operator maps labels →
  // real rooms locally; the LLM only sees the label.
  const locationLine =
    state.analysisMode === "live_sanitized" && state.subjectArea
      ? `Subject Area: ${state.subjectArea}  (operator-defined label, not a real location)`
      : `Target: ${state.target ?? "default"}`;

  return `[PENTEST ASSESSMENT RESULTS - DO NOT EXECUTE ANY TOOLS]
[ANALYZE THE FOLLOWING COMPLETED SCAN DATA AND PRODUCE A RISK REPORT]

Assessment Type: ${ASSESSMENT_PRESETS[state.type as keyof typeof ASSESSMENT_PRESETS]?.label ?? state.type}
Profile: ${state.profileKey ?? "none"}
${locationLine}
Date: ${new Date().toISOString()}
Completed: ${completedSteps.length}/${state.steps.length} scans

${scanSections}${failedText}

INSTRUCTIONS:
Produce a security assessment report with:
1. Executive summary (3-4 sentences)
2. Findings table sorted by severity (CRITICAL > HIGH > MEDIUM > LOW)
3. Cross-scan correlation (how findings from different scan types combine into attack chains)
4. Prioritized remediation plan with specific actions
5. Overall risk rating (CRITICAL / HIGH / MEDIUM / LOW) with justification`;
}

/** Summarize a scan result to reduce token usage in the LLM prompt. */
function summarizeScanResult(result?: ScanResult): Record<string, unknown> {
  if (!result) return {};
  const { scan_id, scan_type, timestamp, duration, ...rest } = result;
  // Keep arrays trimmed to first 10 items
  const summary: Record<string, unknown> = { scan_id, scan_type, duration };
  for (const [key, value] of Object.entries(rest)) {
    if (Array.isArray(value)) {
      summary[key] = value.length > 10
        ? { count: value.length, sample: value.slice(0, 10) }
        : value;
    } else if (typeof value === "object" && value !== null) {
      summary[key] = value;
    } else {
      summary[key] = value;
    }
  }
  return summary;
}
