"use client";

import { useEffect } from "react";

const URL_RE = /(https?:\/\/[^\s<>"']+|www\.[^\s<>"']+)/gi;
const TRAILING_RE = /[),.;:!?]+$/;
const INTERNAL_MESSAGE_SELECTOR = ".imail-route-webmail article .whitespace-pre-wrap";

function splitTrailing(value: string) {
  const match = value.match(TRAILING_RE);
  if (!match) return { token: value, trailing: "" };
  return { token: value.slice(0, -match[0].length), trailing: match[0] };
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

  // A plain-text reply can contain rows made only from `>` quote markers.
  // Showing those markers is noisy and was the main visual defect in the
  // internal reader. Keep real quoted text, but omit empty quote rows.
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

function renderStructuredMail(container: HTMLElement) {
  // The mutation observer fires again after replaceChildren(). Avoid a loop,
  // but allow React to replace the body text when a different message opens.
  // In that case these structured child rows disappear and we render again.
  if (container.querySelector(":scope > [data-imail-mail-line='true']")) return;

  const source = (container.textContent || "").replace(/\r\n?/g, "\n");
  const fragment = document.createDocumentFragment();
  const lines = source.split("\n");
  let rendered = 0;

  for (const line of lines) {
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

function enhanceVisibleMail() {
  document.querySelectorAll(INTERNAL_MESSAGE_SELECTOR).forEach((container) => {
    if (container instanceof HTMLElement) renderStructuredMail(container);
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
