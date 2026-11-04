// Lets an already visited notebook page reopen without a network. Ink data never passes through
// this cache: the API is left alone, and the journal lives in IndexedDB.

const CACHE = "tutor-shell-v2";
const SHELL = [
  "/static/css/notebook.css",
  "/static/js/grading/verify.js",
  "/static/js/ink/capture.js",
  "/static/js/ink/core.js",
  "/static/js/ink/notebook.js",
  "/static/js/ink/render.js",
  "/static/js/ink/sha256.js",
  "/static/js/ink/store.js",
  "/static/js/ink/sync.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const isShell = url.pathname.startsWith("/static/") || url.pathname.startsWith("/notebook/");
  if (event.request.method !== "GET" || url.origin !== self.location.origin || !isShell) return;
  // Network first, so that a deployed fix is never hidden behind a stale copy.
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(async () => {
        const cached = await caches.match(event.request);
        return cached ?? Response.error();
      }),
  );
});
