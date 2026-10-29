import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CheckCircle2, Flag, Hourglass, Info } from "lucide-react";
import { api, send, type Diagnosis, type WrongReport } from "@/shared/lib/api";
import { LabelPicker } from "@/shared/components/label-picker";
import { Button } from "@/shared/ui/button";
import { Input, Textarea } from "@/shared/ui/input";
import { Field, Notice } from "@/shared/ui/misc";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/shared/ui/dialog";

/** "Kết quả sai?": người dùng chọn bệnh / loài đúng (hoặc tự ghi), quản trị viên duyệt rồi sửa kết quả và dùng ảnh để huấn luyện lại. */
export function ReportBlock({ d }: { d: Diagnosis }) {
  const q = useQuery({ queryKey: ["report", d.id], queryFn: () => api<WrongReport | null>(`/api/diagnoses/${d.id}/report`) });
  const [open, setOpen] = useState(false);
  const r = q.data;
  return (
    <section className="rounded-3xl border bg-card p-5">
      <h2 className="flex items-center gap-2 font-bold"><Flag className="h-5 w-5 text-primary" />Kết quả sai?</h2>
      {r?.status === "open" ? (
        <Notice icon={Hourglass} className="mt-2 p-3 text-sm">Bạn đã báo đúng là <b>{r.plant ? `${r.plant}: ` : ""}{r.disease}</b>. Quản trị viên sẽ xem xét, sửa kết quả và dùng ảnh này để hệ thống học lại.</Notice>
      ) : r?.status === "accepted" ? (
        <Notice tone="ok" icon={CheckCircle2} className="mt-2 p-3 text-sm">Cảm ơn bạn! Quản trị viên đã sửa kết quả theo báo cáo của bạn{r.answer ? `. Ghi chú: ${r.answer}` : "."}</Notice>
      ) : r?.status === "rejected" ? (
        <Notice icon={Info} className="mt-2 p-3 text-sm">Quản trị viên đã xem báo cáo và giữ nguyên kết quả{r.answer ? `: ${r.answer}` : "."}</Notice>
      ) : (
        <p className="mt-1 text-sm text-muted-foreground">Nếu bạn biết cây đang bị bệnh gì, hãy báo để quản trị viên sửa và hệ thống học từ ảnh thực tế của bạn.</p>
      )}
      {r?.status !== "accepted" && (
        <Button variant="outline" className="mt-3" onClick={() => setOpen(true)}><Flag />{r?.status === "open" ? "Sửa báo cáo" : "Báo bệnh đúng"}</Button>
      )}
      {open && <ReportDialog d={d} prev={r?.status === "open" ? r : null} onOpenChange={setOpen} />}
    </section>
  );
}

function ReportDialog({ d, prev, onOpenChange }: { d: Diagnosis; prev: WrongReport | null; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const pest = d.details?.kind === "pest";
  const [cls, setCls] = useState<string | null>(prev?.class_name || null), [manual, setManual] = useState(!!prev && !prev.class_name);
  const [plant, setPlant] = useState(prev && !prev.class_name ? prev.plant || "" : ""), [disease, setDisease] = useState(prev && !prev.class_name ? prev.disease : "");
  const [note, setNote] = useState(prev?.note || ""), [busy, setBusy] = useState(false), [errs, setErrs] = useState<Record<string, string>>({});
  const submit = async () => {
    setBusy(true); setErrs({});
    try {
      await send(`/api/diagnoses/${d.id}/report`, manual ? { plant, disease, note } : { class_name: cls, note });
      toast.success("Đã gửi báo cáo, cảm ơn bạn!");
      qc.invalidateQueries({ queryKey: ["report", d.id] });
      onOpenChange(false);
    } catch (e) {
      const x = e as Error & { field?: string };
      if (x.field) setErrs({ [x.field]: x.message }); else toast.error(x.message);
    } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Báo kết quả sai</DialogTitle>
          <DialogDescription>Kết quả hiện tại: {d.plant}, {d.disease.toLowerCase()}. Chọn {pest ? "loài" : "bệnh"} đúng trong danh sách.</DialogDescription>
        </DialogHeader>
        {!manual ? (
          <>
            <LabelPicker kind={pest ? "pest" : "all"} value={cls} onChange={setCls} exclude={d.raw} />
            {errs.class_name && <p className="text-sm text-destructive">{errs.class_name}</p>}
            <button type="button" className="justify-self-start text-sm font-semibold text-primary hover:underline" onClick={() => setManual(true)}>Không có trong danh sách? Tự ghi tên</button>
          </>
        ) : (
          <>
            <Field label="Tên cây" htmlFor="rp-plant"><Input id="rp-plant" maxLength={80} value={plant} onChange={(e) => setPlant(e.target.value)} placeholder="VD: Lúa" /></Field>
            <Field label={pest ? "Tên sâu hại" : "Tên bệnh / sâu hại"} htmlFor="rp-disease" error={errs.disease}><Input id="rp-disease" maxLength={120} value={disease} onChange={(e) => setDisease(e.target.value)} placeholder="VD: Bệnh đạo ôn" /></Field>
            <button type="button" className="justify-self-start text-sm font-semibold text-primary hover:underline" onClick={() => setManual(false)}>Chọn trong danh sách</button>
          </>
        )}
        <Field label="Ghi chú (không bắt buộc)" htmlFor="rp-note" error={errs.note}><Textarea id="rp-note" rows={2} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} placeholder="VD: cán bộ khuyến nông đã xác định là…" /></Field>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Hủy</Button>
          <Button loading={busy} disabled={manual ? !disease.trim() : !cls} onClick={submit}><Flag />Gửi báo cáo</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
