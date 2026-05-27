// Phase 12.0: минимальный service worker для PWA-режима.
// Phase 13.1: + обработка `push`/`notificationclick` для фоновых
// app/alarm уведомлений.
// - Кеширует «оболочку» (index.html / manifest / icons) для запуска
//   без сети.
// - НЕ кеширует /api/* и /healthz — там всегда нужны свежие данные.
// - Стратегия: network-first (с фоновой записью в кеш); если сети
//   нет — отдаём из кеша.

// Bump version при изменении манифеста или статики, чтобы старый SW
// сбросил кеш у пользователей.
const CACHE = "reminderr-shell-v3";
const CORE = [
  "/",
  "/manifest.webmanifest",
  "/icon.svg",
  "/icon-192.png",
  "/icon-512.png",
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

// --- Phase 13.1: Web Push (фоновая доставка app/alarm) ---

self.addEventListener("push", (e) => {
  let data = {title: "Напоминалка", body: "Уведомление", channel: "app"};
  try {
    if (e.data) data = Object.assign(data, e.data.json());
  } catch (_) {
    if (e.data) data.body = e.data.text();
  }
  const isAlarm = data.channel === "alarm";
  // Опции системного notification.
  const opts = {
    body: data.body || "",
    icon: "/icon-192.png",
    badge: "/icon-192.png",
    // alarm — не пропадает само + сильная вибрация.
    requireInteraction: isAlarm,
    vibrate: isAlarm ? [400, 200, 400, 200, 400, 200, 400] : [200, 100, 200],
    tag: data.task_id ? "task-" + data.task_id : undefined,
    renotify: true,
    data: {task_id: data.task_id || null, channel: data.channel || "app"},
  };
  e.waitUntil(self.registration.showNotification(data.title || "Напоминалка", opts));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  // По клику открываем/фокусируем уже открытую вкладку.
  e.waitUntil((async () => {
    const allClients = await self.clients.matchAll({
      type: "window", includeUncontrolled: true,
    });
    for (const c of allClients) {
      if ("focus" in c) return c.focus();
    }
    if (self.clients.openWindow) return self.clients.openWindow("/");
  })());
});
