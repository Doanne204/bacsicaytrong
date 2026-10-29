// Gọi API Flask (cùng origin; lúc phát triển Vite proxy sang cổng 5000). Phiên đăng nhập dùng cookie.
export class ApiError extends Error {
  status: number;
  field?: string;
  email?: string;
  constructor(message: string, status: number, field?: string, email?: string) {
    super(message);
    this.status = status;
    this.field = field;
    this.email = email;
  }
}

export async function api<T = unknown>(url: string, opts: RequestInit = {}): Promise<T> {
  const r = await fetch(url, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const msg = r.status === 413 ? "Ảnh quá lớn, tối đa 8 MB." : j.error || `Máy chủ báo lỗi (${r.status}), hãy thử lại.`;
    throw new ApiError(msg, r.status, j.field, j.email);
  }
  return j as T;
}
export const send = <T = unknown>(url: string, body: unknown, method = "POST") =>
  api<T>(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const del = <T = unknown>(url: string) => api<T>(url, { method: "DELETE" });
export const upload = <T = unknown>(url: string, fd: FormData) => api<T>(url, { method: "POST", body: fd });

// ---------- Kiểu dữ liệu trả về từ API ----------
export interface Location { lat: number; lon: number; place: string | null }
export interface Me {
  id: number; username: string; email: string; phone: string | null; role: "user" | "admin"; created: string;
  stats: { scans: number; posts: number; ratings: number; treatments: number }; unread: number; due: number; location: Location | null;
}
export interface Plant { id: string; name: string; note: string; source: "model" | "ai" | "pest" }
export interface Candidate {
  raw: string; plant_id: string; plant: string; disease: string; healthy: boolean; remedy: string; prob: number;
  group_name?: string; hosts?: string; beneficial?: boolean;
}
export interface PestInfo { group_name: string; hosts: string; beneficial: boolean; sci: string }
export interface Diagnosis {
  id: number; plant_id: string; plant: string; disease: string; raw: string; healthy: boolean; confidence: number; remedy: string;
  image_url: string | null; source: "model" | "ai" | "memory"; created: string;
  details: { top?: Candidate[]; notes?: string[]; symptoms?: string; demo?: boolean; plant_choice?: string; ai_failed?: boolean;
    ai?: { plant_en?: string; disease_en?: string; differential?: string; confidence?: number } | null; kind?: "pest"; pest?: PestInfo | null;
    lesion_url?: string; lesion_available?: boolean; photos?: Photo[];
    severity?: { pct: number; level: "nhe" | "vua" | "nang"; label: string; advice: string; leaf_pct: number; photos?: number } | null };
  rating: { stars: number; comment: string } | null;
}
/** Một ảnh trong lượt tra cứu nhiều ảnh: kết quả mô hình riêng của ảnh đó, có được dùng để kết luận không, ảnh tô vết bệnh. */
export interface Photo { url: string; used: boolean; plant?: string; disease?: string; prob?: number; lesion_url?: string | null }
export interface PredictResult {
  diagnosis_id: number; result: Candidate; top: Candidate[]; source: string; demo: boolean; low_confidence: boolean; notes: string[]; image_url: string | null;
}
export interface HistoryItem {
  id: number; plant_id: string; plant: string; disease: string; healthy: boolean; confidence: number; image_url: string | null; source: string; created: string; stars: number | null;
}
export interface ChatMsg { role: "user" | "assistant"; content: string; created?: string; source?: string; image_url?: string | null }
export interface DiagCard { id: number; plant_id: string; plant: string; disease: string; confidence: number; healthy: boolean; source: string; image_url: string | null }
export interface Post {
  id: number; content: string; image_url: string | null; status: "pending" | "approved" | "rejected"; created: string; username: string; is_mine: boolean;
  likes: number; liked: boolean; comments: number; shares: number; diagnosis: DiagCard | null;
  shared: (Post & { deleted?: false }) | { deleted: true } | null; feedback?: string | null; ai_decision?: string | null; ai_reason?: string | null;
}
export interface Comment { id: number; content: string; created: string; username: string; can_delete: boolean }
export interface Notification { id: number; content: string; link: string | null; read: number; created: string }

// ---------- Nhật ký điều trị, nhắc việc ----------
export type LogKind = "phun" | "tia" | "tuoi" | "kiemtra" | "khac";
export const LOG_KINDS: Record<LogKind, string> = { phun: "Phun thuốc", tia: "Tỉa, vệ sinh", tuoi: "Tưới, bón phân", kiemtra: "Kiểm tra cây", khac: "Việc khác" };
export interface Reminder { id: number; content: string; due: string; repeat_days: number; done: number; created?: string }
export interface DueReminder extends Reminder { treatment_id: number; name: string | null; plant: string; disease: string; overdue: boolean }
/** Lịch việc theo ngày (/api/agenda): việc cần làm (projected = lần lặp lại sắp tới, chưa có thật) và việc đã làm. */
export interface AgendaTask extends DueReminder { projected: boolean }
export interface AgendaLog { id: number; kind: LogKind; content: string; at: string; treatment_id: number; name: string | null; plant: string; disease: string }
export interface Agenda { tasks: AgendaTask[]; logs: AgendaLog[] }
export interface LogEntry { id: number; kind: LogKind; content: string; image_url: string | null; done_at: string | null; created: string }
export interface Treatment {
  id: number; diagnosis_id: number | null; name: string | null; plant: string; disease: string; status: "active" | "done"; created: string; closed: string | null;
  logs: number; pending: number; overdue: number; next: { content: string; due: string } | null; last_log: string | null;
  diagnosis: { id: number; image_url: string | null; confidence: number; healthy: number; plant_id: string; source: string } | null;
}
export interface TreatmentDetail extends Treatment { reminders: Reminder[]; entries: LogEntry[]; remedy?: string | null }

// ---------- Thời tiết, cảnh báo ----------
export type Level = "thap" | "vua" | "cao";
export interface WeatherDay {
  date: string; tmin: number; tmax: number; tmean: number; rh: number | null; wet_hours: number; rain: number; wind: number | null; code: number | null; sun: number; desc: string;
  rain_prob?: number | null; uv?: number | null; sunrise?: string | null; sunset?: string | null;
}
export interface WeatherNow { time: string; temp: number; feels: number | null; rh: number | null; rain: number | null; code: number | null; wind: number | null; is_day: number; desc: string }
export interface WeatherHour { time: string; temp: number | null; rh: number | null; rain: number | null; rain_prob: number | null; code: number | null; is_day: number; desc: string }
export interface WeatherPart { key: "sang" | "chieu" | "toi"; name: string; temp: number; code: number | null; rain: number; rain_prob: number; is_day: boolean; desc: string }
export interface Alert { key: string; name: string; kind: "benh" | "sau" | "thoi_tiet"; level: Level; days: string[]; plants: string[]; plant_names: string[]; diseases: string[]; advice: string; mine: boolean }
export interface NearbyCase { plant: string; disease: string; count: number; level: Level }
export interface WeatherReport {
  location: Location; days: WeatherDay[]; alerts: Alert[]; nearby: NearbyCase[]; nearby_km: number; my_plants: string[];
  current: WeatherNow | null; hourly: WeatherHour[]; parts: WeatherPart[];
}
export interface GeoHit { name: string; lat: number; lon: number }

// ---------- Gợi ý thuốc (AI + Google Search) ----------
export interface Product {
  name: string; active_ingredient: string; kind: "sinh_hoc" | "hoa_hoc"; description: string; usage: string; pack: string;
  price_vnd: number | null; shop: string; url: string | null; page_title?: string | null; image: string | null;
}
export interface ProductReport { products: Product[]; sources: { title: string; url: string }[]; note: string; disease: string; plant: string; cached_at?: string }
export interface MapPoint { plant: string; disease: string; lat: number; lon: number; n: number; last: string }

// ---------- Báo kết quả sai, thư viện bệnh lá và sâu hại ----------
export interface WrongReport {
  id: number; class_name: string | null; plant: string | null; disease: string; note: string | null;
  status: "open" | "accepted" | "rejected"; answer: string | null; created: string; reviewed: string | null;
}
export interface LibDisease { class_name: string; plant_id: string; plant: string; disease: string; healthy: boolean; remedy: string; source: "model" | "ai" }
export interface LibPest { class_name: string; name: string; group: string; group_name: string; hosts: string; beneficial: boolean; remedy: string }
export interface Library { plants: { id: string; name: string }[]; diseases: LibDisease[]; pests: LibPest[]; groups: { id: string; name: string }[] }
export const libImage = (c: string) => `/api/library/image?c=${encodeURIComponent(c)}`;
