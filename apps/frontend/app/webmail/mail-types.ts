export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8006/api/v1";
export const PAGE_SIZE = 50;

export type Folder = { name: string; raw: string };
export type FolderCount = { name: string; messages: number; unseen: number };
export type Attachment = { index: number; filename: string; content_type: string; size: number };
export type Contact = { email: string; name?: string };

export type MessageRow = {
  uid: string;
  message_id: string;
  in_reply_to?: string;
  references?: string;
  from: string;
  to: string;
  cc: string;
  reply_to?: string;
  subject: string;
  date: string;
  seen: boolean;
  flagged: boolean;
  answered: boolean;
  draft?: boolean;
  snippet: string;
  attachments: Attachment[];
  body_text?: string;
};

export type ComposeState = {
  to: string;
  cc: string;
  bcc: string;
  subject: string;
  bodyText: string;
  bodyHtml: string;
  in_reply_to: string;
  references: string;
  attachments: { filename: string; content_type: string; content_b64: string }[];
};

export type Density = "comfortable" | "compact";
export type InboxView = "primary" | "starred" | "attachments";

export const emptyCompose: ComposeState = {
  to: "",
  cc: "",
  bcc: "",
  subject: "",
  bodyText: "",
  bodyHtml: "",
  in_reply_to: "",
  references: "",
  attachments: [],
};

async function externalSession(path: string, init?: RequestInit) {
  return fetch(`${API}/webmail/external${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
}

export async function webmail(path: string, init?: RequestInit) {
  const method = String(init?.method || "GET").toUpperCase();

  // A previously verified external mailbox is a normal mailbox login. Check
  // the remembered profile first so it never records a failed hosted-mailbox
  // attempt before reaching its real mail server. A registry miss is cheap and
  // immediately falls through to the hosted Ithute mailbox path.
  if (
    typeof window !== "undefined" &&
    path === "/session" &&
    method === "POST" &&
    typeof init?.body === "string"
  ) {
    try {
      const body = JSON.parse(init.body) as { address?: string; password?: string };
      const address = String(body.address || "").trim().toLowerCase();
      const password = String(body.password || "");
      if (address && password) {
        const external = await externalSession("/known-session", {
          method: "POST",
          body: JSON.stringify({ address, password }),
        });
        if (external.ok) {
          window.location.assign("/webmail/external");
          return external;
        }
        if (external.status !== 404) return external;
      }
    } catch {
      // A malformed local request still falls through to the normal endpoint.
    }
  }

  const response = await fetch(`${API}/webmail${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });

  if (typeof window !== "undefined" && path === "/session" && method === "GET" && !response.ok) {
    try {
      const external = await externalSession("/session");
      if (external.ok) {
        window.location.assign("/webmail/external");
        return external;
      }
    } catch {
      // Keep the original hosted-mailbox session result.
    }
  }

  return response;
}

export function initials(value: string) {
  const text = value.replace(/<.*?>/g, "").trim();
  return (
    text
      .split(/[\s@._-]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((x) => x[0]?.toUpperCase())
      .join("") || "M"
  );
}

export function splitAddresses(value: string) {
  return value
    .split(/[;,]/)
    .map((x) => x.trim())
    .filter(Boolean);
}

export function addressOnly(value: string) {
  const match = value.match(/<([^>]+)>/);
  return (match?.[1] || value).trim();
}

export function senderName(value: string) {
  const text = value.replace(/<.*?>/g, "").replace(/^"|"$/g, "").trim();
  return text || addressOnly(value) || "Unknown sender";
}

export function humanBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

export function shortDate(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const now = new Date();
  if (parsed.toDateString() === now.toDateString()) {
    return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  if (parsed.getFullYear() === now.getFullYear()) {
    return parsed.toLocaleDateString([], { day: "2-digit", month: "short" });
  }
  return parsed.toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric" });
}

export function htmlEscape(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function textToHtml(value: string) {
  return htmlEscape(value).replace(/\n/g, "<br>");
}

export function stripHtml(value: string) {
  const withBreaks = value
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|li|blockquote|pre)>/gi, "\n");
  if (typeof document === "undefined") {
    return withBreaks.replace(/<[^>]*>/g, " ").replace(/[ \t]+/g, " ").replace(/\n\s*\n\s*\n+/g, "\n\n").trim();
  }
  const node = document.createElement("div");
  node.innerHTML = withBreaks;
  return (node.textContent || node.innerText || "")
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n\s*\n\s*\n+/g, "\n\n")
    .trim();
}

export function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  return Boolean(target.closest("input, textarea, select, [contenteditable='true']"));
}

export function folderKind(name: string) {
  const value = name.toLowerCase();
  if (value === "inbox") return "inbox";
  if (value.includes("sent")) return "sent";
  if (value.includes("draft")) return "drafts";
  if (value.includes("trash") || value.includes("bin")) return "trash";
  if (value.includes("archive")) return "archive";
  return "folder";
}

export function draftStorageKey(address: string) {
  return `ithute-webmail-local-draft:${address.toLowerCase()}`;
}
