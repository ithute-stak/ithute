"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

const PREFIX = "ithute:navigation:";
const SIDEBAR_KEY = "ithute:sidebar:collapsed";

export function NavigationMemory() {
  const pathname = usePathname();

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.localStorage.getItem(SIDEBAR_KEY) === null) {
      const lowResolutionDesktop =
        window.innerWidth >= 1024 &&
        (window.innerWidth <= 1366 || window.innerHeight <= 800);
      window.localStorage.setItem(SIDEBAR_KEY, String(lowResolutionDesktop));
    }
  }, []);

  useEffect(() => {
    if (!pathname || typeof window === "undefined") return;
    const key = `${PREFIX}${pathname}`;
    const saved = Number(sessionStorage.getItem(key) || "0");
    const frame = window.requestAnimationFrame(() => {
      if (saved > 0) window.scrollTo({ top: saved, behavior: "auto" });
    });

    sessionStorage.setItem(`${PREFIX}last-route`, pathname);
    const persist = () => sessionStorage.setItem(key, String(window.scrollY));
    window.addEventListener("pagehide", persist);
    window.addEventListener("beforeunload", persist);
    return () => {
      window.cancelAnimationFrame(frame);
      persist();
      window.removeEventListener("pagehide", persist);
      window.removeEventListener("beforeunload", persist);
    };
  }, [pathname]);

  return null;
}
