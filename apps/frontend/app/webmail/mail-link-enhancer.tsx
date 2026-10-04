"use client";

import { useEffect } from "react";

import { webmail } from "./mail-types";

const URL_RE = /(https?:\/\/[^\s<>"']+|www\.[^\s<>"']+)/gi;
const TRAILING_RE = /[),.;:!?]+$/;
const INTERNAL_MESSAGE_SELECTOR = ".imail-route-webmail [data-imail-message-body='true']";
const UID_RE = /^\d+$/;
const TRUSTED_IMAGE_SENDERS_KEY = "ithute-webmail-trusted-image-senders";

type MessageTarget = {
  uid: string;
  folder: string;
  key: string;
};

type RichMessageContent = {
  body_html?: string;
  has_html?: boolean;
  remote_images_blocked?: number;
  remote_images_total?: number;
  remote_images_shown?: boolean;
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

function senderDomain(container: HTMLElement) {
  const sender = (container.dataset.imailSender || "").trim().toLowerCase();
  const at = sender.lastIndexOf("@");
  return at > 0 ? sender.slice(at + 1) : "";
}

function trustedImageSenders() {
  try {
    const raw = window.localStorage.getItem(TRUSTED_IMAGE_SENDERS_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed.map((value) => String(value).toLowerCase()) : []);
  } catch {
    return new Set<string>();
  }
}

function saveTrustedImageSender(domain: string) {
  if (!domain) return;
  const trusted = trustedImageSenders();
  trusted.add(domain.toLowerCase());
  window.localStorage.setItem(TRUSTED_IMAGE_SENDERS_KEY, JSON.stringify(Array.from(trusted).sort()));
}

function removeTrustedImageSender(domain: string) {
  if (!domain) return;
  const trusted = trustedImageSenders();
  trusted.delete(domain.toLowerCase());
  window.localStorage.setItem(TRUSTED_IMAGE_SENDERS_KEY, JSON.stringify(Array.from(trusted).sort()));
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

function richContent(target: MessageTarget, showImages: boolean) {
  const key = `${target.key}|images=${showImages ? "1" : "0"}`;
  const existing = richContentRequests.get(key);
  if (existing) return existing;

  const request = (async (): Promise<RichMessageContent | null> => {
    try {
      const response = await webmail(
        `/messages/${target.uid}/content?folder=${encodeURIComponent(target.folder)}&show_images=${showImages ? "true" : "false"}`,
      );
      if (!response.ok) return null;
      const payload = (await response.json()) as RichMessageContent;
      return payload.has_html && payload.body_html?.trim() ? payload : null;
    } catch {
      return null;
    }
  })();

  richContentRequests.set(key, request);
  return request;
}

function visibleDomain(text: string) {
  const match = text.match(/(?:https?:\/\/)?(?:www\.)?([a-z0-9.-]+\.[a-z]{2,})(?:\/|\b)/i);
  return match?.[1]?.toLowerCase().replace(/^www\./, "") || "";
}

function linkRisk(anchor: HTMLAnchorElement) {
  const href = anchor.getAttribute("href") || "";
  if (!/^https?:/i.test(href)) return "";
  try {
    const url = new URL(href);
    const host = url.hostname.toLowerCase().replace(/^www\./, "");
    const shown = visibleDomain(anchor.textContent || "");
    if (url.protocol !== "https:") return `This link uses insecure HTTP and opens ${host}.`;
    if (url.username || url.password) return `This link contains embedded credentials and opens ${host}.`;
    if (host.startsWith("xn--") || host.includes(".xn--")) return `This link uses an internationalized/punycode domain: ${host}.`;
    if (/^\d{1,3}(?:\.\d{1,3}){3}$/.test(host)) return `This link goes directly to an IP address: ${host}.`;
    if (shown && shown !== host && !host.endsWith(`.${shown}`) && !shown.endsWith(`.${host}`)) {
      return `The visible link text mentions ${shown}, but the destination is ${host}.`;
    }
  } catch {
    return "This link has an invalid destination.";
  }
  return "";
}

function hardenRichContent(root: HTMLElement, showImages: boolean) {
  root.querySelectorAll("script, style, iframe, object, embed, form, svg, link, meta").forEach((node) => node.remove());

  root.querySelectorAll("img").forEach((node) => {
    if (!(node instanceof HTMLImageElement)) return;
    const src = node.getAttribute("src") || "";
    if (!showImages || !/^https?:\/\//i.test(src)) {
      node.remove();
      return;
    }
    node.loading = "lazy";
    node.decoding = "async";
    node.referrerPolicy = "no-referrer";
    node.classList.add("imail-remote-image");
  });

  root.querySelectorAll("a").forEach((node) => {
    if (!(node instanceof HTMLAnchorElement)) return;
    const href = node.getAttribute("href") || "";
    if (!/^(https?:|mailto:)/i.test(href)) {
      node.removeAttribute("href");
      return;
    }
    if (/^https?:/i.test(href)) {
      node.target = "_blank";
      node.rel = "noopener noreferrer nofollow";
      try {
        node.dataset.imailDestination = new URL(href).hostname;
      } catch {
        node.dataset.imailDestination = "";
      }
      const risk = linkRisk(node);
      if (risk) {
        node.dataset.imailLinkRisk = risk;
        node.classList.add("imail-suspicious-link");
        node.title = `Caution: ${risk}`;
        node.addEventListener("click", (event) => {
          if (!window.confirm(`Caution before opening this link:\n\n${risk}\n\nOpen it anyway?`)) {
            event.preventDefault();
            event.stopPropagation();
          }
        });
      } else if (node.dataset.imailDestination) {
        node.title = `Opens ${node.dataset.imailDestination}`;
      }
    }
    node.classList.add("imail-detected-link");
  });
}

function imageControls(
  container: HTMLElement,
  target: MessageTarget,
  payload: RichMessageContent,
  showImages: boolean,
) {
  const total = Number(payload.remote_images_total || payload.remote_images_blocked || 0);
  if (!total) return null;

  const domain = senderDomain(container);
  const trusted = Boolean(domain && trustedImageSenders().has(domain));
  const bar = document.createElement("div");
  bar.className = "imail-image-controls";

  const copy = document.createElement("span");
  copy.textContent = showImages
    ? `${total} remote image${total === 1 ? "" : "s"} shown. External servers may learn that you opened this message.`
    : `${total} remote image${total === 1 ? "" : "s"} blocked to protect your privacy.`;
  bar.append(copy);

  if (!showImages) {
    const show = document.createElement("button");
    show.type = "button";
    show.textContent = "Show images";
    show.addEventListener("click", async () => {
      const next = await richContent(target, true);
      if (next) renderRichContent(container, target, next, true);
    });
    bar.append(show);

    if (domain) {
      const always = document.createElement("button");
      always.type = "button";
      always.textContent = `Always show from ${domain}`;
      always.addEventListener("click", async () => {
        saveTrustedImageSender(domain);
        const next = await richContent(target, true);
        if (next) renderRichContent(container, target, next, true);
      });
      bar.append(always);
    }
  } else if (trusted && domain) {
    const stop = document.createElement("button");
    stop.type = "button";
    stop.textContent = "Stop auto-loading";
    stop.addEventListener("click", () => {
      removeTrustedImageSender(domain);
      void enhanceContainer(container, false, true);
    });
    bar.append(stop);
  }

  return bar;
}

function renderRichContent(
  container: HTMLElement,
  target: MessageTarget,
  payload: RichMessageContent,
  showImages: boolean,
) {
  if (!payload.body_html?.trim()) return;

  const shell = document.createElement("div");
  shell.dataset.imailRichShell = "true";
  const controls = imageControls(container, target, payload, showImages);
  if (controls) shell.append(controls);

  const root = document.createElement("div");
  root.dataset.imailRichRoot = "true";
  root.className = "imail-rich-message";
  root.innerHTML = payload.body_html;
  hardenRichContent(root, showImages);
  shell.append(root);

  container.replaceChildren(shell);
  container.dataset.imailContentKey = target.key;
  container.dataset.imailRichMail = "true";
  container.dataset.imailBlockedImages = String(payload.remote_images_blocked || 0);
  container.dataset.imailImagesShown = showImages ? "true" : "false";
}

async function enhanceContainer(container: HTMLElement, forceImages?: boolean, force = false) {
  const target = currentMessageTarget();
  if (!target) {
    renderStructuredText(container);
    return;
  }

  if (container.dataset.imailContentKey !== target.key) {
    container.dataset.imailContentKey = target.key;
    delete container.dataset.imailRichMail;
    delete container.dataset.imailBlockedImages;
    delete container.dataset.imailImagesShown;
  }

  if (!force && container.querySelector(":scope > [data-imail-rich-shell='true']")) return;

  renderStructuredText(container);

  const domain = senderDomain(container);
  const trusted = Boolean(domain && trustedImageSenders().has(domain));
  const showImages = forceImages ?? trusted;
  const requestKey = target.key;
  const payload = await richContent(target, showImages);
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

  renderRichContent(container, target, payload, showImages);
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
