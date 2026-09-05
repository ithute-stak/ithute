"use client";

import { useEffect } from "react";

const RETRY_MS = 3000;
const SIGNED_OUT_RETRY_MS = 10000;

function websocketUrl(lastEventId: string) {
  const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = new URL(`${scheme}//${window.location.host}/api/v1/webmail/events/ws`);
  if (lastEventId && lastEventId !== "$") url.searchParams.set("last_event_id", lastEventId);
  return url.toString();
}

async function hasActiveMailboxSession() {
  try {
    const response = await fetch("/api/v1/webmail/session", {
      method: "GET",
      credentials: "include",
      cache: "no-store",
    });
    return response.ok;
  } catch {
    return false;
  }
}

function refreshVisibleMailbox() {
  // Do not pull the user out of an open message. The pending refresh is
  // replayed after navigation returns to the message list.
  if (new URLSearchParams(window.location.search).has("message")) return false;
  const button = document.querySelector<HTMLButtonElement>('button[title="Refresh"]');
  if (!button) return false;
  button.click();
  window.dispatchEvent(new CustomEvent("ithute:mailbox-refreshed"));
  return true;
}

export function MailRealtime() {
  useEffect(() => {
    let socket: WebSocket | null = null;
    let events: EventSource | null = null;
    let retryTimer: number | null = null;
    let refreshTimer: number | null = null;
    let pendingRefresh = false;
    let stopped = false;
    let lastEventId = "$";

    const scheduleRetry = (callback: () => void, delay: number) => {
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      retryTimer = window.setTimeout(callback, delay);
    };

    const scheduleRefresh = () => {
      pendingRefresh = true;
      if (refreshTimer !== null) window.clearTimeout(refreshTimer);
      refreshTimer = window.setTimeout(() => {
        if (refreshVisibleMailbox()) pendingRefresh = false;
      }, 250);
    };

    const flushPending = () => {
      if (pendingRefresh && refreshVisibleMailbox()) pendingRefresh = false;
    };

    const handleEvent = (payload: unknown) => {
      if (!payload || typeof payload !== "object") return;
      const typed = payload as { id?: string; type?: string };
      if (typed.id) lastEventId = typed.id;
      if (typed.type === "mailbox.changed") scheduleRefresh();
    };

    const startSseFallback = () => {
      if (stopped || events) return;
      events = new EventSource("/api/v1/webmail/events/stream", { withCredentials: true });
      events.addEventListener("mailbox.changed", (event) => {
        const message = event as MessageEvent;
        if (message.lastEventId) lastEventId = message.lastEventId;
        try {
          handleEvent(JSON.parse(message.data));
        } catch {
          scheduleRefresh();
        }
      });
      events.onerror = () => {
        // EventSource reconnects automatically and keeps Last-Event-ID.
      };
    };

    const connectWebSocket = async () => {
      if (stopped || socket) return;
      if (!(await hasActiveMailboxSession())) {
        scheduleRetry(() => void connectWebSocket(), SIGNED_OUT_RETRY_MS);
        return;
      }
      if (stopped) return;

      try {
        socket = new WebSocket(websocketUrl(lastEventId));
      } catch {
        startSseFallback();
        scheduleRetry(() => void connectWebSocket(), RETRY_MS);
        return;
      }

      socket.onmessage = (event) => {
        try {
          handleEvent(JSON.parse(String(event.data)));
        } catch {
          // Ignore malformed control frames.
        }
      };
      socket.onopen = () => {
        if (events) {
          events.close();
          events = null;
        }
      };
      socket.onerror = () => {
        socket?.close();
      };
      socket.onclose = () => {
        socket = null;
        if (stopped) return;
        startSseFallback();
        scheduleRetry(() => void connectWebSocket(), RETRY_MS);
      };
    };

    window.addEventListener("popstate", flushPending);
    void connectWebSocket();

    return () => {
      stopped = true;
      window.removeEventListener("popstate", flushPending);
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      if (refreshTimer !== null) window.clearTimeout(refreshTimer);
      socket?.close(1000, "page closed");
      events?.close();
    };
  }, []);

  return null;
}
