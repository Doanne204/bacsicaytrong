import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ChevronRight, Heart, Leaf, Link2, MessageCircle, Repeat2, ScanLine, Share2, Trash2, AlertTriangle, Clock } from "lucide-react";
import { api, del, send, type DiagCard, type Post } from "@/shared/lib/api";
import { ago, cn, copyText, pct } from "@/shared/lib/utils";
import { useMe } from "@/shared/hooks/use-me";
import { Avatar, Notice } from "@/shared/ui/misc";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Textarea } from "@/shared/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/shared/ui/dialog";
import { ConfirmDialog } from "@/shared/components/common";

/** Thẻ kết quả tra cứu đính kèm bài viết; postId: bấm vào xem chi tiết. */
export function DiagCardView({ d, postId, className }: { d: DiagCard; postId?: number; className?: string }) {
  const unknown = d.plant_id === "unknown" || d.plant_id === "background";
  const inner = (
    <>
      {d.image_url ? <img src={d.image_url} alt="Ảnh đã tra cứu" loading="lazy" className="h-[76px] w-[76px] shrink-0 rounded-xl object-cover" /> : <span className="grid h-[76px] w-[76px] shrink-0 place-items-center rounded-xl bg-secondary text-primary"><Leaf /></span>}
      <span className="min-w-0 flex-1">
        <span className="inline-flex items-center gap-1 text-xs font-bold text-primary"><ScanLine className="h-3.5 w-3.5" />Kết quả tra cứu</span>
        <b className="block truncate">{d.disease}</b>
        <span className="block text-sm text-muted-foreground">{d.plant}{unknown ? "" : `, độ tin cậy ${pct(d.confidence)}`}</span>
        {postId && <span className="text-sm font-semibold text-primary">Xem chi tiết</span>}
      </span>
      {postId && <ChevronRight className="text-muted-foreground" />}
    </>
  );
  const cls = cn("mt-3 flex items-center gap-3 rounded-2xl border bg-card p-2.5 text-left", postId && "transition hover:border-primary", className);
  return postId ? <Link to={`/kq/${postId}`} className={cls}>{inner}</Link> : <div className={cls}>{inner}</div>;
}

function PostBody({ p, clamp }: { p: Post; clamp?: boolean }) {
  const long = clamp && (p.content || "").length > 280;
  return (
    <>
      {p.content && <p className={cn("whitespace-pre-wrap break-words leading-relaxed", long && "clamp-6")}>{p.content}</p>}
      {long && <Link to={`/p/${p.id}`} className="text-sm font-semibold text-primary">Xem thêm</Link>}
      {p.image_url && <img src={p.image_url} alt={`Ảnh trong bài viết của ${p.username}`} loading="lazy" className="mt-3 max-h-[520px] w-full rounded-2xl bg-secondary object-cover" />}
      {p.diagnosis && <DiagCardView d={p.diagnosis} postId={p.id} />}
    </>
  );
}

export function PostCard({ p, clamp = true, onChange }: { p: Post; clamp?: boolean; onChange?: () => void }) {
  const { me } = useMe();
  const nav = useNavigate();
  const [liked, setLiked] = useState(p.liked), [likes, setLikes] = useState(p.likes), [shares, setShares] = useState(p.shares);
  const [share, setShare] = useState(false), [confirm, setConfirm] = useState(false);
  const status = p.is_mine && p.status !== "approved" ? (p.status === "pending" ? <Badge variant="warning"><Clock />Chờ duyệt</Badge> : <Badge variant="destructive">Không được đăng</Badge>) : null;
  const o = p.shared;
  const like = async () => {
    setLiked(!liked); setLikes(likes + (liked ? -1 : 1));
    try { const r = await send<{ liked: boolean; likes: number }>(`/api/posts/${p.id}/like`, {}); setLiked(r.liked); setLikes(r.likes); }
    catch (e) { setLiked(liked); setLikes(likes); toast.error((e as Error).message); }
  };
  return (
    <article className="border-b py-5 first:pt-0 last:border-0" data-id={p.id}>
      <header className="mb-3 flex items-center gap-3">
        <Avatar name={p.username} />
        <div className="min-w-0 flex-1 leading-tight"><b className="block truncate">{p.username}</b><time className="text-xs text-muted-foreground">{o ? "Đã chia sẻ một bài viết, " : ""}{ago(p.created)}</time></div>
        {status}
        {(p.is_mine || me?.role === "admin") && <Button variant="ghost" size="icon-sm" aria-label="Xóa bài viết" onClick={() => setConfirm(true)}><Trash2 className="h-4 w-4" /></Button>}
      </header>
      <PostBody p={p} clamp={clamp} />
      {o && (o.deleted ? <div className="mt-3 rounded-2xl border p-4 text-sm text-muted-foreground">Bài viết gốc đã bị xóa.</div> : (
        <div className="mt-3 rounded-2xl border p-4">
          <Link to={`/p/${o.id}`} className="mb-2 flex items-center gap-2"><Avatar name={o.username} size="sm" /><span className="leading-tight"><b className="block text-sm">{o.username}</b><time className="text-xs text-muted-foreground">{ago(o.created)}</time></span></Link>
          <PostBody p={o} clamp />
        </div>
      ))}
      {p.is_mine && p.status === "rejected" && p.feedback && <Notice tone="danger" icon={AlertTriangle} className="mt-3"><b>Lý do</b><p>{p.feedback}</p></Notice>}
      {p.is_mine && p.status === "pending" && <Notice tone="warn" icon={Clock} className="mt-3">Bài viết sẽ hiện trên trang chủ sau khi quản trị viên duyệt.</Notice>}
      {p.status === "approved" && (
        <>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground empty:hidden">
            {likes > 0 && <span className="inline-flex items-center gap-1"><Heart className="h-3.5 w-3.5 fill-destructive text-destructive" />{likes}</span>}
            {p.comments > 0 && <Link to={`/p/${p.id}`} className="hover:underline">{p.comments} bình luận</Link>}
            {shares > 0 && <span>{shares} lượt chia sẻ</span>}
          </div>
          <div className="mt-2 grid grid-cols-3 border-t pt-1">
            <Button variant="ghost" className={cn("text-muted-foreground", liked && "text-destructive hover:text-destructive")} onClick={like} aria-pressed={liked}><Heart className={cn(liked && "fill-current")} />Thích</Button>
            <Button variant="ghost" className="text-muted-foreground" onClick={() => nav(`/p/${p.id}`, { state: { focusComment: true } })}><MessageCircle />Bình luận</Button>
            <Button variant="ghost" className="text-muted-foreground" onClick={() => setShare(true)}><Share2 />Chia sẻ</Button>
          </div>
        </>
      )}
      <ShareDialog open={share} onOpenChange={setShare} post={p} onShared={(n) => { setShares(n); onChange?.(); }} />
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Xóa bài viết này?" description="Bài viết cùng lượt thích, bình luận sẽ bị xóa." confirmText="Xóa" danger
        onConfirm={async () => { try { await del(`/api/posts/${p.id}`); toast.success("Đã xóa bài viết"); onChange?.(); } catch (e) { toast.error((e as Error).message); } }} />
    </article>
  );
}

export function ShareDialog({ open, onOpenChange, post, onShared }: { open: boolean; onOpenChange: (o: boolean) => void; post: Post; onShared?: (shares: number) => void }) {
  const qc = useQueryClient();
  const [text, setText] = useState(""), [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const url = `${location.origin}/p/${post.id}`;
  const counted = async () => { try { const r = await send<{ shares: number }>(`/api/posts/${post.id}/share`, { kind: "link" }); onShared?.(r.shares); } catch { /* chỉ là số đếm */ } };
  const repost = async () => {
    setBusy(true); setErr("");
    try {
      const r = await send<{ status: string; message: string; post: Post }>(`/api/posts/${post.id}/share`, { kind: "repost", content: text.trim() });
      if (r.status === "rejected") { setErr(r.post.feedback || r.message); return; }
      toast.success(r.status === "approved" ? "Đã chia sẻ lên trang của bạn" : "Bài chia sẻ đang chờ duyệt");
      onOpenChange(false); setText(""); qc.invalidateQueries({ queryKey: ["posts"] }); onShared?.(post.shares + 1);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const native = async () => {
    if (navigator.share) { try { await navigator.share({ title: "Bác sĩ cây trồng", text: post.content?.slice(0, 100), url }); counted(); onOpenChange(false); } catch { /* người dùng hủy */ } }
    else { await copyText(url); toast.success("Đã sao chép liên kết"); counted(); onOpenChange(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Chia sẻ bài viết</DialogTitle><DialogDescription>Người nhận liên kết cần đăng nhập để xem bài viết.</DialogDescription></DialogHeader>
        <div className="space-y-2">
          <label htmlFor="shtext" className="text-sm font-semibold">Viết vài lời (không bắt buộc)</label>
          <Textarea id="shtext" rows={3} maxLength={2000} placeholder="Bà con xem bài này nhé…" value={text} onChange={(e) => setText(e.target.value)} />
          {err && <p className="text-sm font-medium text-destructive" role="alert">{err}</p>}
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <Button onClick={repost} loading={busy}><Repeat2 />Chia sẻ lên trang của tôi</Button>
          <Button variant="outline" onClick={native}><Link2 />{typeof navigator.share === "function" ? "Gửi qua ứng dụng khác" : "Sao chép liên kết"}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export async function fetchPosts(mine: boolean) {
  return api<Post[]>("/api/posts" + (mine ? "?scope=mine" : ""));
}
