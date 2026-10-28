import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, Clock, KeyRound, Pencil, Power, RefreshCcw, Trash2 } from "lucide-react";
import { api, del, send, ApiError } from "@/shared/lib/api";
import { ago, whenSec } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";
import { Input } from "@/shared/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";
import { EmptyState, Field, Skeleton, Switch } from "@/shared/ui/misc";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/shared/ui/dialog";
import { ConfirmDialog } from "@/shared/components/common";
import type { AdminKey, KeysResponse } from "../lib/types";

export default function Keys() {
  const q = useQuery({ queryKey: ["admin", "keys"], queryFn: () => api<KeysResponse>("/api/admin/keys") });
  const [label, setLabel] = useState(""), [key, setKey] = useState(""), [err, setErr] = useState<Record<string, string>>({}), [busy, setBusy] = useState("");
  const [models, setModels] = useState(""), [fast, setFast] = useState("");
  const [rename, setRename] = useState<AdminKey | null>(null), [newLabel, setNewLabel] = useState(""), [victim, setVictim] = useState<AdminKey | null>(null);
  useEffect(() => { if (q.data) { setModels(q.data.models); setFast(q.data.fast_models); } }, [q.data]);
  const d = q.data;
  const status = (k: AdminKey): [string, "destructive" | "muted" | "warning" | "success"] => !k.masked ? ["Không giải mã được", "destructive"] : !k.enabled ? ["Đang tắt", "muted"] : k.cooling["*"] ? ["Khóa lỗi", "destructive"] : Object.keys(k.cooling).length ? ["Tạm hết lượt một số model", "warning"] : ["Đang dùng", "success"];
  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (key.trim().length < 20) return setErr({ key: "Hãy dán khóa API (thường bắt đầu bằng AIza)" });
    setBusy("add"); setErr({});
    try { const r = await send<{ message: string }>("/api/admin/keys", { label: label.trim(), key: key.trim() }); toast.success(r.message); setLabel(""); setKey(""); q.refetch(); }
    catch (e) { if (e instanceof ApiError && e.field) setErr({ [e.field]: e.message }); else toast.error((e as Error).message); } finally { setBusy(""); }
  };
  const saveModels = async (body: { models: string; fast_models: string }) => {
    setBusy("models");
    try { await send("/api/admin/settings", body, "PUT"); toast.success("Đã lưu thứ tự model"); q.refetch(); }
    catch (e) { if (e instanceof ApiError && e.field) setErr({ [e.field]: e.message }); else toast.error((e as Error).message); } finally { setBusy(""); }
  };
  const act = async (k: AdminKey, a: "test" | "toggle" | "reset") => {
    setBusy(`${a}${k.id}`);
    try {
      if (a === "test") { const r = await api<{ ok: boolean; message: string }>(`/api/admin/keys/${k.id}/test`, { method: "POST" }); r.ok ? toast.success(r.message) : toast.error(r.message); }
      else if (a === "toggle") { await send(`/api/admin/keys/${k.id}`, { enabled: !k.enabled }, "PATCH"); toast.success(k.enabled ? "Đã tắt khóa" : "Đã bật khóa"); }
      else { await send(`/api/admin/keys/${k.id}`, { reset: true }, "PATCH"); toast.success("Đã mở lại khóa"); }
      q.refetch();
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(""); }
  };
  return (
    <div className="grid grid-cols-1 gap-5 animate-fade-up lg:grid-cols-[minmax(0,1fr)_380px]">
      <section>
        <h2 className="mb-3 font-bold">Danh sách khóa{d ? ` (${d.keys.length})` : ""}</h2>
        {q.isLoading ? <div className="space-y-3">{[0, 1].map((i) => <Skeleton key={i} className="h-40" />)}</div>
          : !d?.keys.length ? <div className="rounded-2xl border bg-card"><EmptyState icon={KeyRound} title="Chưa có khóa nào" text="App đang dùng GEMINI_API_KEY trong file .env (nếu có). Thêm khóa ở bên phải." /></div>
          : <div className="space-y-3">{d.keys.map((k) => { const [l, tone] = status(k); return (
            <article key={k.id} className="rounded-2xl border bg-card p-4 shadow-soft">
              <div className="flex flex-wrap items-center gap-2"><b>{k.label}</b><Badge variant={tone}>{l}</Badge><code className="ml-auto rounded-md bg-muted px-2 py-0.5 text-xs">{k.masked || "••••"}</code><Switch checked={k.enabled} onCheckedChange={() => act(k, "toggle")} aria-label="Bật/tắt khóa" /></div>
              <p className="mt-2 flex flex-wrap gap-x-3 text-xs text-muted-foreground"><span>{k.ok_count} lượt thành công</span><span>{k.fail_count} lượt lỗi</span>{k.last_used && <span>Dùng lần cuối {ago(k.last_used)}</span>}</p>
              {Object.entries(k.cooling).map(([m, t]) => <p key={m} className="mt-1 flex items-center gap-1.5 text-sm text-warning"><Clock className="h-4 w-4" />{m === "*" ? "Tạm bỏ qua mọi model" : `Hết lượt ${m}`} đến {whenSec(t)}</p>)}
              {k.last_error && <p className="mt-1 text-xs text-muted-foreground">Lỗi gần nhất: {k.last_error}{k.last_error_at ? `, ${ago(k.last_error_at)}` : ""}</p>}
              <div className="mt-3 flex flex-wrap gap-1.5">
                <Button size="sm" variant="outline" loading={busy === `test${k.id}`} onClick={() => act(k, "test")}><Check />Kiểm tra</Button>
                {Object.keys(k.cooling).length > 0 && <Button size="sm" variant="outline" loading={busy === `reset${k.id}`} onClick={() => act(k, "reset")}><RefreshCcw />Mở lại</Button>}
                <Button size="sm" variant="ghost" onClick={() => { setRename(k); setNewLabel(k.label); }}><Pencil />Đổi tên</Button>
                <Button size="sm" variant="ghost" className="ml-auto text-destructive hover:text-destructive" onClick={() => setVictim(k)}><Trash2 />Xóa</Button>
              </div>
            </article>
          ); })}</div>}
      </section>
      <aside className="space-y-4 lg:sticky lg:top-8 lg:self-start">
        <Card>
          <CardHeader><CardTitle>Thêm khóa</CardTitle><CardDescription>Lấy khóa miễn phí ở aistudio.google.com/apikey. Mỗi dự án Google có hạn mức riêng, nên khóa từ nhiều dự án giúp AI không bị gián đoạn.</CardDescription></CardHeader>
          <CardContent>
            <form onSubmit={add} noValidate className="space-y-3">
              <Field label="Tên gợi nhớ" htmlFor="klabel" error={err.label}><Input id="klabel" maxLength={60} placeholder="VD: Khóa của Nam" value={label} onChange={(e) => setLabel(e.target.value)} /></Field>
              <Field label="Khóa API" htmlFor="key" error={err.key}><Input id="key" type="password" autoComplete="off" spellCheck={false} value={key} onChange={(e) => setKey(e.target.value)} aria-invalid={!!err.key} /></Field>
              <Button type="submit" className="w-full" loading={busy === "add"}><Check />{busy === "add" ? "Đang kiểm tra khóa…" : "Thêm và kiểm tra"}</Button>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Thứ tự model</CardTitle><CardDescription>Mỗi lần gọi, app bắt đầu từ khóa kế tiếp để chia đều lượt. Khóa nào hết lượt với một model thì thử khóa khác cùng model; mọi khóa đều hết mới xuống model sau.</CardDescription></CardHeader>
          <CardContent>
            <form onSubmit={(e) => { e.preventDefault(); saveModels({ models, fast_models: fast }); }} noValidate className="space-y-3">
              <Field label="Phân tích ảnh, trợ lý chat (mạnh trước)" htmlFor="models" error={err.models} hint={d ? `Mặc định: ${d.default_models}` : ""}><Input id="models" spellCheck={false} value={models} onChange={(e) => setModels(e.target.value)} /></Field>
              <Field label="Kiểm duyệt bài, bình luận (nhanh trước)" htmlFor="fast_models" error={err.fast_models} hint={d ? `Mặc định: ${d.default_fast_models}` : ""}><Input id="fast_models" spellCheck={false} value={fast} onChange={(e) => setFast(e.target.value)} /></Field>
              <div className="flex gap-2"><Button type="submit" variant="secondary" loading={busy === "models"}>Lưu thứ tự</Button><Button type="button" variant="ghost" onClick={() => saveModels({ models: "", fast_models: "" })}><Power />Dùng mặc định</Button></div>
            </form>
          </CardContent>
        </Card>
      </aside>
      <Dialog open={!!rename} onOpenChange={(o) => !o && setRename(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Đổi tên khóa</DialogTitle></DialogHeader>
          <Input value={newLabel} onChange={(e) => setNewLabel(e.target.value)} maxLength={60} aria-label="Tên mới" autoFocus />
          <DialogFooter><Button variant="outline" onClick={() => setRename(null)}>Hủy</Button><Button disabled={!newLabel.trim()} onClick={async () => { try { await send(`/api/admin/keys/${rename!.id}`, { label: newLabel.trim() }, "PATCH"); toast.success("Đã đổi tên"); setRename(null); q.refetch(); } catch (e) { toast.error((e as Error).message); } }}>Lưu</Button></DialogFooter>
        </DialogContent>
      </Dialog>
      <ConfirmDialog open={!!victim} onOpenChange={(o) => !o && setVictim(null)} title={`Xóa khóa "${victim?.label}"?`} description="Khóa sẽ không được dùng nữa." confirmText="Xóa" danger onConfirm={async () => { if (!victim) return; await del(`/api/admin/keys/${victim.id}`); toast.success("Đã xóa khóa"); q.refetch(); }} />
    </div>
  );
}
