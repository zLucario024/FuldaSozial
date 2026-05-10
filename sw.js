const SHELL_CACHE = 'shell-v1';
const SHELL_ASSETS = ['/', '/index.html', '/fonts/playfair-display-700.woff2', '/fonts/playfair-display-900.woff2', '/fonts/source-sans-3-400.woff2', '/fonts/source-sans-3-500.woff2', '/fonts/source-sans-3-600.woff2', '/Design/rn_logo_mini.jpg'];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(SHELL_CACHE).then(c => c.addAll(SHELL_ASSETS)));
  self.skipWaiting();
});

self.addEventListener('activate', event => event.waitUntil(clients.claim()));

self.addEventListener('fetch', event => {
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).catch(() => caches.match('/index.html')));
  }
});

self.addEventListener('push', event => {
  if (!event.data) return;
  const d = event.data.json();
  event.waitUntil(
    self.registration.showNotification(d.title, {
      body: d.body,
      icon: d.icon,
      badge: 'https://www.rnfulda.de/Design/rn_logo_mini.jpg',
      tag: d.tag,       // same tag replaces older notification for the same article
      renotify: true,
      data: { url: d.url }
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      for (const client of list) {
        if (client.url === event.notification.data.url && 'focus' in client)
          return client.focus();
      }
      return clients.openWindow(event.notification.data.url);
    })
  );
});
