const CACHE = "haus-v25";
const SHELL = ["/", "/static/style.css?v=25", "/static/app.js?v=25", "/manifest.json", "/static/placeholder.jpg"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);

  // Never cache the live image or API calls
  if (url.pathname === "/image" || url.pathname.startsWith("/api/") || url.pathname === "/ws") {
    e.respondWith(fetch(e.request));
    return;
  }

  // Network-first for the app shell so updates land on next open.
  // `cache: "no-store"` forces a real network hit, bypassing the browser
  // HTTP cache — which would otherwise serve stale assets even when the
  // SW thinks it's fetching fresh.
  e.respondWith(
    fetch(e.request, { cache: "no-store" })
      .then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});

// ── Web Push ──────────────────────────────────────────────────────────────
// Payload comes from app/push.py: { title, body, tag, url }
self.addEventListener("push", e => {
  let d = {};
  try {
    d = e.data ? e.data.json() : {};
  } catch (_) {
    d = { body: e.data ? e.data.text() : "" };
  }
  e.waitUntil(self.registration.showNotification(d.title || "Haus", {
    body: d.body || "",
    tag: d.tag || "haus",
    renotify: true,
    icon: "/static/icon-192.png",
    badge: "/static/icon-192.png",
    data: { url: d.url || "/" },
  }));
});

self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then(list => {
      for (const c of list) {
        if ("focus" in c) return c.focus();
      }
      return clients.openWindow(url);
    })
  );
});
