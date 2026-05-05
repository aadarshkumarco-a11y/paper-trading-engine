/**
 * Minimal service worker for the NSE Paper Trading PWA.
 *
 * We intentionally do NOT cache the live trading view — paper trading still
 * needs fresh prices. This SW only caches the static app shell (manifest,
 * icons) and falls through to network for everything else.
 */
const CACHE_NAME = "nse-paper-trader-v1";
const SHELL_ASSETS = [
  "./manifest.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const isShell = SHELL_ASSETS.some((path) => url.pathname.endsWith(path.replace("./", "/")));
  if (isShell) {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request))
    );
    return;
  }
  // Everything else goes to the network — trading data must be fresh.
});
