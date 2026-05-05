/**
 * customFetch header-handling tests.
 *
 * Item 109 (planning-next-sprint.md): customFetch was unconditionally setting
 * `Content-Type: application/json` whenever a body was present, including
 * `FormData`. That clobbers the browser's auto-generated
 * `multipart/form-data; boundary=...` header and breaks every multipart upload
 * (regulatory import-html, org-context bulk upload, doc-gen logo upload, chat
 * file attach, email attachment send, ...).
 *
 * The fix is a 1-line change to skip the JSON header when the body is a
 * FormData instance. These tests lock that contract so a future mutator
 * refactor can't silently regress.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/auth/localAuth", () => ({
  getLocalAuthToken: vi.fn(() => null),
  isLocalAuthMode: vi.fn(() => false),
}));

vi.mock("@/auth/wechatAuth", () => ({
  getWeChatAuthToken: vi.fn(() => null),
}));

vi.mock("@/lib/api-base", () => ({
  getApiBaseUrl: vi.fn(() => "http://test.local"),
}));

import { customFetch } from "./mutator";

const okJsonResponse = () =>
  new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

let fetchSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(okJsonResponse());
});

afterEach(() => {
  fetchSpy.mockRestore();
});

const lastCallHeaders = (): Headers => {
  const init = fetchSpy.mock.calls[0]?.[1] as RequestInit | undefined;
  return new Headers(init?.headers);
};

describe("customFetch Content-Type handling", () => {
  it("does NOT set Content-Type: application/json when body is FormData", async () => {
    const form = new FormData();
    form.append("file", new Blob(["<html></html>"], { type: "text/html" }), "tracker.html");

    await customFetch("/api/v1/regulatory/import-html", {
      method: "POST",
      body: form,
    });

    const headers = lastCallHeaders();
    expect(headers.get("Content-Type")).toBeNull();
  });

  it("preserves an explicit Content-Type header when caller provides one", async () => {
    const form = new FormData();
    form.append("k", "v");

    await customFetch("/x", {
      method: "POST",
      body: form,
      headers: { "Content-Type": "multipart/form-data; boundary=zzz" },
    });

    expect(lastCallHeaders().get("Content-Type")).toBe(
      "multipart/form-data; boundary=zzz",
    );
  });

  it("still sets Content-Type: application/json for plain string bodies", async () => {
    await customFetch("/x", {
      method: "POST",
      body: JSON.stringify({ a: 1 }),
    });

    expect(lastCallHeaders().get("Content-Type")).toBe("application/json");
  });

  it("does not set Content-Type when there is no body", async () => {
    await customFetch("/x", { method: "GET" });

    expect(lastCallHeaders().get("Content-Type")).toBeNull();
  });
});
