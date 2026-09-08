"use client";

import { useEffect } from "react";

export function MailBrowserNotifications() {
  useEffect(() => {
    const notify = () => {
      if (!document.hidden || !("Notification" in window) || Notification.permission !== "granted") return;
      if ("serviceWorker" in navigator) {
        void navigator.serviceWorker.ready.then((registration) => {
          registration.active?.postMessage({ type: "IMAIL_NOTIFICATION", title: "New iMail activity", body: "Your mailbox has new activity. Open iMail to review it." });
        }).catch(() => undefined);
      }
    };
    window.addEventListener("ithute:mailbox-refreshed", notify);
    return () => window.removeEventListener("ithute:mailbox-refreshed", notify);
  }, []);
  return null;
}
