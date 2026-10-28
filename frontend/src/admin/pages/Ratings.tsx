import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Leaf, Star, Trash2 } from "lucide-react";
import { api, del } from "@/shared/lib/api";
import { ago } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Avatar, EmptyState } from "@/shared/ui/misc";
import { ConfirmDialog, Stars } from "@/shared/components/common";
import { DataTable, Segmented } from "../components/table";
import type { AdminRating } from "../lib/types";

export default function Ratings() {
  const [f, setF] = useState<"all" | "5" | "4" | "3" | "2" | "1">("all"), [victim, setVictim] = useState<AdminRating | null>(null);
  const list = useQuery({ queryKey: ["admin", "ratings", f], queryFn: () => api<AdminRating[]>("/api/admin/ratings" + (f === "all" ? "" : `?stars=${f}`)) });
  const diag = (r: AdminRating) => `${r.plant || "đã xóa"}${r.disease ? `: ${r.disease}` : ""}${r.source === "ai" ? " (AI)" : ""}`;
  return (
    <div className="animate-fade-up">
      <DataTable rows={list.data || []} loading={list.isLoading} keyOf={(r) => r.id}
        toolbar={<Segmented value={f} onChange={setF} options={[["all", "Tất cả"], ["5", "5 sao"], ["4", "4 sao"], ["3", "3 sao"], ["2", "2 sao"], ["1", "1 sao"]]} />}
        empty={<EmptyState icon={Star} title="Không có đánh giá" />}
        renderCard={(r) => (
          <div className="flex gap-3 rounded-2xl border bg-card p-3">
            {r.image_url ? <img src={r.image_url} alt="" className="h-14 w-14 rounded-xl object-cover" /> : <span className="grid h-14 w-14 place-items-center rounded-xl bg-secondary text-primary"><Leaf /></span>}
            <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><b className="text-sm">{r.username}</b><Stars value={r.stars} size="sm" /><small className="text-muted-foreground">{ago(r.created)}</small></div>{r.comment && <p className="mt-1 text-[15px]">{r.comment}</p>}<p className="text-xs text-muted-foreground">Tra cứu {diag(r)}</p></div>
            <Button variant="ghost" size="icon-sm" aria-label="Xóa" onClick={() => setVictim(r)}><Trash2 className="h-4 w-4" /></Button>
          </div>
        )}
        columns={[
          { key: "img", header: "", cell: (r) => (r.image_url ? <img src={r.image_url} alt="" className="h-12 w-12 rounded-lg object-cover" /> : <span className="grid h-12 w-12 place-items-center rounded-lg bg-secondary text-primary"><Leaf className="h-5 w-5" /></span>), className: "w-16" },
          { key: "user", header: "Người dùng", cell: (r) => <span className="flex items-center gap-2"><Avatar name={r.username} size="sm" /><b>{r.username}</b></span>, sort: (r) => r.username },
          { key: "stars", header: "Sao", cell: (r) => <Stars value={r.stars} size="sm" />, sort: (r) => r.stars },
          { key: "comment", header: "Nhận xét / kết quả", cell: (r) => <>{r.comment && <p>{r.comment}</p>}<span className="text-xs text-muted-foreground">Tra cứu {diag(r)}</span></>, className: "min-w-[240px]" },
          { key: "when", header: "Lúc", cell: (r) => <span className="text-muted-foreground">{ago(r.created)}</span>, sort: (r) => r.created, hide: "md" },
          { key: "act", header: "", cell: (r) => <Button variant="ghost" size="icon-sm" aria-label="Xóa" onClick={() => setVictim(r)}><Trash2 className="h-4 w-4" /></Button>, className: "text-right" },
        ]} />
      <ConfirmDialog open={!!victim} onOpenChange={(o) => !o && setVictim(null)} title="Xóa đánh giá này?" confirmText="Xóa" danger onConfirm={async () => { if (!victim) return; await del(`/api/admin/ratings/${victim.id}`); toast.success("Đã xóa đánh giá"); list.refetch(); }} />
    </div>
  );
}
