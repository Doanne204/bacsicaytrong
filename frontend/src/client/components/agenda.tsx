import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { CalendarDays, CheckCircle2, ChevronLeft, ChevronRight, Repeat } from "lucide-react";
import { api, LOG_KINDS, type Agenda, type AgendaTask, type DueReminder } from "@/shared/lib/api";
import { cn, dayKey, fmtTime, toDate } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";
import { Skeleton } from "@/shared/ui/misc";
import { KIND_ICON } from "./journal";

const WEEK = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
const WEEKDAY = ["Chủ nhật", "Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy"];

/** Lịch chăm sóc: lịch tháng có chấm báo ngày có việc, bấm một ngày để xem việc cần làm và việc đã làm ngày đó.
 *  Ngày hôm nay kèm cả việc quá hạn. Việc lặp lại hiện trước các lần sắp tới (chỉ để xem, đến lượt mới đánh dấu được). */
export function AgendaCalendar({ overdue, onDone }: { overdue: DueReminder[]; onDone: (r: DueReminder) => void }) {
  const today = dayKey(new Date());
  const [month, setMonth] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const [day, setDay] = useState(today);
  // Lưới 6 tuần bắt đầu từ thứ hai, tải lịch việc của cả lưới (tối đa 42 ngày)
  const first = new Date(month); first.setDate(1 - ((month.getDay() + 6) % 7));
  const days = Array.from({ length: 42 }, (_, i) => { const d = new Date(first); d.setDate(first.getDate() + i); return d; });
  const end = new Date(days[41]); end.setHours(23, 59, 59);
  const q = useQuery({
    queryKey: ["agenda", dayKey(first)],
    queryFn: () => api<Agenda>(`/api/agenda?from=${encodeURIComponent(first.toISOString())}&to=${encodeURIComponent(end.toISOString())}`),
    placeholderData: keepPreviousData,
  });
  const byDay = useMemo(() => {
    const m: Record<string, { tasks: AgendaTask[]; logs: Agenda["logs"] }> = {};
    const at = (k: string) => (m[k] ||= { tasks: [], logs: [] });
    for (const t of q.data?.tasks || []) at(dayKey(toDate(t.due))).tasks.push(t);
    for (const l of q.data?.logs || []) at(dayKey(toDate(l.at))).logs.push(l);
    return m;
  }, [q.data]);
  const sel = byDay[day] || { tasks: [], logs: [] };
  const late = day === today ? overdue.filter((r) => r.overdue && dayKey(toDate(r.due)) !== today) : [];
  const selDate = new Date(day + "T00:00:00");
  const go = (n: number) => setMonth(new Date(month.getFullYear(), month.getMonth() + n, 1));
  const label = (t: { name: string | null; plant: string; disease: string }) => t.name || `${t.plant}: ${t.disease}`;
  return (
    <section className="mb-6 grid gap-4 rounded-2xl border bg-card p-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="flex items-center gap-2 whitespace-nowrap font-bold"><CalendarDays className="h-5 w-5 text-primary" />Lịch chăm sóc</h2>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="icon-sm" aria-label="Tháng trước" onClick={() => go(-1)}><ChevronLeft /></Button>
            <span className="whitespace-nowrap text-center text-sm font-semibold sm:min-w-[6.5rem]"><span className="hidden sm:inline">Tháng </span>{month.getMonth() + 1}/{month.getFullYear()}</span>
            <Button variant="ghost" size="icon-sm" aria-label="Tháng sau" onClick={() => go(1)}><ChevronRight /></Button>
          </div>
        </div>
        <div className="grid grid-cols-7 text-center text-[11px] font-semibold text-muted-foreground">{WEEK.map((w) => <span key={w} className="py-1">{w}</span>)}</div>
        <div className="grid grid-cols-7 gap-0.5" role="grid" aria-label="Chọn ngày">
          {days.map((d) => {
            const k = dayKey(d), info = byDay[k], out = d.getMonth() !== month.getMonth();
            const lateToday = k === today && overdue.some((r) => r.overdue);
            const pending = !!info?.tasks.length || lateToday, late2 = lateToday || !!info?.tasks.some((t) => t.overdue);
            return (
              <button key={k} type="button" onClick={() => { setDay(k); if (out) setMonth(new Date(d.getFullYear(), d.getMonth(), 1)); }} aria-pressed={day === k}
                aria-label={`${d.getDate()}/${d.getMonth() + 1}${info ? `: ${info.tasks.length} việc cần làm, ${info.logs.length} việc đã làm` : ""}`}
                className={cn("relative flex h-10 flex-col items-center justify-center rounded-lg text-sm transition", out && "text-muted-foreground/50",
                  day === k ? "bg-primary font-bold text-primary-foreground" : k === today ? "font-bold text-primary ring-1 ring-primary" : "hover:bg-secondary")}>
                {d.getDate()}
                <span className="absolute bottom-1 flex gap-0.5">
                  {pending && <span className={cn("h-1.5 w-1.5 rounded-full", late2 ? "bg-destructive" : day === k ? "bg-primary-foreground" : "bg-paddy")} />}
                  {!!info?.logs.length && <span className={cn("h-1.5 w-1.5 rounded-full", day === k ? "bg-primary-foreground/70" : "bg-primary")} />}
                </span>
              </button>
            );
          })}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-paddy" />Việc cần làm</span>
          <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-destructive" />Quá hạn</span>
          <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-primary" />Đã làm</span>
          {day !== today && <button type="button" className="ml-auto font-semibold text-primary hover:underline" onClick={() => { setDay(today); const d = new Date(); setMonth(new Date(d.getFullYear(), d.getMonth(), 1)); }}>Hôm nay</button>}
        </div>
      </div>
      <div className="min-w-0">
        <h3 className="mb-2 font-bold">{day === today ? "Hôm nay, " : ""}{WEEKDAY[selDate.getDay()]} {selDate.getDate()}/{selDate.getMonth() + 1}</h3>
        {q.isLoading ? <Skeleton className="h-24" /> : (
          <>
            {!late.length && !sel.tasks.length && !sel.logs.length && <p className="rounded-xl bg-secondary/50 p-4 text-sm text-muted-foreground">Không có việc nào trong ngày này.</p>}
            {(!!late.length || !!sel.tasks.length) && (
              <ul className="mb-3 divide-y rounded-xl border">
                {[...late.map((r) => ({ ...r, projected: false })), ...sel.tasks].map((t) => (
                  <li key={`${t.id}-${t.due}`} className="flex items-center gap-3 p-2.5 text-sm">
                    {t.projected ? <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full border-2 border-dashed text-muted-foreground"><Repeat className="h-3.5 w-3.5" /></span>
                      : <button type="button" onClick={() => onDone(t)} className="grid h-7 w-7 shrink-0 place-items-center rounded-full border-2 border-primary text-primary transition hover:bg-primary hover:text-primary-foreground" aria-label={`Đánh dấu đã làm: ${t.content}`}><CheckCircle2 className="h-4 w-4" /></button>}
                    <span className="min-w-0 flex-1"><b className="block">{t.content}</b><Link to={`/journal/${t.treatment_id}`} className="text-xs text-muted-foreground hover:text-primary">{label(t)}</Link></span>
                    <span className="shrink-0 text-right text-xs">
                      {t.overdue ? <Badge variant="destructive">{dayKey(toDate(t.due)) === today ? "Đến hạn" : `Quá hạn từ ${toDate(t.due).getDate()}/${toDate(t.due).getMonth() + 1}`}</Badge>
                        : t.projected ? <Badge variant="muted">Lặp {t.repeat_days} ngày</Badge> : <span className="font-semibold text-muted-foreground">{fmtTime(toDate(t.due))}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {!!sel.logs.length && (
              <>
                <p className="mb-1.5 text-xs font-semibold text-muted-foreground">Đã làm</p>
                <ul className="divide-y rounded-xl border bg-secondary/30">
                  {sel.logs.map((l) => { const Icon = KIND_ICON[l.kind] || CheckCircle2; return (
                    <li key={l.id} className="flex items-center gap-3 p-2.5 text-sm">
                      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-primary/10 text-primary"><Icon className="h-3.5 w-3.5" /></span>
                      <span className="min-w-0 flex-1"><span className="block">{l.content || LOG_KINDS[l.kind]}</span><Link to={`/journal/${l.treatment_id}`} className="text-xs text-muted-foreground hover:text-primary">{label(l)}</Link></span>
                      <span className="shrink-0 text-xs text-muted-foreground">{fmtTime(toDate(l.at))}</span>
                    </li>
                  ); })}
                </ul>
              </>
            )}
          </>
        )}
      </div>
    </section>
  );
}
