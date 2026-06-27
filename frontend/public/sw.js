const CACHE_VERSION = "aira-pwa-v1";
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;
const OFFLINE_URL = "/offline";

const PRECACHE_URLS = [
  OFFLINE_URL,
  "/favicon.ico",
  "/icons/aira-icon-192.png",
  "/icons/aira-icon-512.png",
  "/icons/aira-maskable-512.png",
];

const isHttpRequest = (request) => {
  try {
    const url = new URL(request.url);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
};

const isSameOrigin = (request) => {
  const url = new URL(request.url);
  return url.origin === self.location.origin;
};

const shouldHandleRequest = (request) => {
  if (request.method !== "GET" || !isHttpRequest(request) || !isSameOrigin(request)) {
    return false;
  }

  const { pathname } = new URL(request.url);
  return !pathname.startsWith("/api/") && !pathname.startsWith("/auth/");
};

const isStaticAsset = (request) => {
  const url = new URL(request.url);
  return (
    url.pathname.startsWith("/_next/static/") ||
    request.destination === "font" ||
    request.destination === "image" ||
    request.destination === "script" ||
    request.destination === "style"
  );
};

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((cacheNames) =>
        Promise.all(
          cacheNames
            .filter((cacheName) => cacheName !== STATIC_CACHE && cacheName !== RUNTIME_CACHE)
            .map((cacheName) => caches.delete(cacheName))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  if (!shouldHandleRequest(request)) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(async () => {
        const cache = await caches.open(STATIC_CACHE);
        return cache.match(OFFLINE_URL);
      })
    );
    return;
  }

  if (isStaticAsset(request)) {
    event.respondWith(
      caches.match(request).then((cachedResponse) => {
        const networkResponse = fetch(request).then((response) => {
          if (response.ok) {
            const responseClone = response.clone();
            caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, responseClone));
          }

          return response;
        });

        return cachedResponse || networkResponse;
      })
    );
  }
});

self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch {
    payload = { title: "Aira", body: event.data ? event.data.text() : "New update" };
  }

  const title = payload.title || "Aira";
  const options = {
    body: payload.body || "You have a new update.",
    icon: "/icons/aira-icon-192.png",
    badge: "/icons/aira-icon-192.png",
    tag: payload.tag || "aira-update",
    data: {
      url: payload.url || "/dashboard",
      ...(payload.data || {}),
    },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = new URL(event.notification.data?.url || "/dashboard", self.location.origin).href;

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ("focus" in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      return self.clients.openWindow(targetUrl);
    })
  );
});
