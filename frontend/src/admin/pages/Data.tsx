import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, CheckCheck, Database, Flag, Leaf, PencilLine, Sparkles, Trash2, X } from "lucide-react";
import { api, del, send } from "@/shared/lib/api";
import { ago, pct } from "@/shared/lib/utils";
import { LabelPicker } from "@/shared/components/label-picker";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { Textarea } from "@/shared/ui/input";
import { EmptyState, Field, Notice, Skeleton } from "@/shared/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/shared/ui/dialog";
import { ConfirmDialog } from "@/shared/components/common";
import type { AdminReport, Sample, Stats } from "../lib/types";

const SOURCE: Record<string, string> = { ai: "AI Gemini", model: "Mô hình", memory: "Bộ nhớ ảnh" };

/** Dữ liệu AI: duyệt nhãn ảnh AI đã lưu (chỉ ảnh đã duyệt được xuất ra để huấn luyện lại) và xử lý báo kết quả sai của người dùng. */
export default function Data({ stats, onChange }: { stats?: Stats; onChange: () => void }) {
  const [tab, setTab] = useState("pending");
  return (
    <div className="space-y-5 animate-fade-up">
      <Notice icon={Database}>
        Ảnh AI phân tích được lưu trong <b>dataset_ai/</b> ở trạng thái <b>chờ duyệt</b>. Duyệt hoặc sửa nhãn ở đây; người dùng báo kết quả sai thì chấp nhận để sửa kết quả và thêm ảnh thực tế vào dữ liệu.
        Huấn luyện lại chỉ với ảnh đã duyệt: <code className="rounded bg-muted px-1">flask --app app export-dataset dataset_ai_duyet</code> rồi <code className="rounded bg-muted px-1">python train.py --data … --extra dataset_ai_duyet</code>.
      </Notice>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Tabs value={tab} onValueChange={setTab} className="min-w-0">
          <TabsList className="w-full justify-start overflow-x-auto no-scrollbar">
            <TabsTrigger value="pending">Chờ duyệt{stats?.samples_pending ? ` (${stats.samples_pending})` : ""}</TabsTrigger>
            <TabsTrigger value="reports">Báo kết quả sai{stats?.reports_open ? ` (${stats.reports_open})` : ""}</TabsTrigger>
            <TabsTrigger value="approved">Đã duyệt</TabsTrigger>
            <TabsTrigger value="done">Báo cáo đã xử lý</TabsTrigger>
          </TabsList>
          <TabsContent value="pending"><Samples status="pending" onChange={onChange} /></TabsContent>
          <TabsContent value="approved"><Samples status="approved" onChange={onChange} /></TabsContent>
          <TabsContent value="reports"><Reports done={false} onChange={onChange} /></TabsContent>
          <TabsContent value="done"><Reports done onChange={onChange} /></TabsContent>
        </Tabs>
        <Card className="h-fit">
          <CardHeader><CardTitle>Số ảnh theo lớp</CardTitle></CardHeader>
          <CardContent>{stats?.classes.length ? (
            <ul className="divide-y text-sm">{stats.classes.map((c) => (
              <li key={c.class_name} className="flex justify-between gap-3 py-2"><span className="truncate">{c.class_name}</span><span className="shrink-0 tabular-nums"><b>{c.approved}</b><span className="text-muted-foreground">/{c.n} đã duyệt</span></span></li>
            ))}</ul>
          ) : <p className="text-sm text-muted-foreground">Chưa có lớp AI nào.</p>}</CardContent>
        </Card>
      </div>
    </div>
  );
}

function Samples({ status, onChange }: { status: "pending" | "approved"; onChange: () => void }) {
  const list = useQuery({ queryKey: ["admin", "samples", status], queryFn: () => api<Sample[]>(`/api/admin/samples?status=${status}`) });
  const [victim, setVictim] = useState<Sample | null>(null), [edit, setEdit] = useState<Sample | null>(null), [busy, setBusy] = useState<number | "all" | null>(null);
  const done = () => { list.refetch(); onChange(); };
  const approve = async (ids: number[], key: number | "all") => {
    setBusy(key);
    try { await send("/api/admin/samples/approve", { ids }); toast.success(ids.length > 1 ? `Đã duyệt ${ids.length} mẫu` : "Đã duyệt mẫu"); done(); }
    catch (e) { toast.error((e as Error).message); } finally { setBusy(null); }
  };
  if (list.isLoading) return <div className="grid gap-3 sm:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}</div>;
  if (!list.data?.length) return <div className="rounded-2xl border bg-card"><EmptyState icon={Sparkles} title={status === "pending" ? "Không còn ảnh nào chờ duyệt" : "Chưa có ảnh nào được duyệt"} /></div>;
  return (
    <div className="space-y-3">
      {status === "pending" && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">Xem ảnh và nhãn AI gán; đúng thì duyệt, sai thì sửa nhãn hoặc xóa.</p>
          <Button variant="outline" size="sm" loading={busy === "all"} onClick={() => approve(list.data!.map((s) => s.id), "all")}><CheckCheck />Duyệt tất cả {list.data.length} mẫu đang hiện</Button>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{list.data.map((s) => (
        <div key={s.id} className="flex min-w-0 flex-col gap-2 rounded-2xl border bg-card p-3">
          <div className="flex gap-3">
            {s.image_url ? <a href={s.image_url} target="_blank" rel="noreferrer"><img src={s.image_url} alt="" loading="lazy" className="h-20 w-20 rounded-xl object-cover" /></a> : <span className="grid h-20 w-20 place-items-center rounded-xl bg-secondary text-primary"><Leaf /></span>}
            <div className="min-w-0 flex-1">
              <b className="block text-sm leading-snug">{s.plant || ""}: {s.disease || ""}</b>
              <p className="truncate text-xs text-muted-foreground" title={s.class_name}>{s.class_name}</p>
              <p className="text-xs text-muted-foreground"><b className="text-foreground">{pct(s.confidence)}</b> · {SOURCE[s.source || ""] || "AI"} · {s.username || "?"}, {ago(s.created)}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {status === "pending" && <Button size="sm" loading={busy === s.id} onClick={() => approve([s.id], s.id)}><Check />Duyệt</Button>}
            <Button size="sm" variant="outline" onClick={() => setEdit(s)}><PencilLine />Sửa nhãn</Button>
            <Button size="sm" variant="ghost" className="ml-auto text-destructive hover:text-destructive" aria-label="Xóa mẫu dán nhãn sai" onClick={() => setVictim(s)}><Trash2 /></Button>
          </div>
        </div>
      ))}</div>
      {edit && <RelabelDialog title="Sửa nhãn mẫu" desc={`Nhãn AI: ${edit.plant}: ${edit.disease}. Kết quả tra cứu gốc cũng được sửa theo.`} current={edit.class_name} kind="leaf"
        onOpenChange={() => setEdit(null)} onSave={async (cls) => { await send(`/api/admin/samples/${edit.id}`, { action: "relabel", class_name: cls }); toast.success("Đã sửa nhãn và duyệt mẫu"); done(); }} />}
      <ConfirmDialog open={!!victim} onOpenChange={(o) => !o && setVictim(null)} title="Xóa mẫu này khỏi bộ dữ liệu AI?" description={victim ? `${victim.class_name}, ${pct(victim.confidence)}` : ""} confirmText="Xóa" danger
        onConfirm={async () => { if (!victim) return; await del(`/api/admin/samples/${victim.id}`); toast.success("Đã xóa mẫu"); done(); }} />
    </div>
  );
}

function Reports({ done, onChange }: { done: boolean; onChange: () => void }) {
  const list = useQuery({ queryKey: ["admin", "reports", done], queryFn: () => api<AdminReport[]>(`/api/admin/reports${done ? "?status=done" : ""}`) });
  const [pick, setPick] = useState<AdminReport | null>(null), [reject, setReject] = useState<AdminReport | null>(null), [busy, setBusy] = useState<number | null>(null);
  const refresh = () => { list.refetch(); onChange(); };
  const resolve = async (r: AdminReport, body: Record<string, unknown>) => {
    setBusy(r.id);
    try {
      const out = await send<{ status: string }>(`/api/admin/reports/${r.id}`, body);
      toast.success(out.status === "accepted" ? "Đã sửa kết quả và báo cho người dùng" : "Đã từ chối và báo cho người dùng"); refresh();
    } catch (e) { toast.error((e as Error).message); throw e; } finally { setBusy(null); }
  };
  if (list.isLoading) return <div className="space-y-3">{[0, 1].map((i) => <Skeleton key={i} className="h-32" />)}</div>;
  if (!list.data?.length) return <div className="rounded-2xl border bg-card"><EmptyState icon={Flag} title={done ? "Chưa xử lý báo cáo nào" : "Không có báo cáo kết quả sai nào đang chờ"} /></div>;
  return (
    <div className="space-y-3">
      {list.data.map((r) => (
        <article key={r.id} className="flex flex-col gap-3 rounded-2xl border bg-card p-4 sm:flex-row">
          {r.image_url ? <a href={r.image_url} target="_blank" rel="noreferrer" className="shrink-0"><img src={r.image_url} alt="" loading="lazy" className="h-28 w-28 rounded-xl object-cover" /></a>
            : <span className="grid h-28 w-28 shrink-0 place-items-center rounded-xl bg-secondary text-primary"><Leaf /></span>}
          <div className="min-w-0 flex-1 space-y-1.5 text-sm">
            <p className="text-xs text-muted-foreground">{r.username || "?"} báo {ago(r.created)} · {SOURCE[r.source || ""] || "Mô hình"}{r.confidence != null ? `, ${pct(r.confidence)}` : ""}</p>
            <p><span className="text-muted-foreground">Kết quả {done ? "lúc báo" : "hiện tại"}:</span> <b>{r.old_label || `${r.cur_plant}: ${r.cur_disease}`}</b></p>
            <p><span className="text-muted-foreground">Người dùng cho là:</span> <b className="text-primary">{r.plant ? `${r.plant}: ` : ""}{r.disease}</b>{!r.class_name && <Badge variant="muted" className="ml-1.5">tự ghi</Badge>}</p>
            {r.note && <p className="rounded-lg bg-muted px-2 py-1">“{r.note}”</p>}
            {!!r.top.length && <p className="text-xs text-muted-foreground">Mô hình cân nhắc: {r.top.map((t) => `${t.disease} (${pct(t.prob)})`).join(", ")}</p>}
            {done ? (
              <p className="flex flex-wrap items-center gap-2"><Badge variant={r.status === "accepted" ? "success" : "muted"}>{r.status === "accepted" ? "Đã sửa kết quả" : "Đã từ chối"}</Badge>{r.answer && <span className="text-muted-foreground">{r.answer}</span>}</p>
            ) : (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {r.class_name && <Button size="sm" loading={busy === r.id} onClick={() => resolve(r, { action: "accept" }).catch(() => {})}><Check />Chấp nhận nhãn này</Button>}
                <Button size="sm" variant="outline" onClick={() => setPick(r)}><PencilLine />{r.class_name ? "Chọn nhãn khác" : "Chọn nhãn đúng"}</Button>
                <Button size="sm" variant="ghost" onClick={() => setReject(r)}><X />Từ chối</Button>
              </div>
            )}
          </div>
        </article>
      ))}
      {pick && <RelabelDialog title="Chọn nhãn đúng" desc={`Người dùng cho là: ${pick.plant ? pick.plant + ": " : ""}${pick.disease}. Kết quả được sửa, ảnh thêm vào dữ liệu đã duyệt.`}
        current={pick.class_name} kind={pick.kind === "pest" ? "pest" : "leaf"} withAnswer onOpenChange={() => setPick(null)}
        onSave={(cls, answer) => resolve(pick, { action: "accept", class_name: cls, answer })} />}
      {reject && <RejectDialog r={reject} onOpenChange={() => setReject(null)} onSave={(answer) => resolve(reject, { action: "reject", answer })} />}
    </div>
  );
}

function RelabelDialog({ title, desc, current, kind, withAnswer, onOpenChange, onSave }: {
  title: string; desc: string; current: string | null; kind: "leaf" | "pest"; withAnswer?: boolean; onOpenChange: () => void; onSave: (cls: string, answer: string) => Promise<void>;
}) {
  const [cls, setCls] = useState<string | null>(current), [answer, setAnswer] = useState(""), [busy, setBusy] = useState(false);
  const save = async () => {
    if (!cls) return;
    setBusy(true);
    try { await onSave(cls, answer); onOpenChange(); } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>{title}</DialogTitle><DialogDescription>{desc}</DialogDescription></DialogHeader>
        <LabelPicker kind={kind} value={cls} onChange={setCls} />
        {withAnswer && <Field label="Nhắn người dùng (không bắt buộc)" htmlFor="rl-answer"><Textarea id="rl-answer" rows={2} maxLength={300} value={answer} onChange={(e) => setAnswer(e.target.value)} /></Field>}
        <DialogFooter><Button variant="ghost" onClick={onOpenChange}>Hủy</Button><Button loading={busy} disabled={!cls} onClick={save}><Check />Lưu nhãn</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RejectDialog({ r, onOpenChange, onSave }: { r: AdminReport; onOpenChange: () => void; onSave: (answer: string) => Promise<void> }) {
  const [answer, setAnswer] = useState(""), [busy, setBusy] = useState(false);
  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Giữ nguyên kết quả?</DialogTitle><DialogDescription>Người dùng cho là {r.disease}; kết quả hiện tại là {r.cur_disease}. Người dùng sẽ nhận thông báo kèm lý do.</DialogDescription></DialogHeader>
        <Field label="Lý do (không bắt buộc)" htmlFor="rj-answer"><Textarea id="rj-answer" rows={3} maxLength={300} value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="VD: vết bệnh có vòng đồng tâm, đúng là đốm vòng" /></Field>
        <DialogFooter>
          <Button variant="ghost" onClick={onOpenChange}>Hủy</Button>
          <Button variant="destructive" loading={busy} onClick={async () => { setBusy(true); try { await onSave(answer); onOpenChange(); } catch { /* đã báo lỗi */ } finally { setBusy(false); } }}><X />Từ chối</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
