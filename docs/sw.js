// Offline copy of the app. tools/release.cjs bumps VERSION and refreshes FILES on every release,
// which is what makes phones notice a new version.
const VERSION = 'wardrobe-v1.0.4';
// FILES-START
const FILES = ["./","data/items.json","data/wishlist.json","icon-192.png","icon-512.png","index.html","manifest.webmanifest"];
// FILES-END

self.addEventListener('install', (e) => {
  // cache:'reload' skips the browser cache, otherwise GitHub Pages can hand back the old files
  e.waitUntil(caches.open(VERSION).then((c) => Promise.all(FILES.map((f) =>
    fetch(new Request(f, { cache: 'reload' })).then((r) => r.ok && c.put(f, r)).catch(() => {})))));
  // no skipWaiting here: the app shows "Update available" and the user decides when
});

self.addEventListener('message', (e) => { if (e.data === 'skipWaiting') self.skipWaiting(); });

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin) return;
  if (u.pathname.endsWith('/version.json')) return;            // always ask the server
  if (u.pathname.includes('/img/')) {                          // photos never change once imported
    e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request).then((res) => {
      const c = res.clone(); caches.open(VERSION).then((k) => k.put(e.request, c)); return res;
    })));
    return;
  }
  // everything else: this version's saved copy, so the app opens offline and only changes
  // when the user taps Update (falls back to the network for anything not saved yet)
  e.respondWith(caches.match(e.request, { ignoreSearch: true }).then((r) => r || fetch(e.request)));
});
