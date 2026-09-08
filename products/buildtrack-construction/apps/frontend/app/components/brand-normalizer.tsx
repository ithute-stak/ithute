"use client";

import { useLayoutEffect } from "react";

const PRODUCT_NAME = "Nthane Brothers";

function replaceText(value: string | null): string | null {
  if (!value) return value;
  return value
    .replaceAll("BuildTrack Construction Operations", "Nthane Brothers Construction Management System")
    .replaceAll("BuildTrack", PRODUCT_NAME);
}

function normalizeNode(root: Node) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const textNodes: Text[] = [];
  while (walker.nextNode()) textNodes.push(walker.currentNode as Text);
  for (const node of textNodes) {
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
        for (const node of mutation.addedNodes) {
          if (node.nodeType === Node.TEXT_NODE) {
            const text = node as Text;
            const next = replaceText(text.nodeValue);
            if (next !== text.nodeValue) text.nodeValue = next;
            if (text.nodeValue?.trim() === "BT") text.nodeValue = "NB";
          } else if (node instanceof Element) {
            normalizeNode(node);
          }
        }
      }
    });
    observer.observe(document.body, { subtree: true, childList: true });
    return () => observer.disconnect();
  }, []);

  return <>{children}</>;
}
