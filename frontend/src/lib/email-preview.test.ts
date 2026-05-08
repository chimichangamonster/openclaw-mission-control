import { describe, expect, it } from "vitest";

import {
  inferPreviewMimeType,
  isImage,
  isPdf,
  isPreviewable,
  isText,
} from "./email-preview";

describe("email-preview", () => {
  describe("isImage", () => {
    it("matches by content_type", () => {
      expect(isImage({ filename: "x", content_type: "image/png" })).toBe(true);
      expect(isImage({ filename: "x", content_type: "image/svg+xml" })).toBe(true);
    });
    it("matches by extension when content_type is missing", () => {
      expect(isImage({ filename: "photo.JPG", content_type: null })).toBe(true);
      expect(isImage({ filename: "logo.svg" })).toBe(true);
    });
    it("rejects non-images", () => {
      expect(isImage({ filename: "doc.pdf", content_type: "application/pdf" })).toBe(false);
      expect(isImage({ filename: "data.json" })).toBe(false);
    });
  });

  describe("isPdf", () => {
    it("matches by content_type", () => {
      expect(isPdf({ filename: "x", content_type: "application/pdf" })).toBe(true);
    });
    it("matches by extension", () => {
      expect(isPdf({ filename: "REPORT.PDF" })).toBe(true);
    });
    it("rejects non-pdfs", () => {
      expect(isPdf({ filename: "photo.png" })).toBe(false);
    });
  });

  describe("isText", () => {
    it("matches text/* content types", () => {
      expect(isText({ filename: "x", content_type: "text/plain" })).toBe(true);
      expect(isText({ filename: "x", content_type: "text/csv" })).toBe(true);
      expect(isText({ filename: "x", content_type: "text/html" })).toBe(true);
    });
    it("matches application/json and application/xml", () => {
      expect(isText({ filename: "x", content_type: "application/json" })).toBe(true);
      expect(isText({ filename: "x", content_type: "application/xml" })).toBe(true);
    });
    it("matches by extension when content_type is missing", () => {
      expect(isText({ filename: "alert.log" })).toBe(true);
      expect(isText({ filename: "config.yaml" })).toBe(true);
      expect(isText({ filename: "package.json" })).toBe(true);
      expect(isText({ filename: "notes.md" })).toBe(true);
      expect(isText({ filename: "data.csv" })).toBe(true);
    });
    it("rejects binary types", () => {
      expect(isText({ filename: "x", content_type: "application/pdf" })).toBe(false);
      expect(isText({ filename: "x", content_type: "image/png" })).toBe(false);
      expect(isText({ filename: "report.docx" })).toBe(false);
    });
  });

  describe("isPreviewable", () => {
    it("covers image + PDF + text classes", () => {
      expect(isPreviewable({ filename: "photo.png" })).toBe(true);
      expect(isPreviewable({ filename: "doc.pdf" })).toBe(true);
      expect(isPreviewable({ filename: "log.txt" })).toBe(true);
      expect(isPreviewable({ filename: "data.json" })).toBe(true);
    });
    it("rejects DOCX/XLSX (Tier B, not yet supported)", () => {
      expect(isPreviewable({ filename: "report.docx" })).toBe(false);
      expect(isPreviewable({ filename: "budget.xlsx" })).toBe(false);
      expect(isPreviewable({ filename: "deck.pptx" })).toBe(false);
    });
    it("rejects unknown binary types", () => {
      expect(isPreviewable({ filename: "archive.zip" })).toBe(false);
      expect(isPreviewable({ filename: "binary.bin" })).toBe(false);
    });
  });

  describe("inferPreviewMimeType", () => {
    it("returns null for unknown extensions", () => {
      expect(inferPreviewMimeType("file.bin")).toBeNull();
      expect(inferPreviewMimeType("noext")).toBeNull();
    });
    it("returns the right MIME for images and PDF", () => {
      expect(inferPreviewMimeType("a.pdf")).toBe("application/pdf");
      expect(inferPreviewMimeType("a.PNG")).toBe("image/png");
      expect(inferPreviewMimeType("a.jpg")).toBe("image/jpeg");
      expect(inferPreviewMimeType("a.svg")).toBe("image/svg+xml");
    });
    it("returns text MIMEs for Tier A formats", () => {
      expect(inferPreviewMimeType("alerts.log")).toBe("text/plain");
      expect(inferPreviewMimeType("config.yaml")).toBe("text/plain");
      expect(inferPreviewMimeType("notes.md")).toBe("text/plain");
      expect(inferPreviewMimeType("data.json")).toBe("application/json");
      expect(inferPreviewMimeType("rss.xml")).toBe("application/xml");
      expect(inferPreviewMimeType("report.csv")).toBe("text/csv");
      expect(inferPreviewMimeType("page.html")).toBe("text/html");
    });
  });
});
