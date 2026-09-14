"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

const IDS_ICON = "/brand/ids-mark.svg?v=ids-20260914";
const HOME_TITLE = "Ithute Digital Solutions · Digital systems built for real operations";

function applyIdsBrowserBrand(pathname: string) {
  if (pathname === "/") {
    document.title = HOME_TITLE;
  }

  document
    .querySelectorAll<HTMLLinkElement>('link[rel="icon"], link[rel="shortcut icon"], link[rel="apple-touch-icon"]')
    .forEach((link) => link.remove());

  const icon = document.createElement("link");
  icon.id = "ids-browser-icon";
  icon.rel = "icon";
  icon.type = "image/svg+xml";
  icon.href = IDS_ICON;
  document.head.appendChild(icon);

  const shortcut = document.createElement("link");
  shortcut.id = "ids-browser-shortcut";
  shortcut.rel = "shortcut icon";
  shortcut.href = IDS_ICON;
  document.head.appendChild(shortcut);

  const apple = document.createElement("link");
  apple.id = "ids-browser-apple-icon";
  apple.rel = "apple-touch-icon";
  apple.href = IDS_ICON;
  document.head.appendChild(apple);
}

export function BrowserBrandSync() {
  const pathname = usePathname();

  useEffect(() => {
    applyIdsBrowserBrand(pathname);

    const observer = new MutationObserver(() => {
      const legacyIcon = Array.from(
        document.querySelectorAll<HTMLLinkElement>('link[rel="icon"], link[rel="shortcut icon"], link[rel="apple-touch-icon"]'),
      ).some((link) => link.href.startsWith("data:image/svg+xml") || !link.href.includes("ids-mark.svg"));

      if (legacyIcon || !document.getElementById("ids-browser-icon")) {
        observer.disconnect();
        applyIdsBrowserBrand(pathname);
        observer.observe(document.head, { childList: true, subtree: true });
      }
    });

    observer.observe(document.head, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [pathname]);

  return null;
}
