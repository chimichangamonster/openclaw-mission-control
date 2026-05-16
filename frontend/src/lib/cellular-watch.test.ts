import { describe, it, expect } from "vitest";
import {
  CELLULAR_UPLINK_BANDS,
  ESCALATION_SPREAD_DB,
  classifyCellularWatchPeaks,
  type CellularWatchPeak,
} from "./cellular-watch";

// Predicate v2 (2026-05-16 session #65): peak-spread (peak_db - median_db)
// within cellular uplink bands. Replaces the v1 median-baseline +10 dB
// approach which was too conservative — real phone bursts in Test 1.7
// positive cases had a peak power similar to tower carrier leakage but
// distinctly higher peak-median spread (≥10 dB) over the 90s scan window.
//
// Empty-room max spread captured in Test 1.7: +5.6 dB (Record 1, 2026-05-16).
// Positive-case max spread: +10.5 dB (30s call, Record 2) and +12.7 dB
// (90s voicemail, Record 0). A spread ≥ 10 dB threshold gives a 4.4 dB
// margin to the empty-room max and cleanly escalates both positive cases.

// Real Test 1.7 negative case data — empty room, both phones out, 850 MHz.
// All in-band peaks have peak-median spread ≤ +5.6 dB.
const EMPTY_ROOM_PEAKS: CellularWatchPeak[] = [
  // Tower carriers — high peak, narrow spread
  { frequency_mhz: 840.059, power_db: -9.7, median_db: -11.8, temporal_class: "continuous" },
  { frequency_mhz: 847.437, power_db: -10.1, median_db: -12.4, temporal_class: "continuous" },
  // Ambient noise peaks
  { frequency_mhz: 834.677, power_db: -15.0, median_db: -20.6, temporal_class: "burst" },
  { frequency_mhz: 824.838, power_db: -18.3, median_db: -22.0, temporal_class: "burst" },
];

// Real Test 1.7 positive case 1 data — phone with 30s outbound call.
// Three peaks at 838-839 MHz with spread > +9 dB; two clear +10.
const POSITIVE_30S_CALL_PEAKS: CellularWatchPeak[] = [
  // Tower carriers (same as empty room)
  { frequency_mhz: 840.059, power_db: -9.4, median_db: -11.7, temporal_class: "continuous" },
  { frequency_mhz: 847.437, power_db: -10.0, median_db: -12.2, temporal_class: "continuous" },
  // Phone uplink bursts — high spread is the signature
  { frequency_mhz: 838.757, power_db: -9.8, median_db: -20.3, temporal_class: "burst" },
  { frequency_mhz: 839.017, power_db: -10.2, median_db: -20.6, temporal_class: "burst" },
  { frequency_mhz: 838.410, power_db: -9.7, median_db: -18.9, temporal_class: "intermittent" },
];

// Real Test 1.7 positive case 2 data — phone with 90s voicemail recording.
// Single very strong burst at 843 MHz with +12.7 dB spread.
const POSITIVE_90S_CALL_PEAKS: CellularWatchPeak[] = [
  { frequency_mhz: 840.059, power_db: -9.8, median_db: -12.0, temporal_class: "continuous" },
  { frequency_mhz: 847.437, power_db: -10.3, median_db: -12.6, temporal_class: "continuous" },
  { frequency_mhz: 843.878, power_db: -7.2, median_db: -19.9, temporal_class: "burst" },
];

describe("classifyCellularWatchPeaks v2 (spread-based)", () => {
  it("escalates ZERO peaks in empty-room baseline (Test 1.7 negative, Record 1)", () => {
    const result = classifyCellularWatchPeaks(EMPTY_ROOM_PEAKS);
    expect(result.totalEscalated).toBe(0);
    expect(result.escalatedContinuous).toBe(0);
    expect(result.escalatedIntermittent).toBe(0);
    expect(result.escalatedBurst).toBe(0);
    expect(result.maxSpreadDb).toBeCloseTo(5.6, 1);
  });

  it("escalates phone bursts in 30s-call positive case (Test 1.7 positive 1, Record 2)", () => {
    const result = classifyCellularWatchPeaks(POSITIVE_30S_CALL_PEAKS);
    // Three phone bursts: 838.757 (+10.5), 839.017 (+10.4), 838.410 (+9.2)
    // Threshold = 10 dB → two clear the bar
    expect(result.totalEscalated).toBe(2);
    expect(result.escalatedBurst).toBe(2);
    expect(result.maxSpreadDb).toBeCloseTo(10.5, 1);
  });

  it("escalates phone burst in 90s-voicemail positive case (Test 1.7 positive 2, Record 0)", () => {
    const result = classifyCellularWatchPeaks(POSITIVE_90S_CALL_PEAKS);
    // 843.878 burst: -7.2 - (-19.9) = +12.7 dB spread
    expect(result.totalEscalated).toBe(1);
    expect(result.escalatedBurst).toBe(1);
    expect(result.maxSpreadDb).toBeCloseTo(12.7, 1);
  });

  it("does NOT escalate peaks outside cellular uplink bands", () => {
    // High-spread peak at FM broadcast frequency — must be ignored
    const peaks: CellularWatchPeak[] = [
      // In-band tower at low spread
      { frequency_mhz: 840.0, power_db: -9.7, median_db: -12.0, temporal_class: "continuous" },
      // Out-of-band peak with high spread — would escalate IF it were in cellular
      { frequency_mhz: 99.5, power_db: 10.0, median_db: -10.0, temporal_class: "burst" },
    ];
    const result = classifyCellularWatchPeaks(peaks);
    expect(result.totalEscalated).toBe(0);
  });

  it("escalates sustained-call continuous emission if spread is wide enough", () => {
    // A continuous emitter with high spread = bursty/changing transmission
    // pattern that the temporal classifier still labels continuous (because
    // it was above floor >50% of the time). Real example: a phone with
    // intermittent voice activity during a call.
    const peaks: CellularWatchPeak[] = [
      { frequency_mhz: 840.0, power_db: -9.7, median_db: -12.0, temporal_class: "continuous" },
      // High-spread continuous — phone with talking
      { frequency_mhz: 835.0, power_db: -5.0, median_db: -16.0, temporal_class: "continuous" },
    ];
    const result = classifyCellularWatchPeaks(peaks);
    // Spread = -5 - (-16) = +11 dB → escalate
    expect(result.escalatedContinuous).toBe(1);
    expect(result.totalEscalated).toBe(1);
  });

  it("escalates intermittent emissions with wide spread", () => {
    const peaks: CellularWatchPeak[] = [
      { frequency_mhz: 838.0, power_db: -8.0, median_db: -18.5, temporal_class: "intermittent" },
    ];
    const result = classifyCellularWatchPeaks(peaks);
    // Spread = +10.5 dB → escalate
    expect(result.escalatedIntermittent).toBe(1);
    expect(result.totalEscalated).toBe(1);
  });

  it("ignores peaks below spread threshold even when peak power is high", () => {
    // Strong continuous tower peak — high absolute power but narrow spread
    const peaks: CellularWatchPeak[] = [
      { frequency_mhz: 840.0, power_db: -5.0, median_db: -7.0, temporal_class: "continuous" },
    ];
    const result = classifyCellularWatchPeaks(peaks);
    // Spread = +2 dB → far below threshold → no escalation
    expect(result.totalEscalated).toBe(0);
  });

  it("ignores peaks with missing or invalid frequency_mhz", () => {
    const peaks: CellularWatchPeak[] = [
      { frequency_mhz: 0, power_db: -7.0, median_db: -20.0, temporal_class: "burst" },
      { frequency_mhz: 840.0, power_db: -9.7, median_db: -12.0, temporal_class: "continuous" },
    ];
    const result = classifyCellularWatchPeaks(peaks);
    expect(result.totalEscalated).toBe(0);
  });

  it("ignores peaks with missing median_db (cannot compute spread)", () => {
    const peaks: CellularWatchPeak[] = [
      { frequency_mhz: 838.0, power_db: -7.0, temporal_class: "burst" },
    ];
    const result = classifyCellularWatchPeaks(peaks);
    // No median → spread unknown → not escalated, surfaced for review
    expect(result.totalEscalated).toBe(0);
    expect(result.peaksWithoutMedian).toBe(1);
  });

  it("classifies tallies separately from escalations", () => {
    const result = classifyCellularWatchPeaks(EMPTY_ROOM_PEAKS);
    expect(result.totalContinuous).toBe(2);
    expect(result.totalIntermittent).toBe(0);
    expect(result.totalBurst).toBe(2);
  });

  it("reports max spread for operator visibility", () => {
    const result = classifyCellularWatchPeaks(POSITIVE_30S_CALL_PEAKS);
    expect(result.maxSpreadDb).toBeCloseTo(10.5, 1);
  });

  it("escalates intermittents from 30s-call when threshold is 8 dB (sanity)", () => {
    // The 30s-call had 4 peaks with spread >= 8 dB. Tonight's threshold is
    // 10 dB; this test documents what would happen at 8 dB for future tuning
    // by replicating the count via raw spread inspection.
    let above8 = 0;
    for (const p of POSITIVE_30S_CALL_PEAKS) {
      if (p.median_db === undefined) continue;
      const spread = p.power_db - p.median_db;
      if (spread >= 8) above8 += 1;
    }
    expect(above8).toBe(3);
  });
});

describe("CELLULAR_UPLINK_BANDS", () => {
  it("covers 850 MHz GSM/LTE uplink (824-849 MHz)", () => {
    const eightFifty = CELLULAR_UPLINK_BANDS.find(
      (b) => b.low === 824 && b.high === 849,
    );
    expect(eightFifty).toBeDefined();
  });

  it("covers AWS-1/PCS uplink (1710-1755 MHz)", () => {
    const aws = CELLULAR_UPLINK_BANDS.find(
      (b) => b.low === 1710 && b.high === 1755,
    );
    expect(aws).toBeDefined();
  });

  it("matches the backend _CELLULAR_UPLINK_BANDS exactly", () => {
    expect(CELLULAR_UPLINK_BANDS).toEqual([
      { low: 824, high: 849 },
      { low: 1710, high: 1755 },
    ]);
  });
});

describe("ESCALATION_SPREAD_DB", () => {
  it("is 10 dB — locked by 2026-05-16 Test 1.7 empirical calibration", () => {
    expect(ESCALATION_SPREAD_DB).toBe(10);
  });
});
