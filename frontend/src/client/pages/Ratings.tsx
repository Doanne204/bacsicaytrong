import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Leaf, Star } from "lucide-react";
import { api, send, type HistoryItem } from "@/shared/lib/api";
import { ago, pct } from "@/shared/lib/utils";
import { Avatar, EmptyState, Progress, Skeleton } from "@/shared/ui/misc";
import { PageHeader, Stars } from "@/shared/components/common";

interface Summary { avg: number; count: number; dist: Record<string, number>; items: { id: number; stars: number; comment: string; created: string; username: string; plant: string; disease: string; source: string }[]; pending: (HistoryItem & { image_url: string | null })[] }

export default function Ratings() {
  const q = useQuery({ queryKey: ["ratings"], queryFn: () => api<Summary>("/api/ratings") });
  if (q.isLoading || !q.data) return <div className="space-y-4"><Skeleton className="h-10 w-1/2" /><Skeleton className="h-40" /><Skeleton className="h-60" /></div>;
  const r = q.data, max = Math.max(1, ...Object.values(r.dist));
  const rate = async (id: number, stars: number) => {
    try { await send("/api/rating", { diagnosis_id: id, stars }); toast.success(`Đã chấm ${stars} sao`); q.refetch(); } catch (e) { toast.error((e as Error).message); }
  };
  return (
    <div className="animate-fade-up">
      <PageHeader title="Đánh giá" text="Người dùng chấm điểm kết quả tra cứu để hệ thống chính xác hơn." />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
        <aside className="space-y-5 lg:sticky lg:top-8 lg:self-start">
          <section className="grid grid-cols-[auto_1fr] items-center gap-6 rounded-3xl border bg-card p-6 shadow-soft">
            <div className="text-center"><div className="text-5xl font-extrabold leading-none">{r.count ? r.avg.toFixed(1).replace(".", ",") : "–"}</div><Stars value={Math.round(r.avg)} size="sm" className="mt-2" /><p className="mt-1 text-sm text-muted-foreground">{r.count} đánh giá</p></div>
            <div className="space-y-1.5">{[5, 4, 3, 2, 1].map((s) => <div key={s} className="grid grid-cols-[14px_1fr_32px] items-center gap-2 text-xs"><span>{s}</span><Progress value={(r.dist[s] / max) * 100} tone="paddy" className="h-2" /><span className="text-right text-muted-foreground">{r.dist[s]}</span></div>)}</div>
          </section>
          {r.pending.length > 0 && (
            <section>
              <h2 className="mb-2 font-bold">Kết quả bạn chưa chấm</h2>
              <div className="divide-y rounded-2xl border bg-card">
                {r.pending.map((it) => (
                  <div key={it.id} className="flex items-center gap-3 p-3">
                    {it.image_url ? <img src={it.image_url} alt="" className="h-12 w-12 rounded-xl object-cover" /> : <span className="grid h-12 w-12 place-items-center rounded-xl bg-secondary text-primary"><Leaf className="h-5 w-5" /></span>}
                    <div className="min-w-0 flex-1"><Link to={`/diagnosis/${it.id}`} className="block truncate text-sm font-bold hover:text-primary">{it.disease}</Link><span className="text-xs text-muted-foreground">{it.plant}, {pct(it.confidence)}</span></div>
                    <Stars value={0} size="sm" onChange={(s) => rate(it.id, s)} />
                  </div>
                ))}
              </div>
            </section>
          )}
        </aside>
        <section>
          <h2 className="mb-2 font-bold">Đánh giá gần đây</h2>
          {r.items.length ? (
            <div className="grid gap-3 md:grid-cols-2">
              {r.items.map((it) => (
                <article key={it.id} className="rounded-2xl border bg-card p-4">
                  <div className="flex items-center gap-2.5"><Avatar name={it.username} size="sm" /><b className="flex-1 truncate text-sm">{it.username}</b><Stars value={it.stars} size="sm" /></div>
                  {it.comment && <p className="mt-2 text-[15px]">{it.comment}</p>}
                  <p className="mt-2 text-xs text-muted-foreground">Tra cứu {it.plant}: {it.disease}{it.source === "ai" ? " (AI)" : ""} · {ago(it.created)}</p>
                </article>
              ))}
            </div>
          ) : <EmptyState icon={Star} title="Chưa có đánh giá nào" text="Hãy là người đầu tiên chấm điểm kết quả tra cứu." />}
        </section>
      </div>
    </div>
  );
}
