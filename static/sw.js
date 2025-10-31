self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open('royal-casino-v1').then((cache) => cache.addAll([
      '/',
      '/static/manifest.json'
    ]))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request).then((resp) => {
      return resp || fetch(event.request);
    })
  );
});
