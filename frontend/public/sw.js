/* Service worker for the installable app. Deliberately small and conservative:
 *  - /api/* is NEVER handled here: login, KYC uploads, payments, voice transcription and quotes always go straight to the
 *    network (nothing personal or financial is ever cached, and a stale price can never be shown).
 *  - Pages (navigations) are network-first; if the phone is offline the friendly /offline.html is shown instead of a browser error.
 *  - Hashed build assets (/_next/static/*) and the icons are cached after first use, so repeat opens are fast.
 * Bump VERSION to invalidate every cache. */
const VERSION = "v1";
const STATIC = `udyam-static-${VERSION}`;
const SHELL = `udyam-shell-${VERSION}`;
const PRECACHE = ["/offline.html", "/icons/icon-192.png", "/icons/icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => ![STATIC, SHELL].includes(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;          // never intercept the API

  if (req.mode === "navigate") {
    event.respondWith(fetch(req).catch(() => caches.match("/offline.html")));
    return;
  }

  if (url.pathname.startsWith("/_next/static/") || url.pathname.startsWith("/icons/")) {
    event.respondWith(
      caches.match(req).then((hit) => hit || fetch(req).then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(STATIC).then((c) => c.put(req, copy)); }
        return res;
      })),
    );
  }
});
