const CACHE = "haus-v14";
const SHELL = ["/", "/static/style.css?v=13", "/static/app.js?v=13", "/manifest.json", "/static/placeholder.jpg"];

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
