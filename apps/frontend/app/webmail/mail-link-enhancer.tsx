"use client";

import { useEffect } from "react";

const URL_RE = /(https?:\/\/[^\s<>"']+|www\.[^\s<>"']+)/gi;
const TRAILING_RE = /[),.;:!?]+$/;

function splitTrailing(value: string) {
  const match = value.match(TRAILING_RE);
  if (!match) return { token: value, trailing: "" };
  return { token: value.slice(0, -match[0].length), trailing: match[0] };
}

function enhanceTextNode(node: Text) {
  const value = node.nodeValue || "";
  if (!URL_RE.test(value)) {
    URL_RE.lastIndex = 0;
    return;
  }
  URL_RE.lastIndex = 0;

  const fragment = document.createDocumentFragment();
  let cursor = 0;
  let matched = false;

  for (const match of value.matchAll(URL_RE)) {
    const start = match.index ?? 0;
    if (start > cursor) fragment.append(document.createTextNode(value.slice(cursor, start)));

    const raw = match[0];
    const { token, trailing } = splitTrailing(raw);
    if (!token) {
      fragment.append(document.createTextNode(raw));
      cursor = start + raw.length;
      continue;
    }

    const anchor = document.createElement("a");
    anchor.href = /^https?:\/\//i.test(token) ? token : `https://${token}`;
    anchor.textContent = token;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer nofollow";
    anchor.className = "imail-detected-link";
    anchor.dataset.imailDetectedLink = "true";
    fragment.append(anchor);
    if (trailing) fragment.append(document.createTextNode(trailing));
    cursor = start + raw.length;
    matched = true;
  }

  if (!matched) return;
  if (cursor < value.length) fragment.append(document.createTextNode(value.slice(cursor)));
  node.replaceWith(fragment);
}

function enhanceContainer(container: Element) {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  let current = walker.nextNode();
  while (current) {
    const parent = current.parentElement;
    if (
      parent &&
      !parent.closest("a, button, input, textarea, select, code, pre, [contenteditable='true']") &&
      (current.nodeValue || "").match(URL_RE)
    ) {
      nodes.push(current as Text);
    }
    URL_RE.lastIndex = 0;
    current = walker.nextNode();
  }
  nodes.forEach(enhanceTextNode);
}

function enhanceVisibleMail() {
  document
    .querySelectorAll(".imail-route-webmail article .whitespace-pre-wrap")
    .forEach(enhanceContainer);
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
