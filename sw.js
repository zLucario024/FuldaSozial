self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(clients.claim()));

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
