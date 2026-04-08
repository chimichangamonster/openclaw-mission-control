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
    notes: "Very common in personal-surveillance / stalking cases. Always scan for these in executive protection sweeps.",
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
