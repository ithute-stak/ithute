"use client";

import { useLayoutEffect } from "react";

function replaceText(value: string | null): string | null {
  if (!value) return value;
  return value
    .replaceAll("BuildTrack Construction Operations", "Nthane Brothers Construction Management System")
    .replaceAll("BuildTrack", "Nthane Brothers");
}

function normalizeNode(root: Node) {
  if (root.nodeType === Node.TEXT_NODE) {
    const text = root as Text;
    const next = replaceText(text.nodeValue);
    if (next !== text.nodeValue) text.nodeValue = next;
    if (text.nodeValue?.trim() === "BT") text.nodeValue = "NB";
    return;
  }

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);
  for (const node of nodes) {
    const next = replaceText(node.nodeValue);
    if (next !== node.nodeValue) node.nodeValue = next;
    if (node.nodeValue?.trim() === "BT") node.nodeValue = "NB";
  }
  if (root instanceof Element) {
    for (const attribute of ["aria-label", "title", "placeholder"]) {
      const current = root.getAttribute(attribute);
      const next = replaceText(current);
      if (next !== current && next !== null) root.setAttribute(attribute, next);
    }
  }
  const parent = root as Node & ParentNode;
  if (typeof parent.querySelectorAll === "function") {
    parent.querySelectorAll("[aria-label], [title], [placeholder]").forEach((element) => {
      for (const attribute of ["aria-label", "title", "placeholder"]) {
        const current = element.getAttribute(attribute);
        const next = replaceText(current);
        if (next !== current && next !== null) element.setAttribute(attribute, next);
      }
    });
  }
}

export function BrandNormalizer({ children }: { children: React.ReactNode }) {
  useLayoutEffect(() => {
    normalizeNode(document.body);
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) normalizeNode(node);
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);
  return <>{children}</>;
}
