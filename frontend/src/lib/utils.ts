import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Extract plain text from gateway message content.
 * Gateway returns content as `string` or `Array<{type:"text", text:string}>`.
 */
export function extractTextContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .filter(
        (p): p is { type: string; text: string } =>
          typeof p === "object" &&
          p !== null &&
          p.type === "text" &&
          typeof p.text === "string",
      )
      .map((p) => p.text)
      .join("\n");
  }
  // Handle nested message objects (gateway sometimes wraps content — e.g.
  // assistant turn stored as {role, content, timestamp, stopReason, usage,
  // api, provider, model} where .content is a string or content-blocks array).
  if (content && typeof content === "object") {
    const obj = content as Record<string, unknown>;
    if (typeof obj.content === "string") return obj.content;
    if (Array.isArray(obj.content)) return extractTextContent(obj.content);
    if (typeof obj.text === "string") return obj.text;
    // Last resort — JSON stringify to prevent [object Object]
    try {
      return JSON.stringify(content);
    } catch {
      return "";
    }
  }
  return String(content ?? "");
}
