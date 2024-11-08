const CACHE_NAME = 'my-cache-v2';
const urlsToCache = [
    '/',
    '/static/css/styles.css',
    '/static/js/script.js',
    '/static/images/icon-192x192.png',
    '/offline.html'  // Fallback page when offline
];

// Install event - Cache essential resources
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('Caching initial files:', urlsToCache);
                return cache.addAll(urlsToCache)
                    .catch((error) => console.error('Failed to cache files on install:', error));
            })
    );
    self.skipWaiting();  // Immediately activate this service worker
});

// Fetch event - Network-first for API calls, Cache-first for others with offline fallback
self.addEventListener('fetch', (event) => {
    if (event.request.url.includes('/api/')) {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    return caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, response.clone());
                        return response;
                    });
                })
                .catch(() => caches.match(event.request) || new Response('{"error": "Network error"}', {
                    headers: { 'Content-Type': 'application/json' }
                }))
        );
    } else {
        event.respondWith(
            caches.match(event.request)
                .then((response) => {
                    return response || fetch(event.request)
                        .then((networkResponse) => {
                            // Cache the dynamically fetched resource if not an API request
                            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, networkResponse.clone()));
                            return networkResponse;
                        });
                })
                .catch(() => caches.match('/offline.html'))  // Show offline page for failed requests
        );
    }
});

// Activate event - Clear old caches and claim clients immediately
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    return self.clients.claim();
});

// Listen for skip waiting message from the client
self.addEventListener('message', (event) => {
    if (event.data.action === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});

// Notify the client of updates and request a reload
self.addEventListener('controllerchange', () => {
    self.clients.matchAll().then(clients => {
        clients.forEach(client => client.postMessage({ action: 'NEW_VERSION_AVAILABLE' }));
    });
});
