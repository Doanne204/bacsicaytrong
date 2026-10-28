import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Bug, Camera, ImagePlus, Leaf, Loader2, RefreshCcw, Sparkles, SwitchCamera, X } from "lucide-react";
import { api, upload, type Plant, type PredictResult } from "@/shared/lib/api";
import { cn, liveCamera, pickFile, shrink } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { PageHeader } from "@/shared/components/common";
import { Skeleton } from "@/shared/ui/misc";

/** Dòng trạng thái khi đang phân tích: lần lượt các bước của hệ thống, quá lâu thì báo đang nhờ AI. */
function ScanStatus({ plant }: { plant: string }) {
  const steps = plant === "pest"
    ? ["Đang tải ảnh lên", "Mô hình đang nhận diện sâu hại", "Đang so với 204 loài đã học", "Đang tra cách phòng trừ"]
    : ["Đang tải ảnh lên", "Mô hình đang nhận diện lá", "Đang so với dữ liệu đã học", "Đang tìm vết bệnh trên lá"];
  const [t, setT] = useState(0);
  useEffect(() => { const id = setInterval(() => setT((x) => x + 1), 1200); return () => clearInterval(id); }, []);
  const text = t < steps.length ? steps[t] : t < 6 ? "Sắp xong" : "Mô hình chưa chắc chắn, AI đang phân tích thêm (khoảng 10-15 giây)";
  return (
    <div className="absolute inset-x-0 bottom-0 z-[7] bg-black/65 px-4 py-3 text-white" role="status" aria-live="polite">
      <div className="flex items-center justify-center gap-2 text-sm font-semibold">
        <Loader2 className="h-4 w-4 shrink-0 animate-spin" /><span className="text-center">{text}…</span>
      </div>
      <div className="mt-2 flex justify-center gap-1.5" aria-hidden>
        {steps.map((_, i) => <span key={i} className={cn("h-1.5 rounded-full transition-all duration-500", i <= t ? "w-6 bg-paddy" : "w-1.5 bg-white/40")} />)}
      </div>
    </div>
  );
}

/** Ảnh chọn từ trang chủ chuyển sang trang tra cứu. */
export const pending: { file: File | null } = { file: null };

export default function Scan({ camera }: { camera?: boolean }) {
  const nav = useNavigate();
  const plants = useQuery({ queryKey: ["plants"], queryFn: () => api<Plant[]>("/api/plants") });
  const [file, setFile] = useState<File | null>(null), [preview, setPreview] = useState("");
  const [plant, setPlant] = useState("auto"), [mode, setMode] = useState<"empty" | "camera" | "preview">("empty");
  const [facing, setFacing] = useState<"environment" | "user">("environment");
  const [busy, setBusy] = useState(false), [err, setErr] = useState("");
  // Ảnh thêm (không bắt buộc): lá bệnh khác trên cùng cây hoặc góc khác của con sâu; máy chủ gộp kết quả các ảnh
  const [extras, setExtras] = useState<{ file: File; url: string }[]>([]);
  const addExtra = async () => { const f = await pickFile(false); if (f) { const s = await shrink(f); setExtras((x) => [...x, { file: s, url: URL.createObjectURL(s) }].slice(0, 2)); } };
  const video = useRef<HTMLVideoElement>(null), stream = useRef<MediaStream | null>(null);
  const stop = () => { stream.current?.getTracks().forEach((t) => t.stop()); stream.current = null; };
  const usePhoto = async (f: File) => { stop(); const s = await shrink(f); setFile(s); setPreview(URL.createObjectURL(s)); setMode("preview"); setErr(""); };
  const pick = async (capture: boolean) => { const f = await pickFile(capture); if (f) usePhoto(f); };
  const startCamera = async (face = facing) => {
    if (!liveCamera()) return pick(true);
    try {
      stop();
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { facingMode: face, width: { ideal: 1920 } }, audio: false });
      setMode("camera");
      requestAnimationFrame(async () => { if (video.current) { video.current.srcObject = stream.current; await video.current.play(); } });
    } catch { toast.error("Không mở được camera, hãy chọn ảnh từ máy"); pick(true); }
  };
  const shoot = () => {
    const v = video.current; if (!v) return;
    const c = Object.assign(document.createElement("canvas"), { width: v.videoWidth, height: v.videoHeight });
    c.getContext("2d")!.drawImage(v, 0, 0);
    c.toBlob((b) => b && usePhoto(new File([b], "chup.jpg", { type: "image/jpeg" })), "image/jpeg", 0.92);
  };
  const [dragging, setDragging] = useState(false);
  const fromList = (list?: DataTransfer | null) => {  // ảnh kéo thả hoặc dán (Ctrl+V) từ clipboard
    const f = [...(list?.files || [])].find((x) => x.type.startsWith("image/"))
      || [...(list?.items || [])].map((i) => (i.kind === "file" && i.type.startsWith("image/") ? i.getAsFile() : null)).find(Boolean);
    if (f) usePhoto(f);
    return !!f;
  };
  useEffect(() => {
    if (pending.file) { const f = pending.file; pending.file = null; usePhoto(f); }
    else if (camera && liveCamera()) startCamera();
    const onPaste = (e: ClipboardEvent) => { if (!(e.target instanceof HTMLTextAreaElement) && fromList(e.clipboardData)) e.preventDefault(); };
    document.addEventListener("paste", onPaste);
    return () => { stop(); document.removeEventListener("paste", onPaste); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const analyze = async () => {
    if (!file) return;
    const fd = new FormData(); fd.append("image", file); extras.forEach((x) => fd.append("image", x.file)); fd.append("plant", plant);
    setBusy(true); setErr("");
    try { const r = await upload<PredictResult>("/api/predict", fd); nav(`/diagnosis/${r.diagnosis_id}`); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const opts: Plant[] = [{ id: "auto", name: "Tự nhận diện", note: "", source: "model" }, ...(plants.data || []), { id: "other", name: "Cây khác", note: "", source: "ai" }];
  const hasPest = plants.data?.some((p) => p.source === "pest");
  const noteFor = (id: string) => {
    if (id === "auto") return `Hệ thống tự nhận ra loại cây${hasPest ? " hoặc sâu hại" : ""}. Nếu mô hình chưa chắc chắn, AI sẽ phân tích thêm.`;
    if (id === "other") return "Cây chưa có trong dữ liệu: AI sẽ phân tích ảnh và ghi nhớ để hệ thống dùng cho lần sau.";
    const p = plants.data?.find((x) => x.id === id);
    if (p?.source === "pest") return "Chụp gần con sâu, côn trùng, nhện hoặc ốc, lấy nét vào con vật. Mô hình nhận ra 204 loài sâu hại và thiên địch.";
    if (p?.source === "ai") return "Cây này do AI học thêm từ ảnh của người dùng, ảnh sẽ được AI phân tích.";
    return p?.note ? `${p.note} Hệ thống sẽ nhờ AI kiểm tra thêm.` : "";
  };
  return (
    <div className="animate-fade-up">
      <PageHeader title="Tra cứu sâu bệnh" text="Chụp hoặc chọn ảnh một chiếc lá bệnh, hoặc con sâu trên cây; rõ nét, đủ sáng." />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div>
          <div className={cn("finder relative aspect-[4/3] overflow-hidden rounded-3xl border bg-card transition lg:aspect-square", mode !== "empty" && "on-media", busy && "scanning", dragging && "border-primary bg-secondary ring-4 ring-primary/20")}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); fromList(e.dataTransfer); }}>
            {mode === "empty" && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-6 text-center">
                <Leaf className="h-12 w-12 text-primary" strokeWidth={1.5} />
                <p className="text-muted-foreground">{dragging ? "Thả ảnh vào đây" : "Đặt chiếc lá hoặc con sâu vào giữa khung"}</p>
                <p className="hidden text-xs text-muted-foreground lg:block">Hoặc kéo thả ảnh vào khung, dán ảnh bằng Ctrl+V</p>
                <div className="mt-2 flex flex-wrap justify-center gap-2"><Button onClick={() => startCamera()}><Camera />Chụp ảnh</Button><Button variant="outline" onClick={() => pick(false)}><ImagePlus />Chọn ảnh có sẵn</Button></div>
              </div>
            )}
            <video ref={video} playsInline muted className={cn("absolute inset-0 h-full w-full object-cover", mode !== "camera" && "hidden")} />
            {mode === "preview" && <img src={preview} alt="Ảnh đã chọn" className="absolute inset-0 h-full w-full object-cover" />}
            {busy && <><div className="scan-grid" /><div className="scan-band" /><ScanStatus plant={plant} /></>}
          </div>
          {mode === "camera" && (
            <div className="mt-3 flex items-center justify-between">
              <Button variant="ghost" onClick={() => { stop(); setMode(file ? "preview" : "empty"); }}><X />Hủy</Button>
              <button type="button" onClick={shoot} aria-label="Chụp ảnh" className="h-[72px] w-[72px] rounded-full border-[5px] border-primary bg-card shadow-[inset_0_0_0_4px_hsl(var(--card)),inset_0_0_0_40px_hsl(var(--primary))] active:scale-95" />
              <Button variant="ghost" size="icon" aria-label="Đổi camera" onClick={() => { const f = facing === "environment" ? "user" : "environment"; setFacing(f); startCamera(f); }}><SwitchCamera /></Button>
            </div>
          )}
          {mode === "preview" && !busy && <div className="mt-3 flex gap-2"><Button variant="ghost" onClick={() => startCamera()}><Camera />Chụp lại</Button><Button variant="ghost" onClick={() => pick(false)}><ImagePlus />Chọn ảnh khác</Button></div>}
          {mode === "preview" && (
            <div className="mt-3 rounded-2xl border bg-card p-3">
              <p className="text-sm font-semibold">Ảnh thêm <span className="font-normal text-muted-foreground">(không bắt buộc, tối đa 2)</span></p>
              <p className="mt-0.5 text-xs text-muted-foreground">Chụp thêm lá bệnh khác trên cùng cây, hoặc góc khác của con sâu. Hệ thống gộp kết quả các ảnh nên chắc chắn hơn; đừng chụp lại cùng một góc.</p>
              <div className="mt-2 flex gap-2">
                {extras.map((x, i) => (
                  <div key={x.url} className="relative h-20 w-20 overflow-hidden rounded-xl border">
                    <img src={x.url} alt={`Ảnh thêm ${i + 1}`} className="h-full w-full object-cover" />
                    <span className="absolute left-1 top-1 rounded bg-black/60 px-1 text-[10px] font-bold text-white">{i + 2}</span>
                    {!busy && <button type="button" aria-label={`Bỏ ảnh ${i + 2}`} onClick={() => setExtras(extras.filter((_, j) => j !== i))}
                      className="absolute right-1 top-1 grid h-6 w-6 place-items-center rounded-full bg-black/60 text-white hover:bg-black/80"><X className="h-3.5 w-3.5" /></button>}
                  </div>
                ))}
                {extras.length < 2 && !busy && (
                  <button type="button" onClick={addExtra} className="grid h-20 w-20 place-items-center rounded-xl border-2 border-dashed text-muted-foreground transition hover:border-primary hover:text-primary">
                    <span className="flex flex-col items-center gap-1 text-[11px] font-semibold"><ImagePlus className="h-5 w-5" />Thêm ảnh</span>
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
        <div>
          <h2 className="mb-2 text-lg font-bold">Ảnh chụp gì?</h2>
          {plants.isLoading ? <Skeleton className="h-24" /> : (
            <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-2 no-scrollbar lg:mx-0 lg:flex-wrap lg:px-0" role="group" aria-label="Chọn loại cây hoặc sâu hại">
              {opts.map((o) => (
                <button key={o.id} type="button" onClick={() => setPlant(o.id)} aria-pressed={plant === o.id}
                  className={cn("inline-flex h-10 shrink-0 items-center gap-1.5 rounded-full border bg-card px-4 text-sm font-semibold transition", plant === o.id ? "border-primary bg-primary text-primary-foreground" : "hover:border-primary", o.source === "pest" && plant !== o.id && "border-paddy/60")}>
                  {o.source === "pest" ? <Bug className="h-4 w-4" /> : o.source === "ai" ? <Sparkles className="h-4 w-4 text-paddy" /> : null}{o.name}
                </button>
              ))}
            </div>
          )}
          <p className="mt-2 min-h-5 text-sm text-muted-foreground">{noteFor(plant)}</p>
          {err && <p className="mt-2 text-sm font-medium text-destructive" role="alert">{err}</p>}
          <Button size="lg" className="mt-4 w-full" disabled={!file} loading={busy} onClick={analyze}>{busy ? "Đang phân tích…" : <><RefreshCcw className="hidden" />Phân tích ảnh</>}</Button>
          <ul className="mt-6 hidden space-y-2 border-l-4 border-secondary pl-4 text-sm text-muted-foreground lg:block">
            <li>Chụp một chiếc lá có vết bệnh rõ nhất, chiếm phần lớn khung hình.</li>
            <li>Đủ sáng, tránh nắng gắt và bóng đổ; giữ máy chắc tay để ảnh nét.</li>
            <li>Nền càng đơn giản càng tốt, VD đặt lá lên tờ giấy hoặc lòng bàn tay.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
