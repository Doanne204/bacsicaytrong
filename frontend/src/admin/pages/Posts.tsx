import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, ExternalLink, Leaf, ScanLine, Search, Trash2, X } from "lucide-react";
import { api, del, send, type Post } from "@/shared/lib/api";
import { ago, pct } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";
import { Textarea } from "@/shared/ui/input";
import { Avatar, EmptyState, Notice, Skeleton } from "@/shared/ui/misc";
import { ConfirmDialog } from "@/shared/components/common";
import { Segmented } from "../components/table";
import { Input } from "@/shared/ui/input";

type Status = "pending" | "rejected" | "approved" | "all";
const STATUS: Record<string, [string, "warning" | "success" | "destructive"]> = { pending: ["Chờ duyệt", "warning"], approved: ["Đã đăng", "success"], rejected: ["Bị từ chối", "destructive"] };
const VERDICT: Record<string, string> = { approve: "Duyệt", reject: "Từ chối", review: "Cần người xem" };

export default function Posts({ onChange }: { onChange: () => void }) {
  const [status, setStatus] = useState<Status>("pending"), [q, setQ] = useState("");
  const list = useQuery({ queryKey: ["admin", "posts", status, q], queryFn: () => api<Post[]>(`/api/admin/posts?status=${status}&q=${encodeURIComponent(q)}`) });
  const done = () => { list.refetch(); onChange(); };
  return (
    <div className="space-y-4 animate-fade-up">
      <div className="flex flex-wrap items-center gap-2">
        <Segmented value={status} onChange={setStatus} options={[["pending", "Chờ duyệt"], ["rejected", "Bị từ chối"], ["approved", "Đã đăng"], ["all", "Tất cả"]]} />
        <div className="relative ml-auto w-full sm:w-72"><Search className="pointer-events-none absolute left-3 top-3 h-5 w-5 text-muted-foreground" /><Input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm nội dung hoặc người đăng…" className="pl-10" /></div>
      </div>
      {list.isLoading ? <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">{[0, 1].map((i) => <Skeleton key={i} className="h-64" />)}</div>
        : !list.data?.length ? <div className="rounded-2xl border bg-card"><EmptyState icon={Check} title={q ? "Không có bài viết khớp từ khóa" : status === "pending" ? "Không có bài nào chờ duyệt" : "Không có bài viết"} /></div>
        : <div className="grid items-start gap-4 lg:grid-cols-2">{list.data.map((p) => <ModCard key={p.id} p={p} onDone={done} />)}</div>}
    </div>
  );
}

function ModCard({ p, onDone }: { p: Post; onDone: () => void }) {
  const [note, setNote] = useState(""), [busy, setBusy] = useState(""), [confirm, setConfirm] = useState(false);
  const [label, tone] = STATUS[p.status];
  const act = async (action: "approve" | "reject") => {
    setBusy(action);
    try { await send(`/api/admin/posts/${p.id}`, { action, note }); toast.success(action === "approve" ? "Đã duyệt và thông báo cho người đăng" : "Đã từ chối và gửi lý do cho người đăng"); onDone(); }
    catch (e) { toast.error((e as Error).message); } finally { setBusy(""); }
  };
  const d = p.diagnosis;
  return (
    <article className="rounded-2xl border bg-card p-4 shadow-soft">
      <header className="mb-3 flex items-center gap-3"><Avatar name={p.username} /><div className="min-w-0 flex-1 leading-tight"><b className="block truncate">{p.username}</b><time className="text-xs text-muted-foreground">{ago(p.created)}</time></div><Badge variant={tone}>{label}</Badge></header>
      {p.content && <p className="whitespace-pre-wrap break-words text-[15px]">{p.content}</p>}
      {p.image_url && <img src={p.image_url} alt="" loading="lazy" className="mt-3 max-h-72 w-full rounded-xl object-cover" />}
      {d && <div className="mt-3 flex items-center gap-3 rounded-xl bg-muted p-2.5">{d.image_url ? <img src={d.image_url} alt="" className="h-14 w-14 rounded-lg object-cover" /> : <span className="grid h-14 w-14 place-items-center rounded-lg bg-secondary text-primary"><Leaf /></span>}<span className="min-w-0 text-sm"><span className="inline-flex items-center gap-1 text-xs font-bold text-primary"><ScanLine className="h-3.5 w-3.5" />Kết quả tra cứu đính kèm</span><b className="block truncate">{d.disease}</b><span className="text-muted-foreground">{d.plant}, {pct(d.confidence)}{d.source === "ai" ? " (AI)" : ""}</span></span></div>}
      {p.shared && <div className="mt-3 rounded-xl border p-3 text-sm">{"deleted" in p.shared && p.shared.deleted ? <span className="text-muted-foreground">Bài viết gốc đã bị xóa.</span> : <><b>Chia sẻ lại bài của {(p.shared as Post).username}</b>{(p.shared as Post).content && <p className="clamp-3 mt-1 text-muted-foreground">{(p.shared as Post).content}</p>}</>}</div>}
      <Notice tone="warn" className="mt-3 border-l-4 border-paddy"><b>AI đề xuất: {VERDICT[p.ai_decision || ""] || "Chưa kiểm duyệt"}</b>{p.ai_reason && <p>{p.ai_reason}</p>}{p.feedback && <p className="text-muted-foreground">Phản hồi đã gửi người đăng: {p.feedback}</p>}</Notice>
      {p.status === "approved" && <p className="mt-2 text-xs text-muted-foreground">{p.likes} lượt thích · {p.comments} bình luận · {p.shares} lượt chia sẻ</p>}
      <div className="mt-3 space-y-2">
        {p.status !== "rejected" && <Textarea rows={2} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Lý do từ chối (gửi cho người đăng)" aria-label="Lý do từ chối" />}
        <div className="flex flex-wrap gap-2">
          {p.status !== "approved" && <Button loading={busy === "approve"} onClick={() => act("approve")}><Check />Duyệt đăng</Button>}
          {p.status !== "rejected" && <Button variant="outline" className="text-destructive" loading={busy === "reject"} onClick={() => act("reject")}><X />{p.status === "approved" ? "Gỡ bài" : "Từ chối"}</Button>}
          {p.status === "approved" && <Button asChild variant="ghost"><a href={`/p/${p.id}`} target="_blank" rel="noopener"><ExternalLink />Xem trong ứng dụng</a></Button>}
          <Button variant="ghost" className="ml-auto text-destructive hover:text-destructive" onClick={() => setConfirm(true)}><Trash2 />Xóa</Button>
        </div>
      </div>
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Xóa vĩnh viễn bài viết?" description="Lượt thích, bình luận của bài cũng bị xóa." confirmText="Xóa" danger onConfirm={async () => { await del(`/api/posts/${p.id}`); toast.success("Đã xóa bài viết"); onDone(); }} />
    </article>
  );
}
