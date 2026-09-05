"use client";

import { useEffect } from "react";

const TECHNICAL_NAME = /(domain|hostname|host|email|address|username|local_part|selector|record|token|scope|ip|url)/i;
const NUMERIC_NAME = /(port|quota|limit|days|years|priority|weight|ttl|amount|price|quantity|count)/i;
const EMAIL_NAME = /(^|_)(email|sender_email|recipient_email|support_email|destination_address|source_address)($|_)/i;
const CONTROL_SELECTOR = "form input, form select, form textarea, .mailbox-admin-shell input, .mailbox-admin-shell select, .mailbox-admin-shell textarea, .lelefa-admin-shell input, .lelefa-admin-shell select, .lelefa-admin-shell textarea";
let nextControlId = 0;

function readableName(value: string) {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
    .trim();
}

function isControl(node: Element): node is HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement {
  return node instanceof HTMLInputElement || node instanceof HTMLSelectElement || node instanceof HTMLTextAreaElement;
}

function enhanceControl(control: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement) {
  if (control.dataset.formEnhanced === "true") return;
  control.dataset.formEnhanced = "true";

  const name = control.getAttribute("name") || "";
  const placeholder = control.getAttribute("placeholder") || "";
  if (!control.id) {
    nextControlId += 1;
    control.id = `mailbox-form-${name || control.tagName.toLowerCase()}-${nextControlId}`;
  }

  const hasAccessibleName = Boolean(
    control.getAttribute("aria-label") ||
      control.getAttribute("aria-labelledby") ||
      document.querySelector(`label[for="${CSS.escape(control.id)}"]`) ||
      control.closest("label"),
  );
  if (!hasAccessibleName) {
    const fallback = placeholder || (name ? readableName(name) : control.tagName.toLowerCase());
    control.setAttribute("aria-label", fallback);
  }

  if (control instanceof HTMLInputElement) {
    const type = (control.type || "text").toLowerCase();
    const isEmail = type === "email" || EMAIL_NAME.test(name);
    const isUsername = /(^|_)username($|_)/i.test(name);
    const isPhone = type === "tel" || /(^|_)(phone|telephone|mobile)($|_)/i.test(name);
    const isUrl = type === "url" || /(^|_)(url|hostname|domain|host)($|_)/i.test(name);

    if (!control.hasAttribute("autocomplete")) {
      if (isEmail) control.autocomplete = "email";
      else if (type === "password") control.autocomplete = /current|login/i.test(name) ? "current-password" : "new-password";
      else if (isUsername) control.autocomplete = "username";
      else if (isPhone) control.autocomplete = "tel";
      else control.autocomplete = "off";
    }

    if (!control.hasAttribute("inputmode")) {
      if (isEmail) control.inputMode = "email";
      else if (isPhone) control.inputMode = "tel";
      else if (isUrl) control.inputMode = "url";
      else if (type === "number" || NUMERIC_NAME.test(name)) control.inputMode = "numeric";
    }

    if (TECHNICAL_NAME.test(name) || type === "email" || type === "url") {
      control.spellcheck = false;
      control.autocapitalize = "none";
    }
  }

  if (control instanceof HTMLTextAreaElement && TECHNICAL_NAME.test(name)) {
    control.spellcheck = false;
    control.autocapitalize = "none";
  }

  const syncValidity = () => {
    if (!control.validity.valid) control.setAttribute("aria-invalid", "true");
    else control.removeAttribute("aria-invalid");
  };
  control.addEventListener("invalid", syncValidity);
  control.addEventListener("input", syncValidity);
  control.addEventListener("change", syncValidity);
}

function enhance(root: ParentNode) {
  if (root instanceof Element && isControl(root) && root.matches(CONTROL_SELECTOR)) enhanceControl(root);
  root.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(CONTROL_SELECTOR).forEach(enhanceControl);
}

export function FormEnhancer() {
  useEffect(() => {
    enhance(document);
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (node instanceof Element) enhance(node);
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  return null;
}
