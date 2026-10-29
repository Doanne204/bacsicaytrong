import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type MapPoint } from "@/shared/lib/api";
import { cn } from "@/shared/lib/utils";
import { useMe } from "@/shared/hooks/use-me";
import { Badge } from "@/shared/ui/badge";
import { Skeleton } from "@/shared/ui/misc";
import { PageHeader } from "@/shared/components/common";
import { LocationPicker } from "../components/weather";
import { GardenMap } from "../components/map";
import { NearbyStores } from "../components/shop";

const RADII = [5, 10, 30, 60];

function km(a: { lat: number; lon: number }, b: { lat: number; lon: number }) {
  const r = Math.PI / 180, dLat = (b.lat - a.lat) * r, dLon = (b.lon - a.lon) * r;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLon / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(h));
}

/** Bản đồ sâu bệnh quanh vườn: ca bệnh người dùng báo 60 ngày qua (vị trí làm tròn ~1 km, không lộ danh tính) trong bán kính chọn được,
 *  và bản đồ Google Maps tìm sẵn cửa hàng thuốc bảo vệ thực vật gần vườn. */
export default function MapPage() {
  const { me } = useMe();
  const loc = me?.location || null;
  const [radius, setRadius] = useState(10);
  const cases = useQuery({ queryKey: ["map"], queryFn: () => api<{ days: number; points: MapPoint[] }>("/api/map"), enabled: !!loc });
  const near = useMemo(() => (loc ? (cases.data?.points || []).filter((p) => km(loc, p) <= radius) : []), [cases.data, loc, radius]);
  const byDisease = useMemo(() => {
    const m: Record<string, { disease: string; plant: string; n: number; last: string }> = {};
    near.forEach((p) => { const k = `${p.plant}|${p.disease}`; const a = (m[k] ||= { disease: p.disease, plant: p.plant, n: 0, last: p.last }); a.n += p.n; if (p.last > a.last) a.last = p.last; });
    return Object.values(m).sort((a, b) => b.n - a.n);
  }, [near]);
  const zoom = radius <= 5 ? 13 : radius <= 10 ? 12 : radius <= 30 ? 10 : 9;
  return (
    <div className="animate-fade-up">
      <PageHeader title="Bản đồ sâu bệnh" text="Ca bệnh bà con báo quanh vườn bạn trong 60 ngày qua và cửa hàng thuốc, vật tư nông nghiệp gần nhất." />
      {!loc ? <LocationPicker value={null} /> : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="min-w-0">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold">Bán kính</span>
              {RADII.map((r) => (
                <button key={r} type="button" onClick={() => setRadius(r)} aria-pressed={radius === r}
                  className={cn("h-8 rounded-full border px-3 text-sm font-semibold transition", radius === r ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:border-primary")}>{r} km</button>
              ))}
            </div>
            <GardenMap center={loc} radiusKm={radius} zoom={zoom} cases={near} className="h-[60vh] min-h-[360px]" />
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full border-2 border-white bg-blue-600 shadow" />Vườn của bạn</span>
              <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full bg-[#e5484d]/70" />Ca bệnh (to hơn = nhiều ca)</span>
              <span>Vị trí ca bệnh làm tròn khoảng 1 km để giữ riêng tư.</span>
            </div>
          </div>
          <aside className="space-y-6">
            <section>
              <h2 className="mb-2 font-bold">Bệnh đang có trong {radius} km</h2>
              {cases.isLoading ? <Skeleton className="h-32" /> : !byDisease.length ? <p className="rounded-2xl border bg-card p-4 text-sm text-muted-foreground">Chưa ai báo ca bệnh nào trong {radius} km quanh vườn bạn 60 ngày qua.</p> : (
                <ul className="divide-y rounded-2xl border bg-card">
                  {byDisease.slice(0, 8).map((a) => (
                    <li key={a.plant + a.disease} className="flex items-center gap-3 px-4 py-3 text-sm">
                      <span className="min-w-0 flex-1"><b className="block">{a.disease}</b><span className="text-xs text-muted-foreground">{a.plant}, gần nhất {a.last.slice(0, 10).split("-").reverse().join("/")}</span></span>
                      <Badge variant={a.n >= 5 ? "destructive" : a.n >= 2 ? "warning" : "muted"}>{a.n} ca</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <LocationPicker value={loc} compact />
          </aside>
          <NearbyStores className="lg:col-span-2" mapClass="h-[60vh] min-h-[360px]" />
        </div>
      )}
    </div>
  );
}
