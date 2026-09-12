"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

const PREFIX = "ithute:navigation:";

export function NavigationMemory() {
  const pathname = usePathname();

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
