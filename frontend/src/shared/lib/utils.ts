import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));

// Máy chủ lưu giờ UTC dạng "YYYY-MM-DD HH:MM:SS"
export const toDate = (s: string) => new Date(String(s).replace(" ", "T") + "Z");
const pad = (n: number) => String(n).padStart(2, "0");
export const fmtDate = (d: Date) => `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
export const fmtTime = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
export const dayKey = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const WEEKDAYS = ["Chủ nhật", "Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy"];
export function dayLabel(d: Date) {
  const today = new Date(), y = new Date(Date.now() - 864e5);
  if (dayKey(d) === dayKey(today)) return `Hôm nay, ${fmtDate(d)}`;
  if (dayKey(d) === dayKey(y)) return `Hôm qua, ${fmtDate(d)}`;
  return `${WEEKDAYS[d.getDay()]}, ${fmtDate(d)}`;
}
export function ago(s: string) {
  const d = toDate(s), m = (Date.now() - d.getTime()) / 6e4;
  if (m < 1) return "Vừa xong";
  if (m < 60) return `${Math.floor(m)} phút trước`;
  if (m < 1440) return `${Math.floor(m / 60)} giờ trước`;
  if (m < 2880) return "Hôm qua";
  return fmtDate(d);
}
export const pct = (p?: number | null) => `${Math.round((p || 0) * 100)}%`;
export const initial = (name?: string) => (name || "?").trim().charAt(0).toUpperCase();
export const whenSec = (t: number) => { const d = new Date(t * 1000); return `${fmtTime(d)} ${fmtDate(d)}`; };
export const ddmm = (s: string) => { const [, m, d] = s.split("-"); return `${d}/${m}`; };

// Thu nhỏ ảnh trước khi gửi (ảnh điện thoại thường 3-8 MB); trình duyệt tự xoay đúng chiều theo EXIF
export async function shrink(file: File, max = 1600): Promise<File> {
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const k = Math.min(1, max / Math.max(bmp.width, bmp.height));
    const c = Object.assign(document.createElement("canvas"), { width: Math.round(bmp.width * k), height: Math.round(bmp.height * k) });
    c.getContext("2d")!.drawImage(bmp, 0, 0, c.width, c.height);
    const blob = await new Promise<Blob | null>((r) => c.toBlob(r, "image/jpeg", 0.9));
    return blob ? new File([blob], "anh.jpg", { type: "image/jpeg" }) : file;
  } catch {
    return file;
  }
}
// Camera trực tiếp trong trang chỉ có khi chạy HTTPS hoặc localhost
export const liveCamera = () => window.isSecureContext && !!navigator.mediaDevices?.getUserMedia;
export function pickFile(capture = false): Promise<File | null> {
  return new Promise((resolve) => {
    const inp = Object.assign(document.createElement("input"), { type: "file", accept: "image/*" });
    if (capture) inp.setAttribute("capture", "environment");
    inp.onchange = () => resolve(inp.files?.[0] || null);
    inp.click();
  });
}
export async function copyText(text: string) {
  try { await navigator.clipboard.writeText(text); return; } catch { /* http://<IP LAN> không có Clipboard API */ }
  const t = Object.assign(document.createElement("textarea"), { value: text });
  document.body.appendChild(t); t.select(); document.execCommand("copy"); t.remove();
}

export const RE = {
  username: /^[A-Za-z0-9_.]{3,30}$/,
  email: /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/,
  phone: /^0[35789]\d{8}$/,
};
export function normPhone(p: string) {
  p = (p || "").replace(/[\s.\-()]/g, "");
  if (p.startsWith("+84")) p = "0" + p.slice(3);
  else if (p.startsWith("84") && p.length === 11) p = "0" + p.slice(2);
  return p;
}
export const MSG = {
  username: "Tên đăng nhập 3-30 ký tự, chỉ gồm chữ không dấu, số, dấu _ hoặc .",
  email: "Email không hợp lệ (VD: ten@gmail.com)",
  phone: "Số điện thoại cần 10 số, bắt đầu bằng 03, 05, 07, 08 hoặc 09",
  password: "Mật khẩu tối thiểu 6 ký tự",
};
