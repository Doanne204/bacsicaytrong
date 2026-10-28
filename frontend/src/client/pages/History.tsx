import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Bug, Leaf, ScanLine, Sparkles, X } from "lucide-react";
import { api, type HistoryItem } from "@/shared/lib/api";
import { cn, dayKey, dayLabel, fmtTime, pct, toDate } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";
import { Input } from "@/shared/ui/input";
import { EmptyState, Skeleton } from "@/shared/ui/misc";
import { PageHeader, Stars } from "@/shared/components/common";

export default function History() {
  const q = useQuery({ queryKey: ["history"], queryFn: () => api<HistoryItem[]>("/api/history") });
  const [day, setDay] = useState(""), [kind, setKind] = useState<"all" | "leaf" | "pest">("all");
  const groups = useMemo(() => {
    const items = (q.data || []).filter((it) => (!day || dayKey(toDate(it.created)) === day) && (kind === "all" || (kind === "pest") === (it.plant_id === "pest" || it.plant === "Sâu hại" || it.plant === "Thiên địch")));
    const g: Record<string, HistoryItem[]> = {};
    items.forEach((it) => { const k = dayKey(toDate(it.created)); (g[k] ||= []).push(it); });
    return Object.entries(g).sort((a, b) => (a[0] < b[0] ? 1 : -1));
  }, [q.data, day, kind]);
  return (
    <div className="animate-fade-up">
      <PageHeader title="Lịch sử tra cứu" text={q.data ? `${q.data.length} lượt tra cứu` : undefined} />
      <div className="mb-5 flex flex-wrap items-center gap-2">
        {([["all", "Tất cả"], ["leaf", "Bệnh lá"], ["pest", "Sâu hại"]] as const).map(([k, l]) => (
          <button key={k} type="button" onClick={() => setKind(k)} aria-pressed={kind === k} className={cn("h-9 rounded-full border bg-card px-4 text-sm font-semibold transition", kind === k ? "border-primary bg-primary text-primary-foreground" : "hover:border-primary")}>{l}</button>
        ))}
        <div className="ml-auto flex items-center gap-1"><Input type="date" value={day} onChange={(e) => setDay(e.target.value)} className="h-9 w-auto" aria-label="Lọc theo ngày" />{day && <Button variant="ghost" size="icon-sm" onClick={() => setDay("")} aria-label="Bỏ lọc"><X className="h-4 w-4" /></Button>}</div>
      </div>
      {q.isLoading ? <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-24" />)}</div>
        : !groups.length ? <EmptyState icon={ScanLine} title={q.data?.length ? "Không có lượt tra cứu nào khớp bộ lọc" : "Chưa có lượt tra cứu nào"} text="Chụp một chiếc lá hoặc con sâu để bắt đầu." action={<Button asChild><Link to="/scan"><ScanLine />Tra cứu ngay</Link></Button>} />
        : groups.map(([k, items]) => (
          <section key={k} className="mb-6">
            <h2 className="mb-2 text-sm font-bold text-primary">{dayLabel(toDate(items[0].created))}</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {items.map((it) => {
                const pest = it.plant === "Sâu hại" || it.plant === "Thiên địch", unknown = it.plant_id === "unknown" || it.plant_id === "background";
                return (
                  <Link key={it.id} to={`/diagnosis/${it.id}`} className="flex gap-3 rounded-2xl border bg-card p-3 transition hover:border-primary hover:shadow-soft">
                    {it.image_url ? <img src={it.image_url} alt="" loading="lazy" className="h-[72px] w-[72px] shrink-0 rounded-xl object-cover" /> : <span className="grid h-[72px] w-[72px] shrink-0 place-items-center rounded-xl bg-secondary text-primary">{pest ? <Bug /> : <Leaf />}</span>}
                    <div className="min-w-0 flex-1">
                      <b className="block truncate">{it.disease}</b>
                      <span className="block truncate text-sm text-muted-foreground">{it.plant}</span>
                      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                        <span>{fmtTime(toDate(it.created))}</span>
                        {!unknown && <b className="text-foreground">{pct(it.confidence)}</b>}
                        {it.source === "ai" ? <Badge variant="paddy"><Sparkles />AI</Badge> : it.source === "memory" ? <Badge variant="paddy"><Sparkles />Đã học</Badge> : null}
                        {it.stars ? <Stars value={it.stars} size="sm" /> : null}
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          </section>
        ))}
    </div>
  );
}
