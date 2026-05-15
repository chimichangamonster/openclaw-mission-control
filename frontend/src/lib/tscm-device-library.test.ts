import { describe, it, expect } from "vitest";
import {
  devicesMatchingFrequency,
  devicesInCategory,
  devicesMatchingBLE,
  shortUuidFromFullUuid,
  SURVEILLANCE_DEVICES,
  MANUFACTURER_IDS,
} from "./tscm-device-library";

describe("devicesMatchingFrequency", () => {
  it("matches a 2.4 GHz WiFi-band peak against multiple fingerprints", () => {
    const matches = devicesMatchingFrequency(2440);
    const ids = matches.map((d) => d.id).sort();
    expect(ids).toEqual([
      "ble_tag_generic",
      "ble_tracker",
      "iot_rogue",
      "wcam_24ghz",
      "wifi_bug",
    ]);
  });

  it("matches a 433 MHz Sub-GHz peak against the audio bug fingerprint", () => {
    const matches = devicesMatchingFrequency(433);
    const ids = matches.map((d) => d.id);
    expect(ids).toContain("audio_bug_sub1ghz");
    expect(ids).not.toContain("wcam_24ghz");
  });

  it("matches a 1900 MHz cellular-band peak against cellular eavesdropper + GPS tracker (consumer + pro-grade) + DECT tap", () => {
    const matches = devicesMatchingFrequency(1900);
    const ids = matches.map((d) => d.id).sort();
    expect(ids).toEqual([
      "cellular_bug_gsm",
      "dect_tap",
      "gps_tracker",
      "gps_tracker_pro_grade",
    ]);
  });

  it("matches a 5.8 GHz peak against the wireless camera entry with low detectability", () => {
    const matches = devicesMatchingFrequency(5800);
    expect(matches.map((d) => d.id)).toEqual(["wcam_58ghz"]);
    // Honest scope check — the entry is explicit about being invisible to current rig
    expect(matches[0].detectability).toBe("low");
    expect(matches[0].notes).toContain("HONEST SCOPE");
  });

  it("returns empty for an FM-radio-band peak the library does not claim to cover", () => {
    const matches = devicesMatchingFrequency(100);
    expect(matches).toEqual([]);
  });

  it("matches a 470 MHz body-wire-band peak against body wire fingerprint (range boundary)", () => {
    const matches = devicesMatchingFrequency(470);
    expect(matches.map((d) => d.id)).toContain("body_wire_uhf");
  });

  it("matches a 150 MHz body-wire-band peak (other range boundary)", () => {
    const matches = devicesMatchingFrequency(150);
    expect(matches.map((d) => d.id)).toContain("body_wire_uhf");
  });

  it("includes BOTH cellular bug AND GPS tracker (consumer + pro-grade) for 850 MHz uplink (overlapping ranges)", () => {
    const matches = devicesMatchingFrequency(850);
    const ids = matches.map((d) => d.id).sort();
    expect(ids).toEqual([
      "audio_bug_sub1ghz",
      "cellular_bug_gsm",
      "gps_tracker",
      "gps_tracker_pro_grade",
    ]);
  });
});

describe("devicesInCategory", () => {
  it("returns only wireless cameras for the wireless_camera category", () => {
    const cameras = devicesInCategory("wireless_camera");
    expect(cameras.map((d) => d.id).sort()).toEqual([
      "wcam_24ghz",
      "wcam_58ghz",
    ]);
  });

  it("returns BOTH the brand-name BLE tracker AND the generic BLE tag entries for ble_tracker category", () => {
    const trackers = devicesInCategory("ble_tracker");
    expect(trackers.map((d) => d.id).sort()).toEqual([
      "ble_tag_generic",
      "ble_tracker",
    ]);
  });
});

describe("shortUuidFromFullUuid", () => {
  it("extracts the 16-bit short form from a canonical 128-bit BLE UUID string", () => {
    // Apple Find My-style UUID: short form 0xFD6F embedded at offset 0-7 of full UUID
    expect(shortUuidFromFullUuid("0000fd6f-0000-1000-8000-00805f9b34fb")).toBe(0xfd6f);
  });

  it("returns null for a malformed UUID string", () => {
    expect(shortUuidFromFullUuid("not-a-uuid")).toBeNull();
    expect(shortUuidFromFullUuid("")).toBeNull();
  });

  it("returns null for a non-standard UUID that is not a 16-bit short within the Bluetooth base UUID space", () => {
    // Custom service UUID not in Bluetooth base space — the 16-bit projection
    // would be 0xABCD but the base bytes don't match standard form
    expect(shortUuidFromFullUuid("0000abcd-1234-5678-abcd-ef0123456789")).toBeNull();
  });

  it("returns the short form regardless of case in the input string", () => {
    expect(shortUuidFromFullUuid("0000FE9F-0000-1000-8000-00805F9B34FB")).toBe(0xfe9f);
  });
});

describe("devicesMatchingBLE", () => {
  it("matches Apple manufacturer ID (76 = 0x004C) against ble_tracker", () => {
    const matches = devicesMatchingBLE({ manufacturerIds: [MANUFACTURER_IDS.APPLE] });
    expect(matches.map((d) => d.id)).toContain("ble_tracker");
  });

  it("matches Tile manufacturer ID (62 = 0x003E) against ble_tracker", () => {
    const matches = devicesMatchingBLE({ manufacturerIds: [MANUFACTURER_IDS.TILE] });
    expect(matches.map((d) => d.id)).toContain("ble_tracker");
  });

  it("matches Samsung manufacturer ID (117 = 0x0075) against ble_tracker", () => {
    const matches = devicesMatchingBLE({ manufacturerIds: [MANUFACTURER_IDS.SAMSUNG] });
    expect(matches.map((d) => d.id)).toContain("ble_tracker");
  });

  it("matches Google manufacturer ID (224 = 0x00E0) against ble_tracker", () => {
    const matches = devicesMatchingBLE({ manufacturerIds: [MANUFACTURER_IDS.GOOGLE] });
    expect(matches.map((d) => d.id)).toContain("ble_tracker");
  });

  it("matches Chipolo manufacturer ID (2243 = 0x08C3) against ble_tracker", () => {
    const matches = devicesMatchingBLE({ manufacturerIds: [MANUFACTURER_IDS.CHIPOLO] });
    expect(matches.map((d) => d.id)).toContain("ble_tracker");
  });

  it("returns empty for an unknown manufacturer ID and no other inputs", () => {
    const matches = devicesMatchingBLE({ manufacturerIds: [0xffff] });
    expect(matches).toEqual([]);
  });

  it("returns empty when given an empty input (no manufacturer IDs, no service UUIDs)", () => {
    expect(devicesMatchingBLE({})).toEqual([]);
    expect(devicesMatchingBLE({ manufacturerIds: [], serviceUuids16: [] })).toEqual([]);
  });

  it("dedupes when both manufacturer ID and service UUID would match the same device", () => {
    // Apple ID + a service UUID seeded on ble_tracker should still return ONE entry
    const matches = devicesMatchingBLE({
      manufacturerIds: [MANUFACTURER_IDS.APPLE],
      serviceUuids16: [0xfd6f],
    });
    const tracker = matches.filter((d) => d.id === "ble_tracker");
    expect(tracker).toHaveLength(1);
  });

  it("matches by service UUID alone (no manufacturer ID provided)", () => {
    // 0xFD6F is on ble_tracker's serviceUuids16 list per the seed
    const matches = devicesMatchingBLE({ serviceUuids16: [0xfd6f] });
    expect(matches.map((d) => d.id)).toContain("ble_tracker");
  });
});

describe("MANUFACTURER_IDS canonical values (verified against Bluetooth SIG)", () => {
  // These are CANONICAL Bluetooth SIG company identifier values, fetched 2026-05-15
  // from the bluetooth-SIG/public Bitbucket repo. If a future test fails on these,
  // the FIRST thing to check is whether the constants were accidentally modified
  // (they should NOT change — Bluetooth SIG IDs are stable forever).
  it("Apple = 76 (0x004C)", () => {
    expect(MANUFACTURER_IDS.APPLE).toBe(76);
    expect(MANUFACTURER_IDS.APPLE).toBe(0x004c);
  });
  it("Tile = 62 (0x003E)", () => {
    expect(MANUFACTURER_IDS.TILE).toBe(62);
    expect(MANUFACTURER_IDS.TILE).toBe(0x003e);
  });
  it("Samsung = 117 (0x0075)", () => {
    expect(MANUFACTURER_IDS.SAMSUNG).toBe(117);
    expect(MANUFACTURER_IDS.SAMSUNG).toBe(0x0075);
  });
  it("Google = 224 (0x00E0)", () => {
    expect(MANUFACTURER_IDS.GOOGLE).toBe(224);
    expect(MANUFACTURER_IDS.GOOGLE).toBe(0x00e0);
  });
  it("Chipolo = 2243 (0x08C3)", () => {
    expect(MANUFACTURER_IDS.CHIPOLO).toBe(2243);
    expect(MANUFACTURER_IDS.CHIPOLO).toBe(0x08c3);
  });
  it("Anker = 3266 (0x0CC2)", () => {
    expect(MANUFACTURER_IDS.ANKER).toBe(3266);
    expect(MANUFACTURER_IDS.ANKER).toBe(0x0cc2);
  });
});

describe("gps_tracker_pro_grade — concealed-install / pro-grade entry", () => {
  it("exists in the library with neutral framing (no adversary-class language)", () => {
    const entry = SURVEILLANCE_DEVICES.find((d) => d.id === "gps_tracker_pro_grade");
    expect(entry).toBeDefined();
    // Adversary-class language failed code review — the entry must describe
    // DEVICE characteristics, not who deployed it (LE vs PI vs ex-LE vs civilian
    // are all possible deployers of the same device class).
    expect(entry!.name.toLowerCase()).not.toContain("government");
    expect(entry!.name.toLowerCase()).not.toContain("federal");
    expect(entry!.name.toLowerCase()).not.toContain("law enforcement");
    expect(entry!.countermeasure.toLowerCase()).not.toContain("stop the sweep");
  });

  it("is categorized as gps_tracker with low detectability and an honest-scope note", () => {
    const entry = SURVEILLANCE_DEVICES.find((d) => d.id === "gps_tracker_pro_grade");
    expect(entry!.category).toBe("gps_tracker");
    expect(entry!.detectability).toBe("low");
    expect(entry!.notes).toContain("HONEST SCOPE");
  });

  it("matches cellular uplink frequencies (same band as consumer gps_tracker)", () => {
    const matches = devicesMatchingFrequency(900);
    expect(matches.map((d) => d.id)).toContain("gps_tracker_pro_grade");
  });
});

describe("ble_tag_generic — cheap no-name BLE tracker entry", () => {
  it("exists in the library and is distinct from ble_tracker (brand-name entry)", () => {
    const entry = SURVEILLANCE_DEVICES.find((d) => d.id === "ble_tag_generic");
    expect(entry).toBeDefined();
    expect(entry!.id).not.toBe("ble_tracker");
  });

  it("matches the BLE frequency band (same as the brand-name ble_tracker entry)", () => {
    const matches = devicesMatchingFrequency(2450);
    expect(matches.map((d) => d.id)).toContain("ble_tag_generic");
    expect(matches.map((d) => d.id)).toContain("ble_tracker");
  });

  it("has BEHAVIORAL markers (non-random MAC, continuous advertising) not brand-specific markers", () => {
    const entry = SURVEILLANCE_DEVICES.find((d) => d.id === "ble_tag_generic");
    const allMarkers = entry!.markers.join(" ").toLowerCase();
    // At least one marker about MAC behavior or advertising pattern
    expect(allMarkers).toMatch(/mac|advertis|continuous|name/i);
  });

  it("does NOT seed AirTag-class manufacturer IDs (those belong on ble_tracker)", () => {
    const entry = SURVEILLANCE_DEVICES.find((d) => d.id === "ble_tag_generic");
    const ids = entry!.manufacturerIds ?? [];
    expect(ids).not.toContain(MANUFACTURER_IDS.APPLE);
    expect(ids).not.toContain(MANUFACTURER_IDS.TILE);
  });
});

describe("SURVEILLANCE_DEVICES library invariants", () => {
  it("has at least one entry per declared category", () => {
    const categories = new Set(SURVEILLANCE_DEVICES.map((d) => d.category));
    expect(categories.size).toBeGreaterThanOrEqual(9);
  });

  it("every entry has a well-formed freqRangeMhz tuple (start <= end, both positive)", () => {
    for (const d of SURVEILLANCE_DEVICES) {
      const [start, end] = d.freqRangeMhz;
      expect(start).toBeGreaterThan(0);
      expect(end).toBeGreaterThanOrEqual(start);
    }
  });

  it("every entry has a non-empty countermeasure (operator-actionable)", () => {
    for (const d of SURVEILLANCE_DEVICES) {
      expect(d.countermeasure.length).toBeGreaterThan(20);
    }
  });
});
