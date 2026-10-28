import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { BellPlus, Droplets, Eye, Info, Loader2, NotebookPen, Scissors, SprayCan, Wrench } from "lucide-react";
import { api, send, type LogKind } from "@/shared/lib/api";
import { cn, dayKey, fmtDate, fmtTime, toDate } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/shared/ui/dialog";
import { Field } from "@/shared/ui/misc";

export const KIND_ICON: Record<LogKind, React.ComponentType<{ className?: string }>> = { phun: SprayCan, tia: Scissors, tuoi: Droplets, kiemtra: Eye, khac: Wrench };

/** "Quá hạn 2 ngày", "Hôm nay 07:00", "Ngày mai 07:00", "Thứ ba 29/10, 07:00". */
export function dueLabel(due: string) {
  const d = toDate(due), now = new Date(), diffDays = Math.round((new Date(dayKey(d)).getTime() - new Date(dayKey(now)).getTime()) / 864e5);
  if (d.getTime() < now.getTime()) return diffDays === 0 ? `Hôm nay ${fmtTime(d)}, đã đến hạn` : `Quá hạn ${-diffDays} ngày (${fmtDate(d)})`;
  if (diffDays === 0) return `Hôm nay ${fmtTime(d)}`;
  if (diffDays === 1) return `Ngày mai ${fmtTime(d)}`;
  const WEEK = ["Chủ nhật", "Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy"];
  return `${WEEK[d.getDay()]} ${fmtDate(d).slice(0, 5)}, ${fmtTime(d)}`;
}

/** Giá trị cho <input type="datetime-local"> sau `days` ngày, lúc `hour` giờ (giờ địa phương). */
export function localAt(days: number, hour = 7) {
  const d = new Date(); d.setDate(d.getDate() + days); d.setHours(hour, 0, 0, 0);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}
export const toUtc = (local: string) => new Date(local).toISOString();

interface Suggest { content: string; days: number; repeat_days: number; on: boolean }
interface CarePlan { kind: string; label: string; note: string; steps: Suggest[] }

/** Hộp thoại mở nhật ký theo dõi: từ kết quả tra cứu hoặc tự ghi cây/bệnh. Nhắc việc ban đầu do máy chủ gợi ý theo nhóm bệnh
 *  (care.py: nấm phấn trắng, mốc sương, vi khuẩn, virus, nhện, từng nhóm sâu hại, do môi trường...), mỗi nhóm một nhịp khác nhau. */
export function TrackDialog({ open, onOpenChange, diagnosis }: { open: boolean; onOpenChange: (o: boolean) => void; diagnosis?: { id: number; plant: string; disease: string } }) {
  const nav = useNavigate(), qc = useQueryClient();
  const [name, setName] = useState(""), [plant, setPlant] = useState(""), [disease, setDisease] = useState(""), [busy, setBusy] = useState(false);
  const [sug, setSug] = useState<Suggest[]>([]);
  // Tự ghi: chờ gõ xong tên bệnh rồi mới hỏi lịch gợi ý
  const [typed, setTyped] = useState("");
  useEffect(() => { const t = setTimeout(() => setTyped(disease.trim()), 500); return () => clearTimeout(t); }, [disease]);
  const plan = useQuery({
    queryKey: ["care-plan", diagnosis?.id ?? null, diagnosis ? "" : typed],
    queryFn: () => api<CarePlan>(diagnosis ? `/api/care-plan?diagnosis_id=${diagnosis.id}` : `/api/care-plan?disease=${encodeURIComponent(typed)}`),
    enabled: open, staleTime: Infinity, placeholderData: keepPreviousData,
  });
  useEffect(() => { if (plan.data) setSug(plan.data.steps); }, [plan.data]);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!diagnosis && (!plant.trim() || !disease.trim())) return toast.error("Hãy nhập tên cây và tên bệnh / sâu hại");
    setBusy(true);
    try {
      const r = await send<{ id: number }>("/api/treatments", {
        diagnosis_id: diagnosis?.id, name: name.trim(), plant: plant.trim(), disease: disease.trim(),
        reminders: sug.filter((s) => s.on).map((s) => ({ content: s.content, due: toUtc(localAt(s.days)), repeat_days: s.repeat_days })),
      });
      qc.invalidateQueries({ queryKey: ["treatments"] }); qc.invalidateQueries({ queryKey: ["me"] });
      toast.success("Đã mở nhật ký theo dõi"); onOpenChange(false); nav(`/journal/${r.id}`);
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><NotebookPen className="h-5 w-5 text-primary" />Theo dõi điều trị</DialogTitle>
            <DialogDescription>{diagnosis ? `${diagnosis.plant}: ${diagnosis.disease}. Ghi lại việc đã làm và đặt lịch nhắc để không quên.` : "Ghi nhật ký cho một cây hoặc luống đang có vấn đề."}</DialogDescription>
          </DialogHeader>
          {!diagnosis && (
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Cây trồng" htmlFor="t-plant"><Input id="t-plant" value={plant} onChange={(e) => setPlant(e.target.value)} placeholder="VD: Cà chua" maxLength={60} /></Field>
              <Field label="Bệnh / sâu hại" htmlFor="t-disease"><Input id="t-disease" value={disease} onChange={(e) => setDisease(e.target.value)} placeholder="VD: Mốc sương" maxLength={100} /></Field>
            </div>
          )}
          <Field label="Tên gợi nhớ (không bắt buộc)" htmlFor="t-name" hint="VD: Luống cà chua sau nhà, Cây xoài góc vườn"><Input id="t-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} /></Field>
          <fieldset>
            <legend className="mb-2 flex items-center gap-1.5 text-sm font-semibold"><BellPlus className="h-4 w-4 text-primary" />Nhắc việc ban đầu
              {plan.data && <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px] font-semibold text-primary">{plan.data.label}</span>}
            </legend>
            {plan.data?.note && <p className="mb-2 flex gap-1.5 text-xs leading-relaxed text-muted-foreground"><Info className="mt-px h-3.5 w-3.5 shrink-0 text-primary" />{plan.data.note}</p>}
            {plan.isLoading && <p className="flex items-center gap-2 py-3 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Đang lập lịch gợi ý…</p>}
            <div className="space-y-1.5">
              {sug.map((s, i) => (
                <label key={i} className={cn("flex cursor-pointer items-center gap-3 rounded-xl border p-3 text-sm transition", s.on && "border-primary bg-secondary/50")}>
                  <input type="checkbox" className="h-4 w-4 accent-[hsl(var(--primary))]" checked={s.on} onChange={(e) => setSug(sug.map((x, j) => (j === i ? { ...x, on: e.target.checked } : x)))} />
                  <span className="flex-1">{s.content}</span>
                  <span className="text-xs text-muted-foreground">sau {s.days} ngày{s.repeat_days ? `, lặp ${s.repeat_days} ngày` : ""}</span>
                </label>
              ))}
            </div>
            <p className="mt-1.5 text-xs text-muted-foreground">Có thể thêm, sửa nhắc việc sau trong nhật ký. Đến hạn sẽ có thông báo trong ứng dụng (và email nếu máy chủ đã cấu hình).</p>
          </fieldset>
          <DialogFooter><Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Hủy</Button><Button type="submit" loading={busy}>Mở nhật ký</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
