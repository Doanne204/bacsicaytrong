import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlarmClock, AlertTriangle, ArrowLeft, Bug, Camera, CheckCircle2, ImagePlus, Leaf, Plus, RotateCcw, Trash2, Undo2, X } from "lucide-react";
import { api, del, send, upload, LOG_KINDS, type LogKind, type Reminder, type TreatmentDetail } from "@/shared/lib/api";
import { cn, fmtDate, fmtTime, pickFile, shrink, toDate } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";
import { Input, Textarea } from "@/shared/ui/input";
import { Notice } from "@/shared/ui/misc";
import { ConfirmDialog } from "@/shared/components/common";
import { PageSkeleton } from "../layout/PageSkeleton";
import { KIND_ICON, dueLabel, localAt, toUtc } from "../components/journal";

export default function JournalDetail() {
  const { id } = useParams();
  const nav = useNavigate(), qc = useQueryClient();
  const q = useQuery({ queryKey: ["treatment", id], queryFn: () => api<TreatmentDetail>(`/api/treatments/${id}`) });
  const [confirm, setConfirm] = useState(false);
  if (q.isLoading) return <PageSkeleton />;
  if (!q.data) return <Notice tone="danger" icon={AlertTriangle}>{(q.error as Error)?.message || "Không tìm thấy nhật ký"}</Notice>;
  const t = q.data, active = t.status === "active", pest = t.plant === "Sâu hại" || t.plant === "Thiên địch";
  const refresh = () => { q.refetch(); qc.invalidateQueries({ queryKey: ["treatments"] }); qc.invalidateQueries({ queryKey: ["reminders"] }); qc.invalidateQueries({ queryKey: ["me"] }); };
  const setStatus = async (status: "active" | "done") => {
    try { await send(`/api/treatments/${t.id}`, { status }, "PUT"); toast.success(status === "done" ? "Đã khép nhật ký" : "Đã mở lại nhật ký"); refresh(); }
    catch (e) { toast.error((e as Error).message); }
  };
  return (
    <div className="animate-fade-up">
      <Link to="/journal" className="mb-3 inline-flex items-center gap-1 text-sm font-semibold text-muted-foreground hover:text-primary"><ArrowLeft className="h-4 w-4" />Nhật ký điều trị</Link>
      <section className="mb-5 flex flex-wrap items-start gap-4 rounded-3xl border bg-card p-5 shadow-soft">
        {t.diagnosis?.image_url ? <img src={t.diagnosis.image_url} alt="" className="h-20 w-20 rounded-2xl object-cover" /> : <span className="grid h-20 w-20 place-items-center rounded-2xl bg-secondary text-primary">{pest ? <Bug className="h-8 w-8" /> : <Leaf className="h-8 w-8" />}</span>}
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-muted-foreground">{t.plant}</p>
          <h1 className="text-2xl font-extrabold leading-tight">{t.name || t.disease}</h1>
          {t.name && <p className="text-muted-foreground">{t.disease}</p>}
          <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <Badge variant={active ? "secondary" : "success"}>{active ? "Đang theo dõi" : "Đã xong"}</Badge>
            <span>Mở {fmtDate(toDate(t.created))}{t.closed ? `, xong ${fmtDate(toDate(t.closed))}` : ""}</span>
            {t.diagnosis && <Link to={`/diagnosis/${t.diagnosis.id}`} className="font-semibold text-primary hover:underline">Xem kết quả tra cứu</Link>}
          </p>
        </div>
        <div className="flex w-full gap-2 sm:w-auto">
          {active ? <Button variant="outline" className="flex-1" onClick={() => setStatus("done")}><CheckCircle2 />Đã khỏi, khép lại</Button> : <Button variant="outline" className="flex-1" onClick={() => setStatus("active")}><RotateCcw />Mở lại</Button>}
          <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive" aria-label="Xóa nhật ký" onClick={() => setConfirm(true)}><Trash2 /></Button>
        </div>
      </section>
      {t.remedy && <Notice className="mb-5" icon={Leaf}><b>Hướng xử lý:</b> {t.remedy}</Notice>}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <section>
          <h2 className="mb-3 text-lg font-bold">Ghi chép</h2>
          {active && <LogForm tid={t.id} onSaved={refresh} />}
          {!t.entries.length ? <p className="rounded-2xl border border-dashed p-6 text-center text-sm text-muted-foreground">Chưa có ghi chép nào. Ghi lại ngay khi phun thuốc, tỉa lá, tưới bón để theo dõi tiến triển.</p>
            : <ol className="relative mt-4 space-y-4 border-l-2 border-muted pl-6">
              {t.entries.map((e) => {
                const Icon = KIND_ICON[e.kind] || KIND_ICON.khac, when = toDate(e.done_at || e.created);
                return (
                  <li key={e.id} className="relative">
                    <span className="absolute -left-[31px] top-0 grid h-7 w-7 place-items-center rounded-full border-2 border-background bg-secondary text-primary"><Icon className="h-3.5 w-3.5" /></span>
                    <div className="rounded-2xl border bg-card p-3.5">
                      <div className="flex items-center gap-2 text-xs text-muted-foreground"><b className="text-foreground">{LOG_KINDS[e.kind] || "Việc khác"}</b><span>{fmtTime(when)}, {fmtDate(when)}</span>
                        {active && <button type="button" className="ml-auto rounded-md p-1 hover:bg-accent hover:text-destructive" aria-label="Xóa ghi chép" onClick={async () => { await del(`/api/logs/${e.id}`); refresh(); }}><X className="h-4 w-4" /></button>}
                      </div>
                      {e.content && <p className="mt-1 whitespace-pre-wrap text-[15px]">{e.content}</p>}
                      {e.image_url && <a href={e.image_url} target="_blank" rel="noreferrer"><img src={e.image_url} alt="Ảnh ghi chép" loading="lazy" className="mt-2 max-h-64 rounded-xl object-cover" /></a>}
                    </div>
                  </li>
                );
              })}
            </ol>}
        </section>
        <aside>
          <h2 className="mb-3 flex items-center gap-2 text-lg font-bold"><AlarmClock className="h-5 w-5 text-primary" />Nhắc việc</h2>
          <Reminders t={t} onChange={refresh} />
        </aside>
      </div>
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Xóa nhật ký này?" description="Mọi ghi chép, ảnh và nhắc việc trong nhật ký sẽ bị xóa." confirmText="Xóa" danger
        onConfirm={async () => { await del(`/api/treatments/${t.id}`); toast.success("Đã xóa nhật ký"); qc.invalidateQueries({ queryKey: ["treatments"] }); nav("/journal"); }} />
    </div>
  );
}

function LogForm({ tid, onSaved }: { tid: number; onSaved: () => void }) {
  const [kind, setKind] = useState<LogKind>("phun"), [content, setContent] = useState(""), [file, setFile] = useState<File | null>(null), [preview, setPreview] = useState(""), [busy, setBusy] = useState(false);
  const pick = async (capture: boolean) => { const f = await pickFile(capture); if (f) { const s = await shrink(f, 1200); setFile(s); setPreview(URL.createObjectURL(s)); } };
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim() && !file) return toast.error("Hãy ghi vài chữ hoặc thêm ảnh");
    setBusy(true);
    try {
      const fd = new FormData(); fd.append("kind", kind); fd.append("content", content.trim()); if (file) fd.append("image", file);
      await upload(`/api/treatments/${tid}/logs`, fd);
      setContent(""); setFile(null); setPreview(""); toast.success("Đã ghi vào nhật ký"); onSaved();
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="rounded-2xl border bg-card p-4">
      <div className="mb-3 flex flex-wrap gap-1.5">
        {(Object.keys(LOG_KINDS) as LogKind[]).map((k) => { const I = KIND_ICON[k]; return <button key={k} type="button" onClick={() => setKind(k)} aria-pressed={kind === k} className={cn("inline-flex h-9 items-center gap-1.5 rounded-full border px-3 text-sm font-semibold transition", kind === k ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:border-primary")}><I className="h-4 w-4" />{LOG_KINDS[k]}</button>; })}
      </div>
      <Textarea rows={2} maxLength={1000} value={content} onChange={(e) => setContent(e.target.value)} placeholder={{ phun: "VD: Phun mancozeb 80WP, 25 g/10 lít, phun ướt đều 2 mặt lá", tia: "VD: Ngắt bỏ 12 lá gốc có vết bệnh, đem đốt", tuoi: "VD: Tưới gốc, bón 50 g NPK 16-16-8 mỗi gốc", kiemtra: "VD: Vết bệnh khô lại, không thấy lá mới bị", khac: "Ghi chú" }[kind]} />
      {preview && <div className="relative mt-2 inline-block"><img src={preview} alt="" className="h-24 rounded-xl object-cover" /><button type="button" onClick={() => { setFile(null); setPreview(""); }} className="absolute -right-2 -top-2 grid h-6 w-6 place-items-center rounded-full bg-foreground text-background" aria-label="Bỏ ảnh"><X className="h-3.5 w-3.5" /></button></div>}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => pick(true)}><Camera />Chụp ảnh</Button>
        <Button type="button" variant="outline" size="sm" onClick={() => pick(false)}><ImagePlus />Chọn ảnh</Button>
        <Button type="submit" size="sm" className="ml-auto" loading={busy}><Plus />Ghi vào nhật ký</Button>
      </div>
    </form>
  );
}

function Reminders({ t, onChange }: { t: TreatmentDetail; onChange: () => void }) {
  const active = t.status === "active";
  const [adding, setAdding] = useState(false), [content, setContent] = useState(""), [due, setDue] = useState(localAt(3)), [repeat, setRepeat] = useState(0), [busy, setBusy] = useState(false);
  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) return toast.error("Hãy nhập nội dung nhắc");
    setBusy(true);
    try { await send(`/api/treatments/${t.id}/reminders`, { content: content.trim(), due: toUtc(due), repeat_days: repeat }); setContent(""); setAdding(false); toast.success("Đã đặt nhắc việc"); onChange(); }
    catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  };
  const toggle = async (r: Reminder) => {
    try {
      await send(`/api/reminders/${r.id}`, { done: r.done ? 0 : 1 }, "PUT");
      if (!r.done) toast.success(r.repeat_days ? `Đã ghi vào nhật ký, hẹn lại sau ${r.repeat_days} ngày` : "Đã ghi vào nhật ký");
      onChange();
    } catch (e) { toast.error((e as Error).message); }
  };
  const pending = t.reminders.filter((r) => !r.done), done = t.reminders.filter((r) => r.done);
  const now = Date.now();
  return (
    <div className="space-y-3">
      {!pending.length && !adding && <p className="rounded-2xl border border-dashed p-4 text-center text-sm text-muted-foreground">{active ? "Chưa có nhắc việc nào." : "Nhật ký đã khép."}</p>}
      <ul className="space-y-2">
        {pending.map((r) => {
          const over = toDate(r.due).getTime() <= now;
          return (
            <li key={r.id} className={cn("flex items-start gap-3 rounded-2xl border bg-card p-3", over && "border-destructive/50 bg-destructive/5")}>
              <button type="button" onClick={() => toggle(r)} disabled={!active} className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full border-2 border-primary text-primary transition hover:bg-primary hover:text-primary-foreground disabled:opacity-40" aria-label="Đánh dấu đã làm"><CheckCircle2 className="h-4 w-4" /></button>
              <span className="min-w-0 flex-1 text-sm"><b className="block">{r.content}</b><span className={cn("text-xs", over ? "font-semibold text-destructive" : "text-muted-foreground")}>{dueLabel(r.due)}{r.repeat_days ? ` · lặp ${r.repeat_days} ngày` : ""}</span></span>
              {active && <button type="button" className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-destructive" aria-label="Xóa nhắc việc" onClick={async () => { await del(`/api/reminders/${r.id}`); onChange(); }}><X className="h-4 w-4" /></button>}
            </li>
          );
        })}
      </ul>
      {active && (adding ? (
        <form onSubmit={add} className="space-y-3 rounded-2xl border bg-card p-3">
          <Input value={content} onChange={(e) => setContent(e.target.value)} placeholder="Việc cần làm, VD: Phun thuốc lần 2" maxLength={200} autoFocus />
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs font-semibold">Khi nào<Input type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} className="mt-1" /></label>
            <label className="text-xs font-semibold">Lặp lại
              <select value={repeat} onChange={(e) => setRepeat(Number(e.target.value))} className="mt-1 flex h-11 w-full rounded-xl border border-input bg-card px-3 text-sm">
                {[[0, "Không lặp"], [3, "Mỗi 3 ngày"], [5, "Mỗi 5 ngày"], [7, "Hằng tuần"], [14, "Mỗi 2 tuần"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
          </div>
          <div className="flex gap-2"><Button type="button" variant="ghost" size="sm" onClick={() => setAdding(false)}>Hủy</Button><Button type="submit" size="sm" className="ml-auto" loading={busy}>Đặt nhắc</Button></div>
        </form>
      ) : <Button variant="outline" className="w-full" onClick={() => setAdding(true)}><Plus />Thêm nhắc việc</Button>)}
      {!!done.length && (
        <details className="text-sm">
          <summary className="cursor-pointer font-semibold text-muted-foreground">Đã làm ({done.length})</summary>
          <ul className="mt-2 space-y-1.5">
            {done.map((r) => (
              <li key={r.id} className="flex items-center gap-2 rounded-xl bg-muted/60 px-3 py-2 text-muted-foreground"><CheckCircle2 className="h-4 w-4 shrink-0 text-primary" /><span className="flex-1 line-through">{r.content}</span>
                {active && <button type="button" className="rounded-md p-1 hover:bg-accent" aria-label="Mở lại nhắc việc" onClick={() => toggle(r)}><Undo2 className="h-4 w-4" /></button>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
