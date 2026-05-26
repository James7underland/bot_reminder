// Phase 12.0: минимальный service worker для PWA-режима.
// - Кеширует «оболочку» (index.html / manifest / icon) для запуска
//   без сети.
// - НЕ кеширует /api/* и /healthz — там всегда нужны свежие данные.
// - Стратегия: network-first (с фоновой записью в кеш); если сети
//   нет — отдаём из кеша.

const CACHE = "reminderr-shell-v1";
const CORE = [
  "/",
  "/manifest.webmanifest",
  "/icon.svg",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(CORE))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  // API и healthz всегда из сети, без кеша.
  if (url.pathname.startsWith("/api/") || url.pathname === "/healthz") {
    return;
  }
  // Внешние ресурсы (telegram.org/js/...) — пропускаем.
  if (url.origin !== self.location.origin) return;

  e.respondWith(
    fetch(req)
      .then((resp) => {
        if (resp.ok) {
          const clone = resp.clone();
          caches.open(CACHE).then((c) => c.put(req, clone)).catch(() => {});
        }
        return resp;
      })
      .catch(() => caches.match(req).then((m) => m || caches.match("/")))
  );
});
