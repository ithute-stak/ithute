"use client";

import { apiJson, invalidateApiCache } from "@/lib/platform-api";
import { useToast } from "@/components/toast-provider";
import { useEffect, useRef } from "react";

type NotificationItem = {
  id: string;
  title: string;
  message: string;
  severity?: string;
  read_at?: string | null;
  action_url?: string | null;
};

type NotificationResponse = { items?: NotificationItem[] };

const TENANT_KEY = "mailbox_dns_tenant";
const POLL_MS = 30_000;

export function BackgroundRefresh() {
  const toast = useToast();
  const seen = useRef<Set<string>>(new Set());
  const initialized = useRef(false);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      if (cancelled || document.visibilityState !== "visible") return;
      const tenantId = window.localStorage.getItem(TENANT_KEY);
      if (!tenantId) return;

      try {
        const path = `/tenants/${tenantId}/notifications`;
        invalidateApiCache(path);
        const data = await apiJson<NotificationResponse>(path, { force: true, ttlMs: 10_000 });
        const unread = (data.items || []).filter((item) => !item.read_at);
        const unreadIds = new Set(unread.map((item) => item.id));

        if (initialized.current) {
          const fresh = unread.filter((item) => !seen.current.has(item.id));
          for (const item of fresh.slice(0, 2)) {
            const tone = item.severity === "error" ? "error" : item.severity === "warning" ? "warning" : item.severity === "success" ? "success" : "info";
            toast.notify({
              tone,
              title: item.title,
              message: item.message,
              duration: 6500,
              action: item.action_url ? { label: "Open", onClick: () => { window.location.href = item.action_url!; } } : undefined,
            });
          }
        }

        seen.current = unreadIds;
        initialized.current = true;
        window.dispatchEvent(new CustomEvent("ithute:notifications-updated", { detail: { unread: unread.length } }));
      } catch {
        // Background refresh must never interrupt the active task. Page-level requests surface actionable errors.
      }
    }

    void check();
    const timer = window.setInterval(() => void check(), POLL_MS);
    const onVisible = () => { if (document.visibilityState === "visible") void check(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [toast]);

  return null;
}
