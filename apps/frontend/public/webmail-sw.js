const CACHE = "ithute-imail-shell-v1";
const SHELL = ["/webmail", "/webmail/unified", "/webmail/accounts", "/webmail/productivity", "/webmail/migrate"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).catch(() => undefined));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key.startsWith("ithute-imail-") && key !== CACHE).map((key) => caches.delete(key)))));
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  // Never persist API responses, messages, attachments, auth data or mailbox
  // pages containing user mail in the service-worker cache.
  if (url.pathname.startsWith("/api/") || url.pathname.includes("/attachments/")) return;
  if (request.destination === "script" || request.destination === "style" || request.destination === "font" || request.destination === "image") {
    event.respondWith(caches.match(request).then((cached) => cached || fetch(request).then((response) => {
      if (response.ok) caches.open(CACHE).then((cache) => cache.put(request, response.clone())).catch(() => undefined);
      return response;
    })));
  }
});

self.addEventListener("message", (event) => {
  if (!event.data || event.data.type !== "IMAIL_NOTIFICATION") return;
  const title = String(event.data.title || "New iMail activity").slice(0, 120);
  const body = String(event.data.body || "Your mailbox has new activity.").slice(0, 240);
  event.waitUntil(self.registration.showNotification(title, { body, tag: "ithute-imail", renotify: true, data: { url: "/webmail/unified" } }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = event.notification.data?.url || "/webmail/unified";
  event.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
    const existing = windows.find((client) => "focus" in client);
    if (existing) { existing.navigate(target); return existing.focus(); }
    return clients.openWindow(target);
  }));
});
