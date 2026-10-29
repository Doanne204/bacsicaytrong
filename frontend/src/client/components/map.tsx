import { useEffect, useRef, useState } from "react";
import type { MapPoint } from "@/shared/lib/api";
import { cn } from "@/shared/lib/utils";
import { loadLeaflet } from "./weather";

const esc = (s: unknown) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
const dmy = (s: string) => s.slice(0, 10).split("-").reverse().join("/");

/* eslint-disable @typescript-eslint/no-explicit-any */
/** Bản đồ vườn (Leaflet + OpenStreetMap): vị trí của tôi, vòng bán kính, ca bệnh người dùng báo quanh đây (đỏ, to theo số ca).
 *  Bấm vào điểm để xem chi tiết. */
export function GardenMap({ center, cases = [], radiusKm, className, zoom = 11 }: {
  center: { lat: number; lon: number; place?: string | null }; cases?: MapPoint[]; radiusKm?: number; className?: string; zoom?: number;
}) {
  const box = useRef<HTMLDivElement>(null), map = useRef<any>(null), layer = useRef<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let dead = false;
    loadLeaflet().then(() => {
      if (dead || !box.current) return;
      const L = (window as any).L;
      if (!map.current) {
        map.current = L.map(box.current, { scrollWheelZoom: false }).setView([center.lat, center.lon], zoom);
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(map.current);
      }
      if (layer.current) layer.current.remove();
      layer.current = L.layerGroup().addTo(map.current);
      if (radiusKm) L.circle([center.lat, center.lon], { radius: radiusKm * 1000, color: "#2f7d4f", weight: 1, fillOpacity: 0.04 }).addTo(layer.current);
      cases.forEach((p) => {
        L.circleMarker([p.lat, p.lon], { radius: Math.min(18, 6 + p.n * 2), color: "#b42318", weight: 1, fillColor: "#e5484d", fillOpacity: 0.5 })
          .bindPopup(`<b>${esc(p.disease)}</b><br>${esc(p.plant)}: ${p.n} ca, gần nhất ${dmy(p.last)}`).addTo(layer.current);
      });
      L.circleMarker([center.lat, center.lon], { radius: 8, color: "#fff", weight: 3, fillColor: "#2563eb", fillOpacity: 1 }).bindTooltip(center.place || "Vị trí của bạn").addTo(layer.current);
    }).catch((e) => setErr(e.message));
    return () => { dead = true; };
  }, [center.lat, center.lon, center.place, cases, radiusKm, zoom]);
  useEffect(() => () => { map.current?.remove(); map.current = null; }, []);
  return (
    <div className={cn("relative z-0 overflow-hidden rounded-2xl border bg-muted", className)}>
      <div ref={box} className="h-full w-full" aria-label="Bản đồ ca bệnh" />
      {err && <p className="absolute inset-0 grid place-items-center p-4 text-center text-sm text-muted-foreground">{err}</p>}
    </div>
  );
}
