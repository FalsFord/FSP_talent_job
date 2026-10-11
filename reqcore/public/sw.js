// This service worker immediately unregisters itself.
// It exists only to clear stale registrations from localhost.
self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', () => {
  self.registration.unregister()
})
