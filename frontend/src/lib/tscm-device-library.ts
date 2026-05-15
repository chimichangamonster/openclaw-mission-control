/**
 * TSCM Surveillance Device Fingerprint Library
 *
 * Reference data for correlating RF scan findings against known surveillance
 * device categories during a TSCM sweep. This is a curated, operator-facing
 * library — not exhaustive, and intentionally conservative. The Pi rig (RTL-SDR
 * + Flipper + Alfa) can detect active broadcasting devices in the 100 kHz to
 * 1.75 GHz range. Passive recording devices (voice recorders, SD card cameras,
 * hardwired microphones) cannot be detected via RF and are NOT in this library.
 *
 * See docs/operations/tscm-testing-protocol.md for the honest scope of what
 * the current rig can and cannot detect.
 *
 * Sources: general TSCM industry knowledge, SDR device identification guides,
 * public consumer-grade surveillance device specifications. Never speculative.
 */

export type DeviceCategory =
  | "wireless_camera"
  | "audio_bug"
  | "cellular_bug"
  | "ble_tracker"
  | "wifi_bug"
  | "gps_tracker"
  | "dect_tap"
  | "body_wire"
  | "iot_rogue";

export type Detectability = "high" | "medium" | "low";

export interface SurveillanceDevice {
  /** Unique ID for the entry (used in UI keys) */
  id: string;
  /** Display name — device category, not a specific model */
  name: string;
  /** Broad category for grouping */
  category: DeviceCategory;
  /** Frequency band in human-readable form */
  frequency: string;
  /** Numeric frequency range in MHz (for scan correlation) */
  freqRangeMhz: [number, number];
  /** Modulation / transmission pattern */
  modulation: string;
  /** How the device typically broadcasts — burst, continuous, etc. */
  pattern: string;
  /** How confidently the Pi rig can detect this device type */
  detectability: Detectability;
  /** What scan type(s) are most likely to find it */
  detectedBy: string[];
  /** Specific fingerprint markers the operator should look for */
  markers: string[];
  /** Countermeasure recommendation if found */
  countermeasure: string;
  /** Notes and caveats */
  notes?: string;
  /**
   * BLE manufacturer company identifiers (decimal form).
   * Source: Bluetooth SIG company-identifiers registry. e.g. 76 = Apple 0x004C.
   * Operator-curated; expanded as Step 3 walkthrough surfaces specific devices.
   */
  manufacturerIds?: number[];
  /**
   * BLE service UUIDs (16-bit short form). e.g. 0xFD6F = Apple Exposure
   * Notification / Find My-related short. Stored as 16-bit ints; the matcher
   * accepts the bridge's full 128-bit UUID strings and extracts the short.
   */
  serviceUuids16?: number[];
}

/**
 * Surveillance device fingerprint library.
 *
 * Entries are intentionally general — "2.4 GHz wireless spy camera" rather
 * than "Acme SpyCam Model 7". Real-world devices vary widely in implementation
 * and a category-level fingerprint is more useful than a model database that
 * would go stale. The operator uses these fingerprints as hypotheses to test
 * with physical search, not as definitive device IDs.
 */
export const SURVEILLANCE_DEVICES: SurveillanceDevice[] = [
  {
    id: "wcam_24ghz",
    name: "2.4 GHz Wireless Spy Camera",
    category: "wireless_camera",
    frequency: "2.40 - 2.48 GHz (ISM band)",
    freqRangeMhz: [2400, 2483],
    modulation: "FM video / digital FSK",
    pattern: "Continuous or periodic transmission while active",
    detectability: "high",
    detectedBy: ["SDR Spectrum", "WiFi Quick Scan"],
    markers: [
      "Strong signal from fixed indoor location",
      "Continuous carrier during operation (not bursty like WiFi)",
      "Does NOT appear in nearby WiFi AP scan (not a WiFi AP, just uses the band)",
      "RSSI correlates with physical proximity in the Subject Area",
    ],
    countermeasure:
      "Physically search the Subject Area — check smoke detectors, picture frames, clocks, USB chargers, air fresheners, and anything with a line-of-sight view of the area. Power down and isolate if found.",
    notes: "Most common consumer spy camera band. Cheap and widely available.",
  },
  {
    id: "wcam_58ghz",
    name: "5.8 GHz Wireless Spy Camera",
    category: "wireless_camera",
    frequency: "5.725 - 5.875 GHz",
    freqRangeMhz: [5725, 5875],
    modulation: "FM video / digital",
    pattern: "Continuous transmission while active",
    detectability: "low",
    detectedBy: ["SDR Spectrum (limited — above Nooelec v5 upper bound)"],
    markers: [
      "The Nooelec NESDR SMArt v5 tops out at 1.75 GHz",
      "These cameras are effectively INVISIBLE to the current rig",
      "Upgrading to HackRF One (1 MHz - 6 GHz) is required for reliable detection",
    ],
    countermeasure:
      "Physical search only — the current rig cannot detect this band. Note this limitation in the client report.",
    notes:
      "HONEST SCOPE: current rig cannot detect 5.8 GHz cameras. HackRF One required. Do not claim coverage.",
  },
  {
    id: "audio_bug_sub1ghz",
    name: "Sub-GHz Analog Audio Bug",
    category: "audio_bug",
    frequency: "315 / 433 / 868 / 915 MHz (ISM bands)",
    freqRangeMhz: [300, 930],
    modulation: "FM narrowband voice",
    pattern: "Continuous analog carrier during room activity",
    detectability: "high",
    detectedBy: ["SDR Spectrum", "Sub-GHz Scan"],
    markers: [
      "Narrow-band signal on a non-standard frequency",
      "Voice content demodulates cleanly as FM",
      "Signal appears continuously while room is occupied",
      "Does NOT correlate to known ISM devices (garage door, weather station, doorbell)",
    ],
    countermeasure:
      "Physically search for concealed transmitters — check wall clocks, pens, air fresheners, power strips, and decorative objects. Devices in this band are often battery-powered and can be moved.",
    notes: "Classic bug type. Easy to find with a baseline of known-ambient signals from the Subject Area.",
  },
  {
    id: "cellular_bug_gsm",
    name: "GSM / 3G / 4G Cellular Eavesdropper",
    category: "cellular_bug",
    frequency: "850 / 900 / 1700 / 1800 / 1900 MHz",
    freqRangeMhz: [800, 2100],
    modulation: "GSM / UMTS / LTE",
    pattern: "Periodic cellular handshakes during registration",
    detectability: "medium",
    detectedBy: ["SDR Spectrum"],
    markers: [
      "Periodic strong signals in cellular uplink bands from an indoor location",
      "Unknown cellular device in a sweep area where no occupant's phone should be",
      "Carrier registration bursts are brief — full characterization requires longer SDR dwell",
    ],
    countermeasure:
      "Physically search for concealed devices with a SIM card — often hidden in wall outlets, power strips, or USB chargers. Tamper-check the actual electrical fixtures.",
    notes:
      "Hard to distinguish from legitimate cellular usage if the Subject Area has normal cellular coverage. Better detection when cellular service is weak (basement, rural).",
  },
  {
    id: "ble_tracker",
    name: "BLE Tracker (Tile / AirTag style)",
    category: "ble_tracker",
    frequency: "2.402 - 2.480 GHz (BLE channels)",
    freqRangeMhz: [2402, 2480],
    modulation: "BLE advertising",
    pattern: "Periodic advertisement packets (every 1-2 seconds typically)",
    detectability: "high",
    detectedBy: ["BLE Scan (Pi)", "BLE Scan (Flipper)"],
    markers: [
      "BLE device with Apple / Tile / Samsung / Google manufacturer data",
      "No paired phone in the Subject Area claiming ownership",
      "Device name is generic or absent",
      "RSSI changes as operator moves through the Subject Area",
    ],
    countermeasure:
      "Physically search for the tracker — check bags, coats, vehicle undercarriage, seat cushions. Check for Apple 'unknown AirTag moving with you' notification on operator's iPhone. Power down or physically remove.",
    notes:
      "Very common in personal-surveillance / stalking cases. Always scan for these in executive protection sweeps. Manufacturer ID match is a HYPOTHESIS not a confirmation — Apple ID 0x004C is broadcast by every Apple device (AirPods, iPhones, Macs, AirTags). Distinguish AirTags from accessories via Apple's Find My beacon format + ownership context (is there a paired iPhone in the room?).",
    manufacturerIds: [
      76,    // Apple (0x004C) — AirTag, AirPods, iPhone, Mac (broad match by design)
      62,    // Tile (0x003E)
      117,   // Samsung (0x0075) — Galaxy SmartTag
      224,   // Google (0x00E0) — Pixel devices, Google Find My Device network
      2243,  // Chipolo (0x08C3) — alternative tracker brand
    ],
    serviceUuids16: [
      0xfd6f, // Apple Exposure Notification / Find My-related short. Operator-curated;
              // Step 3 walkthrough will surface the actual UUIDs broadcast by trackers
              // vs accessories in a real vehicle environment.
    ],
  },
  {
    id: "wifi_bug",
    name: "WiFi Connected Bug",
    category: "wifi_bug",
    frequency: "2.4 / 5 GHz (WiFi channels)",
    freqRangeMhz: [2400, 2500],
    modulation: "802.11",
    pattern: "Joins target WiFi or creates hidden hotspot",
    detectability: "high",
    detectedBy: ["WiFi Quick Scan", "WiFi Full Scan"],
    markers: [
      "Unknown device on the target WiFi network (port scan)",
      "Unexpected hidden SSID broadcast from inside the Subject Area",
      "OUI / MAC vendor not matching any known client device",
      "High upstream bandwidth from a device with no legitimate purpose",
    ],
    countermeasure:
      "Identify by MAC, block at the router or disconnect, then physically locate. WiFi bugs are often concealed in smart plugs, smoke detectors, or USB chargers.",
    notes: "Easy to detect if the operator has an inventory of legitimate WiFi clients for comparison.",
  },
  {
    id: "gps_tracker",
    name: "Cellular GPS Tracker",
    category: "gps_tracker",
    frequency: "Cellular bands (uplink)",
    freqRangeMhz: [800, 2100],
    modulation: "GSM / LTE",
    pattern: "Periodic location reports (every few minutes to hours)",
    detectability: "medium",
    detectedBy: ["SDR Spectrum"],
    markers: [
      "Periodic short bursts in cellular uplink bands",
      "Signal originates from inside a vehicle or luggage, not from an occupant's phone",
      "Pattern repeats at regular intervals matching a tracker's reporting schedule",
    ],
    countermeasure:
      "Physically search vehicle — check undercarriage (magnetic trackers), OBD-II port, trunk lining, wheel wells. For non-vehicle scenarios, check bags, coats, and personal items.",
    notes:
      "Vehicle TSCM sweeps are the typical use case. Longer SDR dwell helps catch the reporting windows.",
  },
  {
    id: "dect_tap",
    name: "DECT Phone Tap Repeater",
    category: "dect_tap",
    frequency: "1.88 - 1.93 GHz (DECT band)",
    freqRangeMhz: [1880, 1930],
    modulation: "DECT",
    pattern: "Narrowband transmission in DECT band",
    detectability: "medium",
    detectedBy: ["SDR Spectrum"],
    markers: [
      "Unexpected transmission in the DECT band",
      "DECT phone tap is separate from any legitimate cordless phone in the environment",
      "Signal appears when the legitimate phone is not in use",
    ],
    countermeasure:
      "Check legitimate DECT cordless phones and base stations for tampering. Inspect the phone's base station enclosure for added hardware.",
    notes:
      "Only applicable to environments still using DECT cordless phones. Rare in modern offices with VoIP.",
  },
  {
    id: "body_wire_uhf",
    name: "Body-Worn Wire (UHF/VHF)",
    category: "body_wire",
    frequency: "VHF / UHF (150-470 MHz typical)",
    freqRangeMhz: [150, 470],
    modulation: "FM narrowband voice",
    pattern: "Narrow-band voice, intermittent (operator-controlled)",
    detectability: "medium",
    detectedBy: ["SDR Spectrum", "Sub-GHz Scan"],
    markers: [
      "Narrow-band voice signal in VHF or UHF that does not match licensed public safety / business radio",
      "Signal appears when a specific person enters the Subject Area",
      "Intermittent — only transmits when the wearer activates it",
    ],
    countermeasure:
      "Physical search is the only reliable countermeasure. If RF evidence exists, document and end the sweep — this is a legal / law enforcement situation, not a technical one.",
    notes:
      "Rare in corporate TSCM. More common in criminal investigation contexts. Flag to client but do not escalate to law enforcement — that is the client's decision.",
  },
  {
    id: "gps_tracker_pro_grade",
    name: "Pro-Grade Concealed GPS Tracker",
    category: "gps_tracker",
    frequency: "Cellular bands (uplink, same as consumer)",
    freqRangeMhz: [800, 2100],
    modulation: "Cellular (GSM / LTE), often encrypted",
    pattern: "Designed to blend with ambient cellular traffic — reporting intervals chosen to avoid distinguishable patterns",
    detectability: "low",
    detectedBy: ["SDR Spectrum (limited)", "Physical inspection (primary)"],
    markers: [
      "Cellular uplink burst from a 'should be empty' room or vehicle",
      "INDISTINGUISHABLE from consumer trackers via RF alone — pro-grade gear deliberately mimics consumer pattern",
      "Professional installation: magnetic mount under wheel wells, hardwired into vehicle 12V harness, concealed in OBD-II port, or fitted inside body panels",
      "Often paired with the vehicle being parked unattended in a publicly accessible location for the install window",
      "Brand identification typically requires physical inspection — the device, not the RF signature, is the identifying evidence",
    ],
    countermeasure:
      "Document the device in place — photograph location, mounting method, any visible identifiers (FCC ID, brand markings, antenna). Do NOT remove or disable. Brief the client and let the client (with their legal counsel) decide next steps — removal, leaving in place, reporting. Pro-grade trackers are deployed by a range of actors (licensed PIs working legitimate investigations, current/former LE, civilian operators with professional gear) and the legal response varies by deployer + jurisdiction + circumstances. Your job is detection and documentation, not adjudication.",
    notes:
      "HONEST SCOPE: RF-only detection is unreliable for pro-grade gear by design. Physical inspection (especially vehicle undercarriage / wheel wells / OBD-II port / inside body panels) is the primary detection method. This entry exists to surface the device class honestly — not to claim RF coverage we don't have. Pro-grade ≠ government-only — the same device class is sold to licensed PIs and is available on the second-hand market.",
  },
  {
    id: "ble_tag_generic",
    name: "Generic No-Name BLE Tag",
    category: "ble_tracker",
    frequency: "2.402 - 2.480 GHz (BLE channels)",
    freqRangeMhz: [2402, 2480],
    modulation: "BLE advertising",
    pattern: "Continuous or near-continuous advertisement (often more frequent than brand-name trackers)",
    detectability: "high",
    detectedBy: ["BLE Scan (Pi)"],
    markers: [
      "Manufacturer ID from a generic chipset OEM (Realtek, Espressif, Nordic Semi, MediaTek) rather than a tracker brand",
      "Static (non-randomized) MAC address — cheap firmware skips MAC privacy that brand-name trackers implement",
      "Continuous BLE advertising with no apparent purpose (not a phone, not a wearable, not an audio device)",
      "Generic / empty / serial-number-style device name (e.g. 'iTAG', 'BT-001', '', or hex digits)",
      "Low TX power consistent with a coin-cell battery (RSSI low even nearby)",
      "Appears in 'unknown' BLE scan rows that don't match any device the operator can identify",
    ],
    countermeasure:
      "Physically search for the tag — check bags, coats, vehicle undercarriage, seat cushions, pocket linings, child car seats. Cheap tags are often hidden in items frequently carried but not searched (clothing seams, gift wrapping, the foam padding inside a phone case). Power down or physically remove. If found in a vehicle, also sweep the OBD-II port and wheel wells for paired cellular tracker — cheap-BLE-tag-as-bluetooth-companion-to-a-cellular-tracker is a common pattern.",
    notes:
      "Distinct from the brand-name ble_tracker entry. Brand-name trackers (AirTag, Tile, SmartTag) have known manufacturer IDs and Find My / network-effect features. No-name tags are simpler: continuous BLE beacon, often Chinese-OEM chipset, very cheap ($5-15 on Amazon). The threat model is the same (stalking, theft tracking, vehicle following) but detection relies on BEHAVIORAL markers, not manufacturer ID lookup.",
  },
  {
    id: "iot_rogue",
    name: "Compromised / Rogue IoT Device",
    category: "iot_rogue",
    frequency: "2.4 GHz WiFi / BLE / cellular",
    freqRangeMhz: [2400, 2500],
    modulation: "802.11 / BLE / cellular",
    pattern: "Unexpected network traffic from a 'smart' device",
    detectability: "medium",
    detectedBy: ["WiFi Quick Scan", "Port Scan", "Service Enumeration"],
    markers: [
      "IoT device on the target network the client did not install",
      "Known IoT device with unexpected outbound connections",
      "Open ports / services that do not match the device's documented functionality",
      "Firmware version mismatches with vendor's current release",
    ],
    countermeasure:
      "Isolate the device, capture its traffic for analysis, and check for known firmware vulnerabilities. If compromise is suspected, factory reset or replace.",
    notes:
      "Most realistic threat vector for SMB TSCM clients. A compromised smart speaker or security camera can be remotely weaponized as a listening device.",
  },
];

/**
 * Bluetooth SIG company identifier constants (canonical values fetched 2026-05-15
 * from the bluetooth-SIG/public Bitbucket repo). These are stable forever —
 * Bluetooth SIG company IDs are append-only and never re-assigned.
 *
 * IMPORTANT: matcher hits on these IDs are HYPOTHESES not confirmations. Apple
 * ID 0x004C is broadcast by every Apple device (AirPods, iPhones, AirTags) —
 * matching alone doesn't prove a tracking device, just narrows the candidate
 * set. Operator must combine with ownership context + Find My beacon format
 * + RSSI behavior to confirm.
 */
export const MANUFACTURER_IDS = {
  APPLE: 76,      // 0x004C
  TILE: 62,       // 0x003E
  SAMSUNG: 117,   // 0x0075
  GOOGLE: 224,    // 0x00E0
  CHIPOLO: 2243,  // 0x08C3
  ANKER: 3266,    // 0x0CC2 — Anker Innovations (Eufy parent — Eufy not separately registered)
} as const;

/**
 * Extract the 16-bit short form of a Bluetooth service UUID from its 128-bit
 * canonical string representation. Returns null if the UUID is not in the
 * standard Bluetooth base UUID space (which would mean it's a vendor-custom
 * UUID, not a SIG-assigned short).
 *
 * The Bluetooth base UUID is `00000000-0000-1000-8000-00805f9b34fb`; any
 * 16-bit short maps onto it at offset 0-7 of the leftmost group.
 */
export function shortUuidFromFullUuid(fullUuid: string): number | null {
  if (!fullUuid || typeof fullUuid !== "string") return null;
  const lower = fullUuid.toLowerCase();
  const BLE_BASE_SUFFIX = "-0000-1000-8000-00805f9b34fb";
  if (!lower.endsWith(BLE_BASE_SUFFIX)) return null;
  const firstGroup = lower.split("-")[0];
  if (!/^[0-9a-f]{8}$/.test(firstGroup)) return null;
  // First 4 hex chars are the high half; for SIG-assigned shorts they're zero
  // and the short lives in the last 4. We accept any value but flag non-zero
  // high halves later — for now, return the low 4 hex chars as the short.
  const high = parseInt(firstGroup.substring(0, 4), 16);
  const low = parseInt(firstGroup.substring(4, 8), 16);
  if (high !== 0) return null; // 32-bit UUID, not a 16-bit short
  return low;
}

/**
 * Filter devices by frequency range — useful when the operator wants to know
 * what kinds of surveillance devices could be responsible for a signal seen
 * in a specific band.
 */
export function devicesMatchingFrequency(
  freqMhz: number,
): SurveillanceDevice[] {
  return SURVEILLANCE_DEVICES.filter(
    (d) => freqMhz >= d.freqRangeMhz[0] && freqMhz <= d.freqRangeMhz[1],
  );
}

/**
 * Match a BLE-scan device against library entries via manufacturer IDs and/or
 * service UUIDs. Returns deduplicated matches. Either or both inputs can be
 * provided — empty inputs return empty results.
 *
 * Hits here are HYPOTHESES, not confirmations. See MANUFACTURER_IDS docstring.
 */
export function devicesMatchingBLE(input: {
  manufacturerIds?: number[];
  serviceUuids16?: number[];
}): SurveillanceDevice[] {
  const mfgIds = input.manufacturerIds ?? [];
  const svcIds = input.serviceUuids16 ?? [];
  if (mfgIds.length === 0 && svcIds.length === 0) return [];
  const matched = new Set<SurveillanceDevice>();
  for (const d of SURVEILLANCE_DEVICES) {
    const dMfg = d.manufacturerIds ?? [];
    const dSvc = d.serviceUuids16 ?? [];
    if (dMfg.length === 0 && dSvc.length === 0) continue;
    if (mfgIds.some((id) => dMfg.includes(id))) {
      matched.add(d);
      continue;
    }
    if (svcIds.some((id) => dSvc.includes(id))) {
      matched.add(d);
    }
  }
  return Array.from(matched);
}

/**
 * Filter by category — used by the TSCM workspace category browser.
 */
export function devicesInCategory(
  category: DeviceCategory,
): SurveillanceDevice[] {
  return SURVEILLANCE_DEVICES.filter((d) => d.category === category);
}

/**
 * Human-readable category labels for UI display.
 */
export const CATEGORY_LABELS: Record<DeviceCategory, string> = {
  wireless_camera: "Wireless Cameras",
  audio_bug: "Audio Bugs",
  cellular_bug: "Cellular Eavesdroppers",
  ble_tracker: "BLE Trackers",
  wifi_bug: "WiFi Bugs",
  gps_tracker: "GPS Trackers",
  dect_tap: "DECT Phone Taps",
  body_wire: "Body Wires",
  iot_rogue: "Compromised IoT",
};
