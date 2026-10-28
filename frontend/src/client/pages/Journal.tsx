import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlarmClock, Bug, CheckCircle2, Leaf, NotebookPen, Plus } from "lucide-react";
import { api, send, type DueReminder, type Treatment } from "@/shared/lib/api";
import { ago } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";
import { EmptyState, Skeleton } from "@/shared/ui/misc";
import { Tabs, TabsList, TabsTrigger } from "@/shared/ui/tabs";
import { PageHeader } from "@/shared/components/common";
import { TrackDialog, dueLabel } from "../components/journal";
import { AgendaCalendar } from "../components/agenda";

export default function Journal() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["treatments"], queryFn: () => api<Treatment[]>("/api/treatments") });
  const due = useQuery({ queryKey: ["reminders"], queryFn: () => api<DueReminder[]>("/api/reminders") });
  const [tab, setTab] = useState<"active" | "done">("active"), [open, setOpen] = useState(false);
  const items = (q.data || []).filter((t) => t.status === tab);
  const refresh = () => ["treatments", "reminders", "agenda", "me"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  const markDone = async (r: DueReminder) => {
    try { await send(`/api/reminders/${r.id}`, { done: 1 }, "PUT"); toast.success(r.repeat_days ? `Đã ghi vào nhật ký, hẹn lại sau ${r.repeat_days} ngày` : "Đã ghi vào nhật ký"); refresh(); }
    catch (e) { toast.error((e as Error).message); }
  };
  return (
    <div className="animate-fade-up">
      <PageHeader title="Nhật ký điều trị" text="Ghi lại việc đã làm cho từng cây bệnh và đặt lịch nhắc phun, kiểm tra." action={<Button onClick={() => setOpen(true)}><Plus />Nhật ký mới</Button>} />
      {!!q.data?.some((t) => t.status === "active") && <AgendaCalendar overdue={due.data || []} onDone={markDone} />}
      <Tabs value={tab} onValueChange={(v) => setTab(v as "active")} className="mb-4"><TabsList><TabsTrigger value="active">Đang theo dõi</TabsTrigger><TabsTrigger value="done">Đã xong</TabsTrigger></TabsList></Tabs>
      {q.isLoading ? <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-28" />)}</div>
        : !items.length ? <EmptyState icon={NotebookPen} title={tab === "active" ? "Chưa có nhật ký nào đang theo dõi" : "Chưa có nhật ký nào đã xong"} text="Mở nhật ký từ một kết quả tra cứu (nút “Theo dõi điều trị”) hoặc tạo mới ở đây." action={tab === "active" && <Button variant="outline" onClick={() => setOpen(true)}><Plus />Nhật ký mới</Button>} />
        : <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((t) => {
            const pest = t.plant === "Sâu hại" || t.plant === "Thiên địch";
            return (
              <Link key={t.id} to={`/journal/${t.id}`} className="flex gap-3 rounded-2xl border bg-card p-3 transition hover:border-primary hover:shadow-soft">
                {t.diagnosis?.image_url ? <img src={t.diagnosis.image_url} alt="" loading="lazy" className="h-[84px] w-[84px] shrink-0 rounded-xl object-cover" /> : <span className="grid h-[84px] w-[84px] shrink-0 place-items-center rounded-xl bg-secondary text-primary">{pest ? <Bug /> : <Leaf />}</span>}
                <div className="min-w-0 flex-1">
                  <b className="block truncate">{t.name || t.disease}</b>
                  <span className="block truncate text-sm text-muted-foreground">{t.name ? `${t.plant}: ${t.disease}` : t.plant}</span>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                    {t.overdue ? <Badge variant="destructive"><AlarmClock />{t.overdue} việc đến hạn</Badge> : t.next ? <Badge variant="muted"><AlarmClock />{dueLabel(t.next.due)}</Badge> : t.status === "active" ? <Badge variant="muted">Chưa đặt nhắc</Badge> : <Badge variant="success"><CheckCircle2 />Đã xong</Badge>}
                    <span>{t.logs} ghi chép{t.last_log ? `, ${ago(t.last_log)}` : ""}</span>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>}
      <TrackDialog open={open} onOpenChange={setOpen} />
    </div>
  );
}
