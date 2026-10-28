import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Cloud, CloudDrizzle, CloudFog, CloudLightning, CloudRain, CloudSun, LocateFixed, Search, Snowflake, Sun, X } from "lucide-react";
import { api, send, type GeoHit, type Level, type Location, type MapPoint } from "@/shared/lib/api";
import { cn } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";

export const LEVEL: Record<Level, { label: string; badge: "destructive" | "warning" | "muted"; bar: string }> = {
  cao: { label: "Nguy cơ cao", badge: "destructive", bar: "bg-destructive" }, vua: { label: "Nguy cơ vừa", badge: "warning", bar: "bg-warning" }, thap: { label: "Theo dõi", badge: "muted", bar: "bg-muted-foreground/40" },
};

/** Biểu tượng theo mã thời tiết WMO của Open-Meteo. */
export function WeatherIcon({ code, className }: { code: number | null; className?: string }) {
  const c = code ?? 0;
  const I = c === 0 ? Sun : c <= 2 ? CloudSun : c === 3 ? Cloud : c <= 48 ? CloudFog : c <= 57 ? CloudDrizzle : c <= 67 || (c >= 80 && c <= 82) ? CloudRain : c <= 77 || c <= 86 ? Snowflake : CloudLightning;
  return <I className={className} />;
}

/** Chọn vị trí: GPS của thiết bị hoặc tìm địa danh; lưu vào hồ sơ. */
export function LocationPicker({ value, onChange, compact }: { value: Location | null; onChange?: (l: Location | null) => void; compact?: boolean }) {
  const qc = useQueryClient();
  const [q, setQ] = useState(""), [hits, setHits] = useState<GeoHit[]>([]), [busy, setBusy] = useState(""), [open, setOpen] = useState(!value);
  const save = async (l: Location | null) => {
    try { await send("/api/me/location", l || { lat: null }, "PUT"); qc.invalidateQueries({ queryKey: ["me"] }); onChange?.(l); setOpen(!l); setHits([]); setQ(""); toast.success(l ? `Đã lưu vị trí: ${l.place || "tọa độ GPS"}` : "Đã xóa vị trí"); }
    catch (e) { toast.error((e as Error).message); }
  };
  const gps = () => {
    if (!navigator.geolocation) return toast.error("Trình duyệt không hỗ trợ định vị");
    setBusy("gps");
    navigator.geolocation.getCurrentPosition(
      (p) => { setBusy(""); save({ lat: +p.coords.latitude.toFixed(4), lon: +p.coords.longitude.toFixed(4), place: null }); },
      (e) => { setBusy(""); toast.error(e.code === 1 ? "Bạn đã từ chối quyền định vị; hãy tìm theo tên địa danh" : "Không lấy được vị trí (cần HTTPS hoặc bật GPS)"); },
      { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 },
    );
  };
  const search = async (e: React.FormEvent) => {
    e.preventDefault();
    if (q.trim().length < 2) return;
    setBusy("q");
    try { const r = await api<GeoHit[]>(`/api/geocode?q=${encodeURIComponent(q.trim())}`); setHits(r); if (!r.length) toast.error("Không tìm thấy địa danh, thử tên tỉnh/huyện khác"); }
    catch (e) { toast.error((e as Error).message); } finally { setBusy(""); }
  };
  return (
    <div className={cn("rounded-2xl border bg-card", compact ? "p-3" : "p-4")}>
      {value && !open ? (
        <div className="flex items-center gap-2 text-sm">
          <LocateFixed className="h-4 w-4 shrink-0 text-primary" />
          <span className="min-w-0 flex-1 truncate"><b>{value.place || "Vị trí GPS"}</b> <span className="text-muted-foreground">({value.lat.toFixed(3)}, {value.lon.toFixed(3)})</span></span>
          <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>Đổi</Button>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm">{value ? "Chọn vị trí mới" : "Đặt vị trí vườn/ruộng để nhận dự báo và cảnh báo sâu bệnh cho đúng nơi bạn canh tác."}</p>
          <div className="flex flex-wrap gap-2">
            <Button onClick={gps} loading={busy === "gps"}><LocateFixed />Dùng vị trí của tôi</Button>
            {value && <Button variant="ghost" onClick={() => setOpen(false)}>Hủy</Button>}
          </div>
          <form onSubmit={search} className="flex gap-2">
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Hoặc nhập tỉnh, huyện, xã (VD: Đà Lạt)" aria-label="Tìm địa danh" />
            <Button type="submit" variant="outline" size="icon" loading={busy === "q"} aria-label="Tìm"><Search /></Button>
          </form>
          {!!hits.length && (
            <ul className="divide-y rounded-xl border">
              {hits.map((h, i) => <li key={i}><button type="button" onClick={() => save({ lat: h.lat, lon: h.lon, place: h.name })} className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm hover:bg-accent"><LocateFixed className="h-4 w-4 shrink-0 text-muted-foreground" /><span className="flex-1">{h.name}</span></button></li>)}
            </ul>
          )}
          {value && <button type="button" onClick={() => save(null)} className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-destructive"><X className="h-3.5 w-3.5" />Xóa vị trí đã lưu</button>}
        </div>
      )}
    </div>
  );
}

// ---------- Bản đồ ca bệnh (Leaflet + OpenStreetMap, nạp từ CDN khi mở trang) ----------
const LEAFLET = "https://unpkg.com/leaflet@1.9.4/dist/";
let leafletLoading: Promise<void> | null = null;
function loadLeaflet() {
  if ((window as unknown as { L?: unknown }).L) return Promise.resolve();
  if (!leafletLoading) {
    leafletLoading = new Promise((resolve, reject) => {
      if (!document.querySelector("link[data-leaflet]")) { const css = document.createElement("link"); css.rel = "stylesheet"; css.href = LEAFLET + "leaflet.css"; css.setAttribute("data-leaflet", "1"); document.head.appendChild(css); }
      const s = document.createElement("script"); s.src = LEAFLET + "leaflet.js"; s.onload = () => resolve(); s.onerror = () => reject(new Error("Không tải được bản đồ (cần Internet)")); document.head.appendChild(s);
    });
  }
  return leafletLoading;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
export function CaseMap({ center, points, radiusKm, className }: { center: Location; points: MapPoint[]; radiusKm: number; className?: string }) {
  const box = useRef<HTMLDivElement>(null), map = useRef<any>(null), layer = useRef<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let dead = false;
    loadLeaflet().then(() => {
      if (dead || !box.current) return;
      const L = (window as any).L;
      if (!map.current) {
        map.current = L.map(box.current, { scrollWheelZoom: false }).setView([center.lat, center.lon], 9);
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(map.current);
      } else map.current.setView([center.lat, center.lon], map.current.getZoom());
      if (layer.current) layer.current.remove();
      layer.current = L.layerGroup().addTo(map.current);
      L.circle([center.lat, center.lon], { radius: radiusKm * 1000, color: "#2f7d4f", weight: 1, fillOpacity: 0.05 }).addTo(layer.current);
      L.circleMarker([center.lat, center.lon], { radius: 7, color: "#fff", weight: 2, fillColor: "#2f7d4f", fillOpacity: 1 }).bindTooltip(center.place || "Vị trí của bạn").addTo(layer.current);
      points.forEach((p) => {
        L.circleMarker([p.lat, p.lon], { radius: Math.min(16, 6 + p.n * 2), color: "#b42318", weight: 1, fillColor: "#e5484d", fillOpacity: 0.55 })
          .bindPopup(`<b>${p.disease}</b><br>${p.plant}: ${p.n} ca, gần nhất ${p.last.slice(0, 10).split("-").reverse().join("/")}`).addTo(layer.current);
      });
    }).catch((e) => setErr(e.message));
    return () => { dead = true; };
  }, [center.lat, center.lon, center.place, points, radiusKm]);
  useEffect(() => () => { map.current?.remove(); map.current = null; }, []);
  return (
    <div className={cn("relative overflow-hidden rounded-2xl border bg-muted", className)}>
      <div ref={box} className="h-full w-full" aria-label="Bản đồ ca bệnh" />
      {err && <p className="absolute inset-0 grid place-items-center p-4 text-center text-sm text-muted-foreground">{err}</p>}
    </div>
  );
}
