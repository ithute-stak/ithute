"use client";

import { useEffect, useLayoutEffect, useState } from "react";

import { useMailPreferences } from "./mail-preferences";

export function MailThemeBridge() {
  const { preferences, ready } = useMailPreferences();
  const [systemDark, setSystemDark] = useState(false);

  useEffect(() => {
    const query = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!query) return;
    const sync = () => setSystemDark(query.matches);
    sync();
    query.addEventListener?.("change", sync);
    return () => query.removeEventListener?.("change", sync);
  }, []);

  const resolved = preferences.theme === "system" ? (systemDark ? "dark" : "light") : preferences.theme;

  useLayoutEffect(() => {
    if (!ready) return;
    const root = document.documentElement;
    root.dataset.imailTheme = resolved;
    root.dataset.imailThemePreference = preferences.theme;
    root.classList.toggle("dark", resolved === "dark");
    root.style.colorScheme = resolved === "dark" ? "dark" : "light";
  }, [preferences.theme, ready, resolved]);

  return null;
}
