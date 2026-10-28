import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertTriangle, Bug, CloudSun, Droplets, Info, Leaf, MapPin, Sunrise, Sunset, Thermometer, Umbrella, Wind, SunMedium, CloudRain } from "lucide-react";
import { api, type Alert, type MapPoint, type WeatherDay, type WeatherReport } from "@/shared/lib/api";
import { cn, ddmm } from "@/shared/lib/utils";
import { useMe } from "@/shared/hooks/use-me";
import { Badge } from "@/shared/ui/badge";
import { EmptyState, Notice, Skeleton } from "@/shared/ui/misc";
import { PageHeader } from "@/shared/components/common";
import { CaseMap, LEVEL, LocationPicker } from "../components/weather";
import { SkyScene, WxIcon } from "../components/sky";

const WEEK = ["Chủ nhật", "Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy"];
const SHORT = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];
const asDate = (s: string) => new Date(s.slice(0, 10) + "T00:00");
const deg = (v?: number | null) => (v === null || v === undefined ? "–" : `${Math.round(v)}°`);
const DEMO_DESC: Record<number, string> = { 0: "Trời quang", 2: "Có mây", 3: "Nhiều mây", 45: "Sương mù", 53: "Mưa phùn", 61: "Mưa nhỏ", 65: "Mưa to", 71: "Tuyết nhẹ", 95: "Dông" };
const uvLabel =(u?: number | null) => (u === null || u === undefined ? "–" : `${Math.round(u)} ${u < 3 ? "thấp" : u < 6 ? "vừa" : u < 8 ? "cao" : "rất cao"}`);

export default function Weather() {
  const { me } = useMe();
  const loc = me?.location || null;
  const q = useQuery({ queryKey: ["weather", loc?.lat, loc?.lon], queryFn: () => api<WeatherReport>("/api/weather"), enabled: !!loc, staleTime: 15 * 60_000, retry: false });
  const map = useQuery({ queryKey: ["map"], queryFn: () => api<{ days: number; points: MapPoint[] }>("/api/map"), enabled: !!loc, staleTime: 15 * 60_000 });
  const r = q.data;
  return (
    <div className="animate-fade-up">
      <PageHeader title="Thời tiết và cảnh báo sâu bệnh" text="Dự báo Open-Meteo cho vị trí vườn của bạn, đối chiếu với điều kiện phát sinh của từng bệnh, sâu hại." />
      {!loc ? (
        <div className="mx-auto max-w-xl space-y-4"><LocationPicker value={null} /><EmptyState icon={MapPin} title="Chưa có vị trí" text="Đặt vị trí vườn/ruộng ở trên để xem dự báo và cảnh báo." /></div>
      ) : q.isLoading ? <Skeleton className="h-[520px] rounded-3xl" />
        : q.error ? <div className="space-y-4"><Notice tone="danger" icon={AlertTriangle}>{(q.error as Error).message}</Notice><LocationPicker value={loc} /></div>
        : r && (
          <>
            <Sky r={r} />
            <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
              <div className="space-y-6">
                <section>
                  <h2 className="mb-2 flex items-center gap-2 font-bold"><AlertTriangle className="h-5 w-5 text-warning" />Cảnh báo sâu bệnh 5 ngày tới</h2>
                  {!!r.my_plants.length && <p className="mb-3 text-sm text-muted-foreground">Xếp trước các cảnh báo liên quan đến cây bạn đã tra cứu hoặc đang theo dõi: <b className="text-foreground">{r.my_plants.join(", ")}</b>.</p>}
                  {!r.alerts.some((a) => a.level !== "thap") && <Notice tone="ok" icon={Leaf} className="mb-3">Thời tiết 5 ngày tới không có điều kiện đặc biệt thuận lợi cho sâu bệnh. Vẫn nên thăm vườn 5-7 ngày/lần.</Notice>}
                  <div className="space-y-3">{r.alerts.filter((a) => a.level !== "thap").map((a) => <AlertCard key={a.key} a={a} />)}</div>
                  {r.alerts.some((a) => a.level === "thap") && (
                    <details className="mt-3 rounded-2xl border bg-card p-4">
                      <summary className="cursor-pointer text-sm font-semibold">Theo dõi thêm (chỉ 1 ngày thuận lợi): {r.alerts.filter((a) => a.level === "thap").map((a) => a.name).join(", ")}</summary>
                      <div className="mt-3 space-y-3">{r.alerts.filter((a) => a.level === "thap").map((a) => <AlertCard key={a.key} a={a} />)}</div>
                    </details>
                  )}
                </section>
                <section>
                  <h2 className="mb-2 flex items-center gap-2 font-bold"><MapPin className="h-5 w-5 text-primary" />Quanh bạn {r.nearby_km} km, 14 ngày qua</h2>
                  {!r.nearby.length ? <p className="rounded-2xl border border-dashed p-4 text-sm text-muted-foreground">Chưa có ca bệnh nào do bà con tra cứu gần vị trí này. Khi bạn và người khác tra cứu với vị trí đã lưu, ca bệnh sẽ hiện ở đây và trên bản đồ (ẩn danh, tọa độ làm tròn ~1 km).</p>
                    : <ul className="divide-y rounded-2xl border bg-card">
                      {r.nearby.map((n, i) => <li key={i} className="flex items-center gap-3 px-4 py-3 text-sm"><Bug className="h-4 w-4 shrink-0 text-destructive" /><span className="min-w-0 flex-1"><b className="block">{n.disease}</b><span className="text-xs text-muted-foreground">{n.plant}</span></span><Badge variant={LEVEL[n.level].badge}>{n.count} ca</Badge></li>)}
                    </ul>}
                  {map.data && <CaseMap center={r.location} points={map.data.points} radiusKm={r.nearby_km} className="mt-3 h-[320px] md:h-[400px]" />}
                  {map.data && <p className="mt-1 text-xs text-muted-foreground">Chấm đỏ: ca bệnh {map.data.days} ngày qua của mọi người dùng đã lưu vị trí (to hơn = nhiều ca). Vòng xanh: bán kính {r.nearby_km} km quanh bạn.</p>}
                </section>
              </div>
              <aside className="space-y-4">
                <LocationPicker value={loc} />
                <Notice icon={Info}>
                  <p><b>Cách tính cảnh báo:</b> mỗi bệnh/sâu có ngưỡng nhiệt độ, ẩm độ, số giờ ẩm ≥ 90%, mưa, gió thuận lợi (theo tài liệu bảo vệ thực vật). Số ngày thuận lợi trong 5 ngày tới: 1 ngày = theo dõi, 2 ngày = nguy cơ vừa, từ 3 ngày = nguy cơ cao.</p>
                  <p className="mt-2">Cảnh báo mức cao được gửi thông báo mỗi sáng khi máy chủ chạy lệnh nhắc theo lịch. Lưu vị trí cũng giúp ghim ca bệnh của bạn lên bản đồ chung (ẩn danh).</p>
                </Notice>
                <p className="text-sm"><Link to="/journal" className="font-semibold text-primary hover:underline">Mở nhật ký điều trị</Link> để đặt lịch phun phòng trước đợt mưa.</p>
              </aside>
            </div>
          </>
        )}
    </div>
  );
}

/** Khung thời tiết kiểu ứng dụng điện thoại: bầu trời động theo thời tiết hiện tại, các thẻ kính mờ. */
function Sky({ r }: { r: WeatherReport }) {
  const todayKey = (r.current?.time || new Date().toISOString()).slice(0, 10);
  const idx = Math.max(0, r.days.findIndex((d) => d.date === todayKey));
  const today = r.days[idx], tomorrow = r.days[idx + 1], week = r.days.slice(idx, idx + 7);
  const base = r.current || { temp: today.tmean, feels: null, rh: today.rh, rain: today.rain, code: today.code, wind: today.wind, is_day: 1, desc: today.desc, time: todayKey };
  // Xem thử hiệu ứng (trình diễn): /weather?wx=<mã WMO>&dem=1, VD wx=61 mưa, 95 dông, 45 sương mù, 71 tuyết, 0&dem=1 trời đêm
  const demo = new URLSearchParams(window.location.search);
  const now = demo.has("wx") ? { ...base, code: Number(demo.get("wx")), is_day: demo.get("dem") ? 0 : 1, desc: DEMO_DESC[Number(demo.get("wx"))] || base.desc } : base;
  const date = asDate(todayKey);
  const details: [React.ComponentType<{ className?: string }>, string, string][] = [
    [Thermometer, "Cảm giác như", deg(now.feels)], [Droplets, "Độ ẩm", now.rh === null ? "–" : `${now.rh}%`],
    [Wind, "Gió", now.wind === null ? "–" : `${Math.round(now.wind)} km/h`], [SunMedium, "Chỉ số UV", uvLabel(today.uv)],
    [Umbrella, "Khả năng mưa", today.rain_prob === null || today.rain_prob === undefined ? "–" : `${today.rain_prob}%`], [CloudRain, "Lượng mưa hôm nay", `${today.rain} mm`],
  ];
  return (
    <SkyScene code={now.code} isDay={now.is_day} className="p-3 sm:p-4 md:p-5">
      <div className="grid grid-cols-[repeat(2,minmax(0,1fr))] gap-3 md:gap-4 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <section className="wx-glass col-span-2 p-4 sm:p-5 lg:col-span-1">
          <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
            <div>
              <p className="text-2xl font-light tracking-wide sm:text-3xl">{WEEK[date.getDay()]}</p>
              <p className="text-sm text-white/80">{date.getDate()} tháng {date.getMonth() + 1}{r.location.place ? ` · ${r.location.place}` : ""}</p>
            </div>
            {now.time && <span className="rounded-full bg-white/15 px-2.5 py-1 text-xs text-white/85">Cập nhật {now.time.slice(11, 16)}</span>}
          </div>
          <div className="mt-3 flex items-center gap-3 sm:gap-5">
            <WxIcon code={now.code} isDay={now.is_day} size={104} className="sm:h-[128px] sm:w-[128px]" />
            <div>
              <p className="text-6xl font-extralight leading-none tabular-nums sm:text-7xl">{Math.round(now.temp)}°<span className="align-top text-2xl font-light sm:text-3xl">C</span></p>
              <p className="mt-1 font-medium">{now.desc || today.desc}</p>
              <p className="text-sm text-white/80">Cao {deg(today.tmax)} · Thấp {deg(today.tmin)}</p>
            </div>
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
            {details.map(([I, k, v]) => <div key={k} className="flex items-center gap-2"><I className="h-4 w-4 shrink-0 text-white/75" /><dt className="sr-only">{k}</dt><span className="min-w-0"><span className="block text-[11px] text-white/70">{k}</span><dd className="font-semibold">{v}</dd></span></div>)}
          </dl>
          {(today.sunrise || today.sunset) && (
            <div className="mt-4 flex gap-6 border-t border-white/20 pt-3 text-sm">
              <span className="inline-flex items-center gap-2"><Sunrise className="h-5 w-5 text-yellow-200" />Mọc <b>{today.sunrise}</b></span>
              <span className="inline-flex items-center gap-2"><Sunset className="h-5 w-5 text-orange-200" />Lặn <b>{today.sunset}</b></span>
            </div>
          )}
        </section>
        <DayCard title="Hôm nay" d={today} />
        {tomorrow && <DayCard title="Ngày mai" d={tomorrow} />}

        {!!r.hourly.length && (
          <section className="wx-glass col-span-2 p-3 lg:col-span-3">
            <h3 className="mb-2 px-1 text-sm font-semibold text-white/90">24 giờ tới</h3>
            <div className="no-scrollbar -mx-1 flex snap-x gap-1 overflow-x-auto px-1">
              {r.hourly.map((h, i) => (
                <div key={h.time} className={cn("flex w-[68px] shrink-0 snap-start flex-col items-center gap-1 rounded-xl py-2", i === 0 && "bg-white/15")}>
                  <span className="text-xs text-white/85">{i === 0 ? "Bây giờ" : h.time.slice(11, 16)}</span>
                  <WxIcon code={h.code} isDay={h.is_day} size={34} />
                  <b className="tabular-nums">{deg(h.temp)}</b>
                  <span className={cn("text-[11px] tabular-nums", h.rain_prob ? "text-sky-100" : "text-transparent")}>{h.rain_prob || 0}%</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {!!r.parts.length && (
          <div className="col-span-2 grid grid-cols-3 gap-2 md:gap-4 lg:col-span-3">
            {r.parts.map((p) => (
              <section key={p.key} className="wx-glass flex flex-col items-center gap-1 p-3 text-center sm:flex-row sm:gap-3 sm:p-4 sm:text-left">
                <WxIcon code={p.code} isDay={p.is_day} size={52} />
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-white/90 sm:text-sm">{p.name}</p>
                  <p className="text-2xl font-light tabular-nums sm:text-3xl">{deg(p.temp)}</p>
                  <p className="text-[11px] leading-tight text-white/80 sm:text-xs">{p.desc}{p.rain_prob ? ` · mưa ${p.rain_prob}%` : ""}</p>
                </div>
              </section>
            ))}
          </div>
        )}

        <section className="wx-glass col-span-2 p-3 lg:col-span-3">
          <h3 className="mb-2 px-1 text-sm font-semibold text-white/90">7 ngày tới</h3>
          <div className="no-scrollbar -mx-1 flex snap-x gap-1 overflow-x-auto px-1 md:grid md:grid-cols-7">
            {week.map((d, i) => { const dt = asDate(d.date); return (
              <div key={d.date} className={cn("flex w-[84px] shrink-0 snap-start flex-col items-center gap-1 rounded-xl py-2 md:w-auto", i === 0 && "bg-white/15")}>
                <b className="text-sm">{i === 0 ? "Hôm nay" : SHORT[dt.getDay()]}</b>
                <span className="text-[11px] text-white/75">{ddmm(d.date)}</span>
                <WxIcon code={d.code} size={40} />
                <b className="tabular-nums">{deg(d.tmax)}</b>
                <span className="text-sm tabular-nums text-white/75">{deg(d.tmin)}</span>
                <span className="text-[11px] text-sky-100">{d.rain > 0 ? `${d.rain} mm` : " "}</span>
              </div>
            ); })}
          </div>
        </section>
      </div>
    </SkyScene>
  );
}

function DayCard({ title, d }: { title: string; d: WeatherDay }) {
  const rows: [string, string][] = [
    ["Khả năng mưa", d.rain_prob === null || d.rain_prob === undefined ? "–" : `${d.rain_prob}%`], ["Lượng mưa", `${d.rain} mm`],
    ["Độ ẩm TB", d.rh === null ? "–" : `${d.rh}%`], ["Gió mạnh nhất", d.wind === null ? "–" : `${Math.round(d.wind)} km/h`],
    ["Giờ nắng", `${d.sun} giờ`], ["UV", uvLabel(d.uv)],
  ];
  return (
    <section className="wx-glass flex flex-col p-4">
      <p className="text-sm font-semibold uppercase tracking-wide text-white/85">{title}</p>
      <div className="mt-2 flex items-center justify-between gap-2"><span className="text-4xl font-light tabular-nums">{deg(d.tmax)}</span><WxIcon code={d.code} size={52} /></div>
      <p className="text-xs text-white/80">{d.desc}</p>
      <div className="mt-3 flex items-center justify-between gap-2 border-t border-white/20 pt-2"><span className="text-3xl font-light tabular-nums text-white/85">{deg(d.tmin)}</span><WxIcon code={0} isDay={false} size={36} /></div>
      <p className="text-xs text-white/75">Thấp nhất (đêm)</p>
      <dl className="mt-auto hidden space-y-1 border-t border-white/20 pt-3 text-xs lg:block">
        {rows.map(([k, v]) => <div key={k} className="flex justify-between gap-2"><dt className="text-white/70">{k}</dt><dd className="font-semibold">{v}</dd></div>)}
      </dl>
    </section>
  );
}

function AlertCard({ a }: { a: Alert }) {
  const lv = LEVEL[a.level];
  return (
    <article className={cn("overflow-hidden rounded-2xl border bg-card", a.level === "cao" && "border-destructive/40")}>
      <div className={cn("h-1.5", lv.bar)} />
      <div className="p-4">
        <div className="flex flex-wrap items-center gap-2">
          {a.kind === "benh" ? <Leaf className="h-5 w-5 text-primary" /> : a.kind === "sau" ? <Bug className="h-5 w-5 text-primary" /> : <CloudSun className="h-5 w-5 text-primary" />}
          <h3 className="font-bold">{a.name}</h3>
          <Badge variant={lv.badge}>{lv.label}</Badge>
          {a.mine && a.plants.length > 0 && <Badge variant="paddy">Cây của bạn</Badge>}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">Ngày thuận lợi: {a.days.map(ddmm).join(", ")}{a.plant_names.length ? ` · Cây: ${a.plant_names.join(", ")}` : ""}</p>
        <p className="mt-2 text-sm leading-relaxed">{a.advice}</p>
        {!!a.diseases.length && <p className="mt-2 text-xs text-muted-foreground">Bệnh liên quan trong ứng dụng: {a.diseases.join("; ")}</p>}
      </div>
    </article>
  );
}
