/* Service worker của Bác sĩ cây trồng (Vite chép sang dist/sw.js, Flask phục vụ ở /sw.js).
 * - Mất mạng vẫn mở được app: giao diện (index.html + JS/CSS) và dữ liệu đã xem gần đây (lịch sử, kết quả, nhật ký, thư viện...)
 *   lấy từ bộ nhớ đệm; có mạng thì luôn lấy bản mới trước (network-first).
 * - Nhận thông báo đẩy (Web Push) và mở đúng trang khi bấm vào thông báo.
 * Đăng xuất thì xóa dữ liệu cá nhân đã lưu (máy dùng chung). Đổi VERSION khi đổi cách lưu để xóa bộ đệm cũ. */
const VERSION = "v1";
const SHELL = `shell-${VERSION}`, STATIC = `static-${VERSION}`, DATA = `data-${VERSION}`;
const SHELL_KEY = "/__app-shell";
const DATA_API = /^\/api\/(me|plants|library|history|diagnoses\/\d+(\/report)?|notifications|treatments(\/\d+)?|agenda|reminders|care-plan|weather|map)$/;
const OFFLINE = JSON.stringify({ error: "Bạn đang ngoại tuyến và dữ liệu này chưa được lưu trên máy. Hãy thử lại khi có mạng." });

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(STATIC).then((c) => c.addAll(["/client/static/manifest.json", "/static/img/app-icon-192.png", "/static/img/logo-96.png"]))
    .catch(() => {}).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => ![SHELL, STATIC, DATA].includes(k)).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request, url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (req.method !== "GET") {
    if (url.pathname === "/api/logout") e.waitUntil(caches.delete(DATA));  // không để lại dữ liệu cá nhân trên máy
    return;
  }
  if (req.mode === "navigate") {
    if (/^\/(admin|api|uploads)\b/.test(url.pathname)) return;
    e.respondWith(fetch(req).then((res) => {
      if (res.ok && (res.headers.get("content-type") || "").includes("text/html")) {
        const copy = res.clone();
        caches.open(SHELL).then((c) => c.put(SHELL_KEY, copy));
      }
      return res;
    }).catch(() => caches.match(SHELL_KEY).then((hit) => hit || new Response("<h1>Bạn đang ngoại tuyến</h1>", { headers: { "content-type": "text/html; charset=utf-8" } }))));
    return;
  }
  if (url.pathname.startsWith("/assets/") || url.pathname.startsWith("/static/")) {  // tên file có mã băm / ít đổi: lấy bộ đệm trước
    e.respondWith(caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      if (res.ok) { const copy = res.clone(); caches.open(STATIC).then((c) => c.put(req, copy)); }
      return res;
    })));
    return;
  }
  if (DATA_API.test(url.pathname) || url.pathname.startsWith("/uploads/") || url.pathname === "/api/library/image") {
    e.respondWith(fetch(req).then((res) => {
      if (res.ok) { const copy = res.clone(); caches.open(DATA).then((c) => c.put(req, copy)); }
      return res;
    }).catch(() => caches.match(req).then((hit) => hit || new Response(OFFLINE, { status: 503, headers: { "content-type": "application/json; charset=utf-8" } }))));
  }
});

self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = { body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.title || "Bác sĩ cây trồng", {
    body: d.body || "", icon: "/static/img/app-icon-192.png", badge: "/static/img/favicon-32.png", lang: "vi", data: { url: d.url || "/notifications" },
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  let target = new URL((e.notification.data && e.notification.data.url) || "/notifications", self.location.origin);
  if (target.origin !== self.location.origin) target = new URL("/notifications", self.location.origin);
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    const win = list.find((c) => c.url.startsWith(self.location.origin) && !c.url.includes("/admin"));
    if (win) return win.navigate(target.href).then((w) => (w || win).focus());
    return self.clients.openWindow(target.href);
  }));
});
