import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Database, Leaf, Sparkles, Trash2 } from "lucide-react";
import { api, del } from "@/shared/lib/api";
import { ago, pct } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { EmptyState, Notice, Skeleton } from "@/shared/ui/misc";
import { ConfirmDialog } from "@/shared/components/common";
import type { Sample, Stats } from "../lib/types";

export default function Data({ stats }: { stats?: Stats }) {
  const list = useQuery({ queryKey: ["admin", "samples"], queryFn: () => api<Sample[]>("/api/admin/samples") });
  const [victim, setVictim] = useState<Sample | null>(null);
  return (
    <div className="space-y-5 animate-fade-up">
      <Notice icon={Database}>Ảnh AI đã phân tích được lưu trong thư mục <b>dataset_ai/</b>, chia theo lớp như PlantVillage. Xóa các mẫu AI dán nhãn sai trước khi huấn luyện lại (<code className="rounded bg-muted px-1">python train.py --data … --extra dataset_ai</code>).</Notice>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <section>
          <h2 className="mb-3 font-bold">Mẫu mới nhất</h2>
          {list.isLoading ? <div className="grid gap-3 sm:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}</div>
            : !list.data?.length ? <div className="rounded-2xl border bg-card"><EmptyState icon={Sparkles} title="Chưa có ảnh nào được AI lưu" /></div>
            : <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{list.data.map((s) => (
              <div key={s.id} className="flex gap-3 rounded-2xl border bg-card p-3">
                {s.image_url ? <img src={s.image_url} alt="" loading="lazy" className="h-16 w-16 rounded-xl object-cover" /> : <span className="grid h-16 w-16 place-items-center rounded-xl bg-secondary text-primary"><Leaf /></span>}
                <div className="min-w-0 flex-1"><b className="block truncate text-sm">{s.plant || ""}: {s.disease || ""}</b><p className="truncate text-xs text-muted-foreground">{s.class_name}</p><p className="text-xs text-muted-foreground"><b className="text-foreground">{pct(s.confidence)}</b> · {s.username || "?"}, {ago(s.created)}</p></div>
                <Button variant="ghost" size="icon-sm" aria-label="Xóa mẫu dán nhãn sai" onClick={() => setVictim(s)}><Trash2 className="h-4 w-4" /></Button>
              </div>
            ))}</div>}
        </section>
        <Card className="h-fit">
          <CardHeader><CardTitle>Số ảnh theo lớp</CardTitle></CardHeader>
          <CardContent>{stats?.classes.length ? <ul className="divide-y text-sm">{stats.classes.map((c) => <li key={c.class_name} className="flex justify-between gap-3 py-2"><span className="truncate">{c.class_name}</span><b className="tabular-nums">{c.n}</b></li>)}</ul> : <p className="text-sm text-muted-foreground">Chưa có lớp AI nào.</p>}</CardContent>
        </Card>
      </div>
      <ConfirmDialog open={!!victim} onOpenChange={(o) => !o && setVictim(null)} title="Xóa mẫu này khỏi bộ dữ liệu AI?" description={victim ? `${victim.class_name}, ${pct(victim.confidence)}` : ""} confirmText="Xóa" danger onConfirm={async () => { if (!victim) return; await del(`/api/admin/samples/${victim.id}`); toast.success("Đã xóa mẫu"); list.refetch(); }} />
    </div>
  );
}
