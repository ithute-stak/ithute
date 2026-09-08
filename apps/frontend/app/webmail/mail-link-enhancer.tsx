"use client";

import { useEffect } from "react";

import { webmail } from "./mail-types";

const URL_RE = /(https?:\/\/[^\s<>"']+|www\.[^\s<>"']+)/gi;
const TRAILING_RE = /[),.;:!?]+$/;
const INTERNAL_MESSAGE_SELECTOR = ".imail-route-webmail article .whitespace-pre-wrap";
const UID_RE = /^\d+$/;

type MessageTarget = {
  uid: string;
  folder: string;
  key: string;
};

type RichMessageContent = {
  body_html?: string;
  has_html?: boolean;
  remote_images_blocked?: number;
};

const richContentRequests = new Map<string, Promise<RichMessageContent | null>>();

function splitTrailing(value: string) {
  const match = value.match(TRAILING_RE);
  if (!match) return { token: value, trailing: "" };
  return { token: value.slice(0, -match[0].length), trailing: match[0] };
}

function currentMessageTarget(): MessageTarget | null {
  const params = new URLSearchParams(window.location.search);
  const uid = params.get("message") || "";
  if (!UID_RE.test(uid)) return null;
  const folder = params.get("folder") || "INBOX";
  return { uid, folder, key: `${folder}\u0000${uid}` };
}

function appendLinkifiedText(parent: HTMLElement, value: string) {
  let cursor = 0;
  let index = 0;

  for (const match of value.matchAll(URL_RE)) {
    const start = match.index ?? 0;
    if (start > cursor) parent.append(document.createTextNode(value.slice(cursor, start)));

    const raw = match[0];
    const { token, trailing } = splitTrailing(raw);
    if (!token) {
      parent.append(document.createTextNode(raw));
      cursor = start + raw.length;
      continue;
    }

    const anchor = document.createElement("a");
    anchor.href = /^https?:\/\//i.test(token) ? token : `https://${token}`;
    anchor.textContent = token;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer nofollow";
    anchor.className = "imail-detected-link break-all";
    anchor.dataset.imailDetectedLink = String(index++);
    parent.append(anchor);
    if (trailing) parent.append(document.createTextNode(trailing));
    cursor = start + raw.length;
  }

  if (cursor < value.length) parent.append(document.createTextNode(value.slice(cursor)));
}

function buildMailLine(line: string) {
  const quoteMatch = line.match(/^\s*(>+)\s?(.*)$/);
  const quoted = Boolean(quoteMatch);
  const value = quoted ? quoteMatch?.[2] || "" : line;

  // Plain-text replies often contain rows made only from `>` markers. Those
  // rows are transport syntax, not useful message content, so hide them while
  // retaining real quoted text in a readable quote block.
  if (quoted && !value.trim()) return null;

  const row = document.createElement("div");
  row.dataset.imailMailLine = "true";
  row.className = quoted
    ? "imail-mail-quote my-0 min-h-[1.75em] border-l-2 border-[#d4e6de] bg-[#f8fbfa] py-0.5 pl-3 pr-2 text-[#65766f]"
    : "imail-mail-line min-h-[1.75em]";

  if (!value) {
    row.append(document.createElement("br"));
    return row;
  }

  appendLinkifiedText(row, value);
  return row;
}

function renderStructuredText(container: HTMLElement) {
  if (container.querySelector(":scope > [data-imail-mail-line='true']")) return;

  const source = (container.textContent || "").replace(/\r\n?/g, "\n");
  const fragment = document.createDocumentFragment();
  let rendered = 0;

  for (const line of source.split("\n")) {
    const row = buildMailLine(line);
    if (!row) continue;
    fragment.append(row);
    rendered += 1;
  }

  if (!rendered) {
    const empty = document.createElement("div");
    empty.dataset.imailMailLine = "true";
    empty.className = "imail-mail-line min-h-[1.75em]";
    empty.append(document.createElement("br"));
    fragment.append(empty);
  }

  container.replaceChildren(fragment);
  container.dataset.imailStructuredMail = "true";
}

function richContent(target: MessageTarget) {
  const existing = richContentRequests.get(target.key);
  if (existing) return existing;

  const request = (async (): Promise<RichMessageContent | null> => {
    try {
      const response = await webmail(
        `/messages/${target.uid}/content?folder=${encodeURIComponent(target.folder)}`,
      );
      if (!response.ok) return null;
      const payload = (await response.json()) as RichMessageContent;
      return payload.has_html && payload.body_html?.trim() ? payload : null;
    } catch {
      return null;
    }
  })();

  richContentRequests.set(target.key, request);
  return request;
}

function hardenRichContent(root: HTMLElement) {
  // The API already sanitizes message HTML and removes remote images. Keep a
  // client-side defensive layer as well because email content is untrusted.
  root.querySelectorAll("script, style, iframe, object, embed, form, img, svg, link, meta").forEach((node) => node.remove());

  root.querySelectorAll("a").forEach((anchor) => {
    const href = anchor.getAttribute("href") || "";
    if (!/^(https?:|mailto:)/i.test(href)) {
      anchor.removeAttribute("href");
      return;
    }
    if (/^https?:/i.test(href)) {
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer nofollow";
    }
    anchor.classList.add("imail-detected-link");
  });
}

function renderRichContent(
  container: HTMLElement,
  target: MessageTarget,
  payload: RichMessageContent,
) {
  if (!payload.body_html?.trim()) return;

  const root = document.createElement("div");
  root.dataset.imailRichRoot = "true";
  root.className = "imail-rich-message";
  root.innerHTML = payload.body_html;
  hardenRichContent(root);

  container.replaceChildren(root);
  container.dataset.imailContentKey = target.key;
  container.dataset.imailRichMail = "true";
  container.dataset.imailBlockedImages = String(payload.remote_images_blocked || 0);
}

async function enhanceContainer(container: HTMLElement) {
  const target = currentMessageTarget();
  if (!target) {
    renderStructuredText(container);
    return;
  }

  if (container.dataset.imailContentKey !== target.key) {
    container.dataset.imailContentKey = target.key;
    delete container.dataset.imailRichMail;
    delete container.dataset.imailBlockedImages;
  }

  if (container.querySelector(":scope > [data-imail-rich-root='true']")) return;

  // Keep the reader useful immediately while the safe rich MIME part is read.
  // If the message is plain-text only, this remains the final rendering.
  renderStructuredText(container);

  const requestKey = target.key;
  const payload = await richContent(target);
  if (!payload) return;

  const liveTarget = currentMessageTarget();
  if (
    !liveTarget ||
    liveTarget.key !== requestKey ||
    container.dataset.imailContentKey !== requestKey ||
    !document.contains(container)
  ) {
    return;
  }

  renderRichContent(container, target, payload);
}

function enhanceVisibleMail() {
  document.querySelectorAll(INTERNAL_MESSAGE_SELECTOR).forEach((container) => {
    if (container instanceof HTMLElement) void enhanceContainer(container);
  });
}

export function MailLinkEnhancer() {
  useEffect(() => {
    let frame = 0;
    const schedule = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(enhanceVisibleMail);
    };

    schedule();
    const root = document.querySelector(".sourceGmailSkin") || document.body;
    const observer = new MutationObserver(schedule);
    observer.observe(root, { childList: true, subtree: true, characterData: true });

    return () => {
      observer.disconnect();
      window.cancelAnimationFrame(frame);
    };
  }, []);

  return null;
}
