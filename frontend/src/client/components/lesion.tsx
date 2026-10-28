import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bug, Columns2, ImageIcon, Info, Loader2 } from "lucide-react";
import { api, type Diagnosis } from "@/shared/lib/api";
import { cn, pct } from "@/shared/lib/utils";
import { Tabs, TabsList, TabsTrigger } from "@/shared/ui/tabs";

/** Ảnh tra cứu kèm ảnh tô vết bệnh: phần lá không còn xanh (nâu, vàng, đen, trắng), máy chủ tìm theo màu, không dùng mô hình.
 *  Lượt tra cứu nhiều ảnh: dải ảnh nhỏ để chuyển ảnh, kèm kết quả mô hình của từng ảnh. Kết quả cũ chưa có ảnh vết bệnh thì xin vẽ khi mở tab. */
export function LesionViewer({ d }: { d: Diagnosis }) {
  const qc = useQueryClient();
  const det = d.details || {}, photos = det.photos || [];
  const [view, setView] = useState<"orig" | "lesion" | "both">("orig"), [idx, setIdx] = useState(0);
  const q = useQuery({
    queryKey: ["lesion", d.id],
    queryFn: async () => { const r = await api<{ url: string }>(`/api/diagnoses/${d.id}/lesion`); qc.invalidateQueries({ queryKey: ["diagnosis", String(d.id)] }); return r; },
    enabled: view !== "orig" && idx === 0 && !det.lesion_url && !!det.lesion_available, retry: false, staleTime: Infinity,
  });
  if (!d.image_url) return null;
  const photo = photos[idx], src = photo?.url || d.image_url;
  const url = idx === 0 ? det.lesion_url || q.data?.url : photo?.lesion_url;
  const hasLesion = !det.demo && (!!det.lesion_url || !!det.lesion_available || photos.some((p) => p.lesion_url));
  const img = (s: string, alt: string, extra?: string) => <img src={s} alt={alt} className={cn("aspect-[4/3] w-full rounded-3xl bg-secondary object-cover lg:aspect-square", extra)} />;
  const lesionBox = url ? img(url, "Vết bệnh tìm theo màu") : (
    <div className="grid aspect-[4/3] w-full place-items-center rounded-3xl bg-secondary p-6 text-center text-sm text-muted-foreground lg:aspect-square">
      {idx > 0 ? "Không tách được lá khỏi nền ở ảnh này nên chưa tô được vết bệnh."
        : q.isError ? (q.error as Error).message : <span className="inline-flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" />Đang tìm vết bệnh…</span>}
    </div>
  );
  return (
    <div>
      {view === "orig" || !hasLesion ? img(src, `Ảnh ${idx + 1} đã tra cứu`) : view === "lesion" ? lesionBox : (
        <div className="grid grid-cols-2 gap-2">
          <figure>{img(src, "Ảnh gốc", "lg:aspect-[4/5]")}<figcaption className="mt-1 text-center text-xs text-muted-foreground">Ảnh gốc</figcaption></figure>
          <figure>{url ? img(url, "Vết bệnh", "lg:aspect-[4/5]") : lesionBox}<figcaption className="mt-1 text-center text-xs text-muted-foreground">Vết bệnh</figcaption></figure>
        </div>
      )}
      {photos.length > 1 && (
        <div className="mt-3">
          <div className="flex gap-2" role="group" aria-label="Chọn ảnh">
            {photos.map((p, i) => (
              <button key={p.url} type="button" onClick={() => setIdx(i)} aria-pressed={idx === i} aria-label={`Ảnh ${i + 1}`}
                className={cn("relative h-16 w-16 overflow-hidden rounded-xl border-2 transition", idx === i ? "border-primary" : "border-transparent opacity-70 hover:opacity-100")}>
                <img src={p.url} alt="" className="h-full w-full object-cover" />
                <span className="absolute left-1 top-1 rounded bg-black/60 px-1 text-[10px] font-bold text-white">{i + 1}</span>
              </button>
            ))}
          </div>
          {photo && (
            <p className="mt-1.5 text-xs text-muted-foreground">
              Ảnh {idx + 1}{photo.disease ? <>: mô hình nhận ra <b className="text-foreground">{photo.disease.toLowerCase()}</b> {pct(photo.prob ?? 0)}</> : ""}
              {!photo.used && " (không dùng để kết luận: ảnh không giống dữ liệu đã học)"}. Kết luận bên dưới gộp từ {photos.filter((p) => p.used).length} ảnh.
            </p>
          )}
        </div>
      )}
      {hasLesion && (
        <section className="mt-3 space-y-3">
          <Tabs value={view} onValueChange={(v) => setView(v as "orig")}>
            <TabsList className="w-full sm:w-auto">
              <TabsTrigger value="orig" className="flex-1 sm:flex-none"><ImageIcon />Ảnh gốc</TabsTrigger>
              <TabsTrigger value="lesion" className="flex-1 sm:flex-none"><Bug />Vết bệnh</TabsTrigger>
              <TabsTrigger value="both" className="flex-1 sm:flex-none"><Columns2 />Cạnh nhau</TabsTrigger>
            </TabsList>
          </Tabs>
          {view !== "orig" && (
            <p className="flex gap-2 rounded-2xl border bg-card p-4 text-sm leading-relaxed"><Info className="mt-0.5 h-4 w-4 shrink-0 text-pink-600" />
              <span>Phần tô hồng là chỗ lá <b>không còn màu xanh</b> (nâu, vàng, đen, trắng), hệ thống tìm theo màu sắc. Bóng đổ, cuống, đất hoặc nền có màu cũng có thể bị tô nhầm: chụp lá trên nền đơn giản, đủ sáng để kết quả đúng hơn.</span>
            </p>
          )}
        </section>
      )}
    </div>
  );
}
