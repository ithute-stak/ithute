"use client";

import { useEffect } from "react";
import { API } from "./mail-types";

const INTERVAL_MS = 90_000;

async function runRules() {
  try {
    await fetch(`${API}/webmail/rules/run`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
  } catch {
    // Rules are a best-effort productivity layer. Mail reading/sending must
    // remain available if a provider is temporarily unreachable.
  }
}

export function WebmailAutomationRunner() {
  useEffect(() => {
    let stopped = false;
    let timer: number | null = null;

    const schedule = () => {
      if (stopped) return;
      timer = window.setTimeout(async () => {
        if (!document.hidden) await runRules();
        schedule();
      }, INTERVAL_MS);
    };

    const onRefresh = () => { if (!document.hidden) void runRules(); };
    const onVisible = () => { if (!document.hidden) void runRules(); };

    window.addEventListener("ithute:mailbox-refreshed", onRefresh);
    document.addEventListener("visibilitychange", onVisible);
    void runRules();
    schedule();

    return () => {
      stopped = true;
      if (timer !== null) window.clearTimeout(timer);
      window.removeEventListener("ithute:mailbox-refreshed", onRefresh);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  return null;
}
