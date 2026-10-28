import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { MessageSquare, Trash2 } from "lucide-react";
import { api, del } from "@/shared/lib/api";
import { ago } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";
import { Avatar, EmptyState } from "@/shared/ui/misc";
import { ConfirmDialog } from "@/shared/components/common";
import { DataTable, Segmented } from "../components/table";
import type { AdminComment } from "../lib/types";

export default function Comments({ onChange }: { onChange: () => void }) {
  const [f, setF] = useState<"all" | "flagged">("all"), [q, setQ] = useState(""), [victim, setVictim] = useState<AdminComment | null>(null);
  const list = useQuery({ queryKey: ["admin", "comments", f, q], queryFn: () => api<AdminComment[]>(`/api/admin/comments?flagged=${f === "flagged" ? 1 : 0}&q=${encodeURIComponent(q)}`) });
  const remove = async () => { if (!victim) return; await del(`/api/comments/${victim.id}`); toast.success("Đã xóa bình luận"); list.refetch(); onChange(); };
  const card = (c: AdminComment) => (
    <div className="flex gap-3 rounded-2xl border bg-card p-3">
      <Avatar name={c.username} size="sm" />
      <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2 text-sm"><b>{c.username}</b><small className="text-muted-foreground">{ago(c.created)}</small>{c.ai_decision !== "approve" && <Badge variant="warning">AI chưa duyệt</Badge>}</div><p className="mt-1 whitespace-pre-wrap text-[15px]">{c.content}</p><a href={`/p/${c.post_id}`} target="_blank" rel="noopener" className="mt-1 block truncate text-xs text-muted-foreground hover:text-primary">Trong bài: {c.post_excerpt || "(bài chỉ có ảnh)"}</a></div>
      <Button variant="ghost" size="icon-sm" aria-label="Xóa" onClick={() => setVictim(c)}><Trash2 className="h-4 w-4" /></Button>
    </div>
  );
  return (
    <div className="animate-fade-up">
      <DataTable rows={list.data || []} loading={list.isLoading} keyOf={(c) => c.id} search={q} onSearch={setQ} searchPlaceholder="Tìm nội dung hoặc người viết…" renderCard={card}
        toolbar={<Segmented value={f} onChange={setF} options={[["all", "Tất cả"], ["flagged", "AI chưa duyệt"]]} />}
        empty={<EmptyState icon={MessageSquare} title={f === "flagged" ? "Không có bình luận nào cần xem lại" : "Không có bình luận"} />}
        columns={[
          { key: "user", header: "Người viết", cell: (c) => <span className="flex items-center gap-2"><Avatar name={c.username} size="sm" /><b>{c.username}</b></span>, sort: (c) => c.username },
          { key: "content", header: "Nội dung", cell: (c) => <><p className="whitespace-pre-wrap">{c.content}</p><a href={`/p/${c.post_id}`} target="_blank" rel="noopener" className="text-xs text-muted-foreground hover:text-primary">Trong bài: {c.post_excerpt || "(bài chỉ có ảnh)"}</a></>, className: "min-w-[280px]" },
          { key: "ai", header: "AI", cell: (c) => (c.ai_decision === "approve" ? <Badge variant="success">Đã duyệt</Badge> : <Badge variant="warning">Chưa duyệt</Badge>), sort: (c) => c.ai_decision || "", hide: "sm" },
          { key: "when", header: "Lúc", cell: (c) => <span className="text-muted-foreground">{ago(c.created)}</span>, sort: (c) => c.created, hide: "md" },
          { key: "act", header: "", cell: (c) => <Button variant="ghost" size="icon-sm" aria-label="Xóa" onClick={() => setVictim(c)}><Trash2 className="h-4 w-4" /></Button>, className: "text-right" },
        ]} />
      <ConfirmDialog open={!!victim} onOpenChange={(o) => !o && setVictim(null)} title="Xóa bình luận này?" description={victim?.content} confirmText="Xóa" danger onConfirm={remove} />
    </div>
  );
}
