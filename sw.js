self.addEventListener('push', e => {
  let d = { title: 'MSNR', body: 'signal' };
  try { d = e.data.json(); } catch (err) { if (e.data) d.body = e.data.text(); }
  e.waitUntil(self.registration.showNotification(d.title || 'MSNR', {
    body: d.body || '', tag: 'msnr', renotify: true, icon: 'icon.png'
  }));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(clients.openWindow('./index.html'));
});
