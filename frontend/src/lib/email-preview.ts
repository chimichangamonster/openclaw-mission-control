/**
 * Pure helpers for the email-attachment inline preview surface.
 *
 * Extracted from `app/email/[messageId]/page.tsx` so the previewability
 * matrix and MIME inference can be unit-tested without rendering React.
 *
 * Tier A scope (item 131c, 2026-05-08): images + PDF + text-class formats
 * (TXT/CSV/JSON/MD/XML/LOG/YAML/HTML). Browsers render text/* natively in
 * iframes; no backend extraction is needed for these.
 *
 * Out of scope: DOCX/XLSX/PPTX (Tier B, deferred until a real-user trigger).
 */

export interface PreviewableAttachment {
  filename: string;
  content_type?: string | null;
}

const _IMAGE_EXTS = /\.(jpg|jpeg|png|gif|webp|svg)$/;
const _TEXT_EXTS = /\.(txt|csv|tsv|json|jsonl|md|markdown|xml|log|yaml|yml|ini|conf|html|htm)$/;

export function isImage(att: PreviewableAttachment): boolean {
  const ct = (att.content_type ?? "").toLowerCase();
  const fn = att.filename.toLowerCase();
  return ct.startsWith("image/") || _IMAGE_EXTS.test(fn);
}

export function isPdf(att: PreviewableAttachment): boolean {
  const ct = (att.content_type ?? "").toLowerCase();
  const fn = att.filename.toLowerCase();
  return ct === "application/pdf" || fn.endsWith(".pdf");
}

export function isText(att: PreviewableAttachment): boolean {
  const ct = (att.content_type ?? "").toLowerCase();
  const fn = att.filename.toLowerCase();
  // text/plain, text/csv, text/html, application/json, application/xml, etc.
  if (ct.startsWith("text/")) return true;
  if (ct === "application/json" || ct === "application/xml") return true;
  return _TEXT_EXTS.test(fn);
}

export function isPreviewable(att: PreviewableAttachment): boolean {
  return isImage(att) || isPdf(att) || isText(att);
}

/**
 * Best-effort MIME type to send to the blob constructor when the provider's
 * Content-Type is missing/octet-stream. Browsers need a real type to render
 * text and PDF inline in iframes.
 *
 * Returns null when no inference is possible — caller falls back to whatever
 * the response Content-Type says (or octet-stream).
 */
export function inferPreviewMimeType(filename: string): string | null {
  const fn = filename.toLowerCase();
  if (fn.endsWith(".pdf")) return "application/pdf";
  if (fn.endsWith(".png")) return "image/png";
  if (fn.endsWith(".gif")) return "image/gif";
  if (fn.endsWith(".webp")) return "image/webp";
  if (fn.endsWith(".svg")) return "image/svg+xml";
  if (fn.endsWith(".jpg") || fn.endsWith(".jpeg")) return "image/jpeg";

  // Tier A text-class fallbacks. Browser uses these to syntax-highlight or
  // at least render as plain text in <iframe>.
  if (fn.endsWith(".json") || fn.endsWith(".jsonl")) return "application/json";
  if (fn.endsWith(".xml")) return "application/xml";
  if (fn.endsWith(".html") || fn.endsWith(".htm")) return "text/html";
  if (fn.endsWith(".csv") || fn.endsWith(".tsv")) return "text/csv";
  if (
    fn.endsWith(".txt") ||
    fn.endsWith(".md") ||
    fn.endsWith(".markdown") ||
    fn.endsWith(".log") ||
    fn.endsWith(".yaml") ||
    fn.endsWith(".yml") ||
    fn.endsWith(".ini") ||
    fn.endsWith(".conf")
  ) {
    return "text/plain";
  }

  return null;
}
