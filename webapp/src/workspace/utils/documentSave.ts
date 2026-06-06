import { getCsrfToken } from "@/commons/utils/csrfTokenStore";

const API_URL = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

export function normalizeDocumentJsonContent(value: unknown): string {
  try {
    return JSON.stringify(value ?? null);
  } catch {
    return "null";
  }
}

export function normalizeDocumentContent(text: string): string {
  return text
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .replace(/\n\n+/g, "\n\n")
    .replace(/[ \t]+/g, " ")
    .trim();
}

export function sanitizeDocumentContentForSave(content: string): string {
  if (content.includes("<") && content.includes(">")) {
    try {
      if (typeof document !== "undefined") {
        const tempDiv = document.createElement("div");
        tempDiv.innerHTML = content;
        return tempDiv.textContent || "";
      }
    } catch {
      // Fall back to regex below.
    }

    return content.replace(/<[^>]*>/g, "");
  }

  return content;
}

export function hasMeaningfulDocumentChange(
  previousContent: string | null | undefined,
  nextContent: string,
): boolean {
  return (
    normalizeDocumentContent(previousContent ?? "") !==
    normalizeDocumentContent(nextContent)
  );
}

export function hasMeaningfulDocumentJsonChange(
  previousContent: unknown,
  nextContent: unknown,
): boolean {
  return (
    normalizeDocumentJsonContent(previousContent) !==
    normalizeDocumentJsonContent(nextContent)
  );
}

export function sendKeepaliveDocumentSave(
  documentId: number | string,
  content: string,
  contentJson?: unknown,
): boolean {
  if (typeof window === "undefined" || typeof fetch === "undefined") {
    return false;
  }

  const csrfToken = getCsrfToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };

  if (csrfToken) {
    headers["X-CSRFToken"] = csrfToken;
  }

  const url = `${API_URL}/api/v1/documents/by-editor/${documentId}`;

  void fetch(url, {
    method: "PATCH",
    credentials: "include",
    keepalive: true,
    headers,
    body: JSON.stringify({
      content,
      content_markdown: content,
      content_json: contentJson ?? null,
    }),
  }).catch(() => {
    // Best-effort only on page exit.
  });

  return true;
}
