import { useEffect, useMemo, useRef } from "react";
import { cn } from "@/shared/lib/utils";

/** Nhóm thời tiết theo mã WMO của Open-Meteo. */
export type WxKind = "clear" | "partly" | "cloudy" | "fog" | "drizzle" | "rain" | "heavy" | "storm" | "snow";
export function wxKind(code: number | null | undefined): WxKind {
  const c = code ?? 0;
  if (c >= 95) return "storm";
  if ([71, 73, 75, 77, 85, 86].includes(c)) return "snow";
  if ([65, 67, 82].includes(c)) return "heavy";
  if ((c >= 61 && c <= 67) || (c >= 80 && c <= 82)) return "rain";
  if (c >= 51 && c <= 57) return "drizzle";
  if (c === 45 || c === 48) return "fog";
  if (c === 3) return "cloudy";
  if (c === 1 || c === 2) return "partly";
  return "clear";
}

const SUN = "#FDB813", MOON = "#FDE68A", RAIN = "#60A5FA", BOLT = "#FACC15";

function Cloud({ x = 0, y = 0, s = 1, fill = "#fff" }: { x?: number; y?: number; s?: number; fill?: string }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`} fill={fill}>
      <circle cx="22" cy="34" r="10" /><circle cx="34" cy="27" r="13" /><circle cx="46" cy="35" r="9" />
      <rect x="12" y="34" width="44" height="12" rx="6" />
    </g>
  );
}
function Sun({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  return (
    <g>
      {Array.from({ length: 8 }, (_, i) => { const a = (i * Math.PI) / 4; return <line key={i} x1={cx + Math.cos(a) * (r + 4)} y1={cy + Math.sin(a) * (r + 4)} x2={cx + Math.cos(a) * (r + 9)} y2={cy + Math.sin(a) * (r + 9)} stroke={SUN} strokeWidth="3" strokeLinecap="round" />; })}
      <circle cx={cx} cy={cy} r={r} fill={SUN} />
    </g>
  );
}
function Moon({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  return <path d={`M${cx + r * 0.35} ${cy - r} a${r} ${r} 0 1 0 ${r * 0.65} ${r * 1.55} a${r * 0.8} ${r * 0.8} 0 0 1 -${r * 0.65} -${r * 1.55}z`} fill={MOON} />;
}

/** Biểu tượng thời tiết nhiều màu (mặt trời vàng, mây trắng, mưa xanh, sét vàng), ban đêm thay mặt trời bằng trăng. */
export function WxIcon({ code, isDay = true, size = 48, className }: { code: number | null | undefined; isDay?: boolean | number; size?: number; className?: string }) {
  const k = wxKind(code), day = !!isDay;
  const grey = k === "storm" || k === "heavy" ? "#94A3B8" : "#CBD5E1";
  const drops = (n: number) => Array.from({ length: n }, (_, i) => { const x = 22 + i * (24 / Math.max(1, n - 1)); return <line key={i} x1={x} y1="50" x2={x - 3} y2="59" stroke={RAIN} strokeWidth="2.5" strokeLinecap="round" />; });
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} className={cn("shrink-0 drop-shadow-sm", className)} aria-hidden>
      {k === "clear" && (day ? <Sun cx={32} cy={32} r={13} /> : <Moon cx={30} cy={32} r={15} />)}
      {k === "partly" && <>{day ? <Sun cx={24} cy={22} r={10} /> : <Moon cx={22} cy={22} r={11} />}<Cloud x={6} y={10} s={0.95} /></>}
      {k === "cloudy" && <><Cloud x={12} y={0} s={0.8} fill={grey} /><Cloud x={2} y={10} /></>}
      {k === "fog" && <><Cloud x={4} y={-2} s={0.9} fill="#E2E8F0" />{[44, 51, 58].map((y, i) => <line key={y} x1={12 + i * 3} y1={y} x2={52 - i * 3} y2={y} stroke="#E2E8F0" strokeWidth="3" strokeLinecap="round" />)}</>}
      {k === "drizzle" && <><Cloud x={4} y={-4} />{drops(2)}</>}
      {(k === "rain" || k === "heavy") && <><Cloud x={4} y={-4} fill={k === "heavy" ? grey : "#fff"} />{drops(k === "heavy" ? 4 : 3)}</>}
      {k === "storm" && <><Cloud x={4} y={-6} fill={grey} /><polygon points="33,40 25,53 31,53 27,63 39,48 33,48 37,40" fill={BOLT} />{drops(2)}</>}
      {k === "snow" && <><Cloud x={4} y={-4} />{[[22, 52], [32, 57], [42, 52], [27, 61], [37, 61]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r="2.4" fill="#fff" stroke={RAIN} strokeWidth="1" />)}</>}
    </svg>
  );
}

const BG: Record<string, string> = {
  "clear-day": "from-sky-400 via-sky-500 to-blue-600", "partly-day": "from-sky-400 via-blue-500 to-blue-600",
  "cloudy-day": "from-slate-400 via-slate-500 to-slate-600", "fog-day": "from-slate-400 via-slate-500 to-slate-600",
  "drizzle-day": "from-slate-500 via-slate-600 to-sky-800", "rain-day": "from-slate-600 via-slate-700 to-sky-900",
  "heavy-day": "from-slate-700 via-slate-800 to-slate-900", "storm-day": "from-slate-800 via-indigo-950 to-slate-900",
  "snow-day": "from-slate-400 via-sky-500 to-blue-600", night: "from-indigo-950 via-blue-950 to-slate-900",
  "night-cloudy": "from-slate-800 via-slate-900 to-slate-950",
};

/** Bầu trời động phía sau các thẻ thời tiết: nắng, sao, mây trôi, mưa, dông (chớp), sương mù, tuyết theo thời tiết hiện tại. */
export function SkyScene({ code, isDay = true, className, children }: { code: number | null | undefined; isDay?: boolean | number; className?: string; children: React.ReactNode }) {
  const k = wxKind(code), day = !!isDay;
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {  // chiều cao / chiều rộng khung để mưa rơi tới đáy, mây trôi hết bề ngang
    const el = box.current; if (!el) return;
    const set = () => { el.style.setProperty("--fall", `${el.offsetHeight}px`); el.style.setProperty("--wide", `${el.offsetWidth}px`); };
    set(); const ro = new ResizeObserver(set); ro.observe(el); return () => ro.disconnect();
  }, []);
  const rnd = (i: number, m: number) => ((i * 9301 + 49297) % 233280) / 233280 * m;  // ngẫu nhiên cố định theo chỉ số
  const nDrops = { drizzle: 45, rain: 110, heavy: 170, storm: 150 }[k as "rain"] || 0;
  const drops = useMemo(() => Array.from({ length: nDrops }, (_, i) => ({ left: rnd(i + 1, 105) - 2, h: 12 + rnd(i + 7, 16), d: (k === "drizzle" ? 1.1 : 0.55) + rnd(i + 3, 0.35), delay: -rnd(i + 11, 2) })), [nDrops, k]);
  const flakes = useMemo(() => (k === "snow" ? Array.from({ length: 70 }, (_, i) => ({ left: rnd(i + 2, 100), s: 2 + rnd(i + 5, 4), d: 7 + rnd(i + 9, 7), delay: -rnd(i + 13, 14) })) : []), [k]);
  const stars = useMemo(() => (!day && (k === "clear" || k === "partly") ? Array.from({ length: 45 }, (_, i) => ({ left: rnd(i + 4, 100), top: rnd(i + 8, 60), s: 1 + rnd(i + 6, 2), d: 2 + rnd(i + 1, 3), delay: -rnd(i + 2, 3) })) : []), [k, day]);
  const clouds = k === "clear" ? 0 : k === "partly" ? 3 : 5;
  const dark = ["rain", "heavy", "storm"].includes(k);
  const bg = !day ? (k === "clear" || k === "partly" ? BG.night : BG["night-cloudy"]) : BG[`${k}-day`] || BG["clear-day"];
  return (
    <div ref={box} className={cn("relative isolate overflow-hidden rounded-3xl bg-gradient-to-br text-white", bg, className)}>
      <div className="pointer-events-none absolute inset-0 -z-10" aria-hidden>
        {day && (k === "clear" || k === "partly") && (
          <div className="absolute -right-16 -top-16 h-72 w-72">
            <div className="wx-pulse absolute inset-0 rounded-full bg-yellow-200/50 blur-3xl" />
            <svg viewBox="0 0 200 200" className="wx-spin absolute inset-0 opacity-50">{Array.from({ length: 12 }, (_, i) => <rect key={i} x="97" y="6" width="6" height="44" rx="3" fill="#FEF3C7" transform={`rotate(${i * 30} 100 100)`} />)}</svg>
            <div className="absolute inset-[30%] rounded-full bg-gradient-to-br from-yellow-100 to-yellow-300 shadow-[0_0_60px_20px_rgba(253,224,71,.45)]" />
          </div>
        )}
        {!day && (k === "clear" || k === "partly") && <div className="absolute right-10 top-8 h-20 w-20 rounded-full bg-amber-50 shadow-[0_0_50px_12px_rgba(254,243,199,.35)]"><div className="absolute -right-2 -top-1 h-16 w-16 rounded-full bg-indigo-950/90" /></div>}
        {stars.map((s, i) => <span key={i} className="wx-star" style={{ left: `${s.left}%`, top: `${s.top}%`, width: s.s, height: s.s, ["--d" as string]: `${s.d}s`, ["--delay" as string]: `${s.delay}s` }} />)}
        {Array.from({ length: clouds }, (_, i) => (
          <div key={i} className="wx-cloud" style={{ top: `${4 + rnd(i + 3, k === "partly" ? 40 : 55)}%`, ["--d" as string]: `${60 + rnd(i + 5, 70)}s`, ["--delay" as string]: `-${rnd(i + 9, 90)}s`, opacity: dark ? 0.35 : 0.55 }}>
            <div className={cn("relative h-16 w-56 rounded-full blur-sm", dark ? "bg-slate-300" : "bg-white")}><div className={cn("absolute -top-8 left-12 h-20 w-24 rounded-full", dark ? "bg-slate-300" : "bg-white")} /><div className={cn("absolute -top-5 left-28 h-16 w-20 rounded-full", dark ? "bg-slate-300" : "bg-white")} /></div>
          </div>
        ))}
        {k === "fog" && [10, 32, 55, 75].map((t, i) => <div key={t} className="wx-fog bg-white/35" style={{ top: `${t}%`, height: 70 + i * 10, ["--d" as string]: `${22 + i * 7}s`, ["--delay" as string]: `-${i * 5}s` }} />)}
        {(dark || k === "fog") && <div className="absolute inset-0 bg-black/10" />}
      </div>
      {children}
      {/* Lớp trước các thẻ (không nhận chuột): mưa, tuyết, sương mỏng, chớp để hiệu ứng thấy rõ cả trên thẻ kính */}
      <div className="pointer-events-none absolute inset-0 z-10" aria-hidden>
        {drops.map((r, i) => <span key={i} className="wx-drop" style={{ left: `${r.left}%`, height: r.h, width: i % 3 ? 1.5 : 2, ["--d" as string]: `${r.d}s`, ["--delay" as string]: `${r.delay}s`, opacity: k === "drizzle" ? 0.45 : 0.7 }} />)}
        {flakes.map((f, i) => <span key={i} className="wx-flake" style={{ left: `${f.left}%`, width: f.s, height: f.s, ["--d" as string]: `${f.d}s`, ["--delay" as string]: `${f.delay}s`, ["--dx" as string]: `${(i % 2 ? 1 : -1) * 30}px` }} />)}
        {k === "fog" && [20, 62].map((t, i) => <div key={t} className="wx-fog bg-white/15" style={{ top: `${t}%`, height: 90, ["--d" as string]: `${26 + i * 9}s`, ["--delay" as string]: `-${i * 7}s` }} />)}
        {k === "storm" && <div className="wx-flash" />}
      </div>
    </div>
  );
}
