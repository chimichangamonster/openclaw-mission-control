import { describe, it, expect } from "vitest";
import {
  devicesMatchingFrequency,
  devicesInCategory,
  SURVEILLANCE_DEVICES,
} from "./tscm-device-library";

describe("devicesMatchingFrequency", () => {
  it("matches a 2.4 GHz WiFi-band peak against multiple fingerprints", () => {
    const matches = devicesMatchingFrequency(2440);
    const ids = matches.map((d) => d.id).sort();
    expect(ids).toEqual([
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

  it("matches a 1900 MHz cellular-band peak against cellular eavesdropper + GPS tracker + DECT tap", () => {
    const matches = devicesMatchingFrequency(1900);
    const ids = matches.map((d) => d.id).sort();
    expect(ids).toEqual(["cellular_bug_gsm", "dect_tap", "gps_tracker"]);
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

  it("includes BOTH cellular bug AND GPS tracker for 850 MHz uplink (overlapping ranges)", () => {
    const matches = devicesMatchingFrequency(850);
    const ids = matches.map((d) => d.id).sort();
    expect(ids).toEqual([
      "audio_bug_sub1ghz",
      "cellular_bug_gsm",
      "gps_tracker",
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

  it("returns the BLE tracker entry for ble_tracker category", () => {
    const trackers = devicesInCategory("ble_tracker");
    expect(trackers.map((d) => d.id)).toEqual(["ble_tracker"]);
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
