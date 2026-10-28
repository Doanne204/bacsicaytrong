import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, MessageCircle, Send } from "lucide-react";
import { api, del, send, ApiError, type Comment, type Post } from "@/shared/lib/api";
import { ago } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Avatar, EmptyState, Notice } from "@/shared/ui/misc";
import { PostCard } from "../components/posts";
import { PageSkeleton } from "../layout/PageSkeleton";

export default function PostView() {
  const { id } = useParams();
  const nav = useNavigate();
  const loc = useLocation();
  const q = useQuery({ queryKey: ["post", id], queryFn: () => api<{ post: Post; comments: Comment[] }>(`/api/posts/${id}`) });
  const [comments, setComments] = useState<Comment[]>([]), [text, setText] = useState(""), [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const ta = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { if (q.data) setComments(q.data.comments); }, [q.data]);
  useEffect(() => { if ((loc.state as { focusComment?: boolean })?.focusComment) ta.current?.focus(); }, [loc.state]);
  if (q.isLoading) return <PageSkeleton />;
  if (!q.data) return <Notice tone="danger">{(q.error as Error)?.message || "Không tìm thấy bài viết"}</Notice>;
  const p = q.data.post, canComment = p.status === "approved";
  const submit = async () => {
    const content = text.trim(); if (!content || busy) return;
    setBusy(true); setErr("");
    try { const r = await send<{ comment: Comment }>(`/api/posts/${p.id}/comments`, { content }); setComments([...comments, r.comment]); setText(""); if (ta.current) ta.current.style.height = "auto"; }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Không gửi được bình luận"); } finally { setBusy(false); }
  };
  const remove = async (c: Comment) => {
    try { await del(`/api/comments/${c.id}`); setComments(comments.filter((x) => x.id !== c.id)); } catch (e) { toast.error((e as Error).message); }
  };
  return (
    <div className="mx-auto flex min-h-[calc(100dvh-3.5rem)] max-w-6xl flex-col px-4 pt-4 lg:min-h-0 lg:px-8 lg:pt-8">
      <Link to="/home" className="mb-3 inline-flex items-center gap-1 text-sm font-semibold text-muted-foreground hover:text-primary"><ArrowLeft className="h-4 w-4" />Trang chủ</Link>
      <div className="grid flex-1 grid-cols-1 gap-8 lg:grid-cols-[1.2fr_1fr]">
        <div className="[&>article]:border-0 [&>article]:pt-0"><PostCard p={p} clamp={false} onChange={() => nav("/home")} /></div>
        <section className="flex flex-col">
          <h2 className="mb-2 font-bold">Bình luận ({comments.length})</h2>
          <div className="flex-1 space-y-2">
            {comments.length ? comments.map((c) => (
              <div key={c.id} className="flex gap-2.5">
                <Avatar name={c.username} size="sm" />
                <div className="min-w-0 flex-1 rounded-2xl border bg-card px-3 py-2"><b className="text-sm">{c.username}</b><p className="whitespace-pre-wrap break-words text-[15px]">{c.content}</p><small className="text-muted-foreground">{ago(c.created)}{c.can_delete && <button type="button" onClick={() => remove(c)} className="ml-3 font-semibold text-destructive">Xóa</button>}</small></div>
              </div>
            )) : <EmptyState icon={MessageCircle} title="Chưa có bình luận" text={canComment ? "Hãy là người đầu tiên chia sẻ ý kiến." : "Bài viết chưa được duyệt nên chưa bình luận được."} className="py-6" />}
          </div>
          {canComment && (
            <form onSubmit={(e) => { e.preventDefault(); submit(); }} className="sticky bottom-0 -mx-4 mt-3 border-t bg-background px-4 pb-[calc(0.75rem+var(--safe-b))] pt-3 lg:static lg:mx-0 lg:px-0 lg:pb-0">
              {err && <p className="mb-2 text-sm font-medium text-destructive" role="alert">{err}</p>}
              <div className="flex items-end gap-2">
                <textarea ref={ta} rows={1} maxLength={1000} value={text} onChange={(e) => { setText(e.target.value); e.target.style.height = "auto"; e.target.style.height = Math.min(e.target.scrollHeight, 140) + "px"; }}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); } }}
                  placeholder="Viết bình luận…" aria-label="Bình luận" className="max-h-[140px] min-h-[46px] flex-1 resize-none rounded-3xl border bg-card px-4 py-3 leading-relaxed focus:border-primary focus:outline-none" />
                <Button type="submit" size="icon" className="rounded-full" disabled={!text.trim()} loading={busy} aria-label="Gửi bình luận"><Send /></Button>
              </div>
            </form>
          )}
        </section>
      </div>
    </div>
  );
}
