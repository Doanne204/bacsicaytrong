// Ứng dụng cài được (PWA): đăng ký service worker (/sw.js), nút "Cài lên màn hình chính", thông báo đẩy (Web Push).
import { api, send } from "./api";

type InstallEvent = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };
let installEvent: InstallEvent | null = null;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((f) => f());

/** Gọi một lần khi mở app: đăng ký service worker (chỉ bản build; trình duyệt chỉ cho phép trên HTTPS hoặc localhost). */
export function registerSW() {
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); installEvent = e as InstallEvent; emit(); });
  window.addEventListener("appinstalled", () => { installEvent = null; emit(); });
  if (!import.meta.env.PROD || !("serviceWorker" in navigator) || !window.isSecureContext) return;
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").then(() => resyncPush()).catch((e) => console.warn("[pwa] không đăng ký được service worker", e));
  });
}

export const onInstallChange = (f: () => void) => { listeners.add(f); return () => { listeners.delete(f); }; };
export const canInstall = () => !!installEvent;
export async function install() {
  if (!installEvent) return false;
  await installEvent.prompt();
  const { outcome } = await installEvent.userChoice;
  installEvent = null; emit();
  return outcome === "accepted";
}
export const isStandalone = () => window.matchMedia("(display-mode: standalone)").matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;

// ---------- Thông báo đẩy ----------
export const pushSupported = () => window.isSecureContext && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

async function registration() {
  return navigator.serviceWorker.getRegistration("/") || navigator.serviceWorker.ready;
}

export async function currentSub(): Promise<PushSubscription | null> {
  if (!pushSupported()) return null;
  const reg = await registration();
  return reg ? reg.pushManager.getSubscription() : null;
}

function keyBytes(b64: string) {
  const s = atob((b64 + "=".repeat((4 - (b64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
}

/** Xin quyền và đăng ký nhận thông báo cho thiết bị này (gắn với tài khoản đang đăng nhập). */
export async function enablePush() {
  if (!pushSupported()) throw new Error("Trình duyệt này chưa hỗ trợ thông báo đẩy, hoặc trang chưa chạy qua HTTPS.");
  const perm = await Notification.requestPermission();
  if (perm !== "granted") throw new Error("Bạn chưa cho phép thông báo. Mở cài đặt trang web của trình duyệt để cho phép lại.");
  const reg = await navigator.serviceWorker.ready;
  const { key } = await api<{ key: string }>("/api/push/key");
  let sub = await reg.pushManager.getSubscription();
  if (sub && sub.options.applicationServerKey && btoa(String.fromCharCode(...new Uint8Array(sub.options.applicationServerKey))) !== btoa(String.fromCharCode(...keyBytes(key)))) {
    await sub.unsubscribe(); sub = null;  // máy chủ đổi khóa: đăng ký lại
  }
  sub = sub || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(key) });
  await send("/api/push/subscribe", sub.toJSON());
}

export async function disablePush() {
  const sub = await currentSub();
  if (!sub) return;
  await send("/api/push/unsubscribe", { endpoint: sub.endpoint }).catch(() => {});
  await sub.unsubscribe();
}

/** Thiết bị đã đăng ký từ trước: báo lại máy chủ (đăng nhập tài khoản khác trên cùng máy thì thông báo theo tài khoản mới). */
export async function resyncPush() {
  try {
    const sub = await currentSub();
    if (sub && Notification.permission === "granted") await send("/api/push/subscribe", sub.toJSON());
  } catch { /* chưa đăng nhập hoặc mất mạng: bỏ qua */ }
}
