// Cellular Uplink Watch escalation predicate v2 (2026-05-16, Test 1.7
// empirical calibration session #65).
//
// Predicate: a peak escalates iff it is in a cellular uplink band AND
// its peak-median spread (power_db - median_db) is at least
// ESCALATION_SPREAD_DB across the 90s scan window.
//
// Calibration data captured during Test 1.7 on 2026-05-16:
//   Empty room (Record 1):           max spread = +5.6 dB
//   30s outbound call (Record 2):    max spread = +10.5 dB (2 peaks ≥10)
//   90s voicemail call (Record 0):   max spread = +12.7 dB (1 peak ≥10)
//
// A threshold of +10 dB gives a 4.4 dB margin over the empty-room ceiling
// and cleanly escalates both positive cases.
//
// Why spread, not absolute power: in the test environment the strongest
// tower carrier peaks (840 / 847 MHz, persistent ambient) reach -9.4 dB,
// indistinguishable in absolute power from an in-room phone's burst peak.
// The discriminator is temporal: a tower carrier holds steady (peak ~=
// median, spread <6 dB), whereas a phone burst spikes briefly above an
// otherwise-quiet bin (median is in the -19 to -21 dB range while peak
// reaches -7 to -10 dB, spread ≥10 dB).
//
// Replaces v1 (median-baseline + 10 dB), which used median continuous power
// as baseline and required absolute peak >= baseline + 10. v1 produced
// green on both empty-room and phone-call scans because the test phone's
// uplink power was similar to tower leakage at the receive antenna. See
// session #65 chat history + feedback_cellular_watch_rtl_power_averaging.md.
//
// Must agree with backend _CELLULAR_UPLINK_BANDS in app/api/pentest.py.

export const CELLULAR_UPLINK_BANDS: ReadonlyArray<{
  low: number;
  high: number;
}> = [
  { low: 824, high: 849 },
  { low: 1710, high: 1755 },
];

export const ESCALATION_SPREAD_DB = 10;

export type TemporalClass =
  | "continuous"
  | "intermittent"
  | "burst"
  | "noise"
  | "unknown";

export interface CellularWatchPeak {
  frequency_mhz: number;
  power_db: number;
  // The bridge emits median_db per peak (peak power vs median across the
  // 90 one-second buckets). Optional in the type because legacy single-row
  // bridge responses lack it — if missing, the peak is surfaced for review
  // rather than auto-escalated.
  median_db?: number;
  temporal_class: TemporalClass;
}

export interface CellularWatchClassification {
  // Tallies — every peak regardless of escalation
  totalContinuous: number;
  totalIntermittent: number;
  totalBurst: number;
  totalUnknown: number;
  // Escalation counts — peaks that meet (in-band ∧ spread ≥ threshold)
  escalatedContinuous: number;
  escalatedIntermittent: number;
  escalatedBurst: number;
  totalEscalated: number;
  // Max observed peak-median spread in cellular bands (operator visibility).
  // Null if no in-band peaks have median_db.
  maxSpreadDb: number | null;
  // Peaks in cellular bands but missing median_db — operator should review
  // the SDR scan record manually for these.
  peaksWithoutMedian: number;
}

function isInCellularBand(freq_mhz: number): boolean {
  if (!Number.isFinite(freq_mhz) || freq_mhz <= 0) return false;
  return CELLULAR_UPLINK_BANDS.some(
    (b) => freq_mhz >= b.low && freq_mhz <= b.high,
  );
}

export function classifyCellularWatchPeaks(
  peaks: ReadonlyArray<CellularWatchPeak>,
): CellularWatchClassification {
  const result: CellularWatchClassification = {
    totalContinuous: 0,
    totalIntermittent: 0,
    totalBurst: 0,
    totalUnknown: 0,
    escalatedContinuous: 0,
    escalatedIntermittent: 0,
    escalatedBurst: 0,
    totalEscalated: 0,
    maxSpreadDb: null,
    peaksWithoutMedian: 0,
  };

  for (const p of peaks) {
    switch (p.temporal_class) {
      case "continuous":
        result.totalContinuous += 1;
        break;
      case "intermittent":
        result.totalIntermittent += 1;
        break;
      case "burst":
        result.totalBurst += 1;
        break;
      default:
        result.totalUnknown += 1;
    }

    if (!isInCellularBand(p.frequency_mhz)) continue;

    if (typeof p.median_db !== "number" || !Number.isFinite(p.median_db)) {
      result.peaksWithoutMedian += 1;
      continue;
    }

    const spread = p.power_db - p.median_db;
    if (result.maxSpreadDb === null || spread > result.maxSpreadDb) {
      result.maxSpreadDb = spread;
    }
    if (spread < ESCALATION_SPREAD_DB) continue;

    switch (p.temporal_class) {
      case "continuous":
        result.escalatedContinuous += 1;
        result.totalEscalated += 1;
        break;
      case "intermittent":
        result.escalatedIntermittent += 1;
        result.totalEscalated += 1;
        break;
      case "burst":
        result.escalatedBurst += 1;
        result.totalEscalated += 1;
        break;
    }
  }

  return result;
}
