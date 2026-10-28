import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle, ArrowLeft, Bug, Clock, Database, Leaf, MessageCircle, NotebookPen, Printer, ScanLine, Share2, Sparkles, Trash2 } from "lucide-react";
import { SpeakButton } from "@/shared/components/speech";
import { TrackDialog } from "../components/journal";
import { LesionViewer } from "../components/lesion";
import { api, del, send, type Diagnosis as Diag } from "@/shared/lib/api";
import { fmtDate, fmtTime, pct, toDate } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";
import { Notice, Progress } from "@/shared/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs";
import { Textarea } from "@/shared/ui/input";
import { ConfidenceRing, ConfirmDialog, Stars } from "@/shared/components/common";
import { PageSkeleton } from "../layout/PageSkeleton";

export default function Diagnosis() {
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["diagnosis", id], queryFn: () => api<Diag>(`/api/diagnoses/${id}`) });
  const [retrying, setRetrying] = useState(false), [confirm, setConfirm] = useState(false), [track, setTrack] = useState(false);
  if (q.isLoading) return <PageSkeleton />;
  if (!q.data) return <Notice tone="danger" icon={AlertTriangle}>{(q.error as Error)?.message || "Không tìm thấy kết quả"}</Notice>;
  const d = q.data, det = d.details || {};
  const notPlant = d.plant_id === "background", unknown = d.plant_id === "unknown", pest = det.kind === "pest";
  const state = unknown ? ["Chưa xác định", "warning"] : notPlant ? ["Không nhận ra", "warning"] : pest ? (d.healthy ? ["Thiên địch có ích", "success"] : ["Sâu hại", "destructive"]) : d.healthy ? ["Khỏe mạnh", "success"] : ["Có dấu hiệu bệnh", "destructive"];
  const others = (det.top || []).filter((t) => t.raw !== d.raw);
  const modelName = pest ? "mô hình nhận diện sâu hại (INSECT204)" : "mô hình MobileNetV3";
  const source = d.source === "ai" ? ["Phân tích bởi AI Gemini", Sparkles] : d.source === "memory" ? ["Nhận ra từ dữ liệu hệ thống đã học", Database] : [unknown ? `Chưa nhận ra bằng ${modelName}` : `Nhận diện bởi ${modelName}`, pest ? Bug : Leaf];
  const SIcon = source[1] as React.ComponentType<{ className?: string }>;
  const retryMain = !pest && d.source === "model" && !!d.image_url && (unknown || !!det.ai_failed || (det.notes || []).some((n) => n.startsWith("Chưa gọi được AI")));
  const retryAlt = !pest && d.source !== "model" && !!d.image_url;
  const retry = async () => {
    setRetrying(true);
    try { await api(`/api/diagnoses/${d.id}/reanalyze`, { method: "POST" }); toast.success("Đã phân tích lại bằng AI"); q.refetch(); }
    catch (e) { toast.error((e as Error).message); } finally { setRetrying(false); }
  };
  const when = toDate(d.created);
  return (
    <div className="animate-fade-up">
      <Link to="/history" className="mb-3 inline-flex items-center gap-1 text-sm font-semibold text-muted-foreground hover:text-primary"><ArrowLeft className="h-4 w-4" />Lịch sử tra cứu</Link>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="lg:sticky lg:top-8 lg:self-start">
          <LesionViewer d={d} />
          {det.severity && (
            <section className="mt-3 rounded-2xl border bg-card p-4">
              <div className="flex items-center justify-between gap-3"><h2 className="font-bold">Mức độ bệnh ước lượng</h2><Badge variant={det.severity.level === "nhe" ? "success" : det.severity.level === "vua" ? "warning" : "destructive"}>{det.severity.label}</Badge></div>
              <div className="mt-2 flex items-center gap-3"><Progress value={Math.min(100, det.severity.pct * 100)} tone={det.severity.level === "nhe" ? "primary" : det.severity.level === "vua" ? "paddy" : "destructive"} className="flex-1" /><b className="tabular-nums">{Math.round(det.severity.pct * 100)}%</b></div>
              <p className="mt-2 text-sm">{det.severity.advice}</p>
              <p className="mt-1 text-xs text-muted-foreground">Tỉ lệ diện tích lá đổi màu (nâu, vàng, đen) so với cả lá, tính từ màu sắc (đúng phần tô hồng ở tab Vết bệnh){det.severity.photos ? `, trung bình ${det.severity.photos} ảnh` : ""}; chỉ là ước lượng, nền ảnh càng đơn giản càng đúng.</p>
            </section>
          )}
        </div>
        <div className="space-y-5">
          <section className="rounded-3xl border bg-card p-5 shadow-soft">
            <div className="flex items-start gap-4">
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-muted-foreground">{d.plant}</p>
                <h1 className="mt-0.5 text-2xl font-extrabold leading-tight md:text-3xl">{d.disease}</h1>
                <Badge variant={state[1] as "warning"} className="mt-2">{state[0]}</Badge>
              </div>
              {!unknown && <ConfidenceRing value={d.confidence} />}
            </div>
            <p className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
              <span className="inline-flex items-center gap-1.5"><SIcon className="h-4 w-4" />{source[0] as string}</span>
              <span className="inline-flex items-center gap-1.5"><Clock className="h-4 w-4" />{fmtTime(when)}, {fmtDate(when)}</span>
            </p>
          </section>
          {retryMain && <Button size="lg" className="w-full" loading={retrying} onClick={retry}><Sparkles />Phân tích lại bằng AI</Button>}
          {det.demo && <Notice tone="danger" icon={AlertTriangle}>Chế độ DEMO: chưa nạp mô hình thật, kết quả chỉ để thử giao diện.</Notice>}
          {!!det.notes?.length && <Notice tone="warn" icon={AlertTriangle}><ul>{det.notes.map((n, i) => <li key={i}>{n}</li>)}</ul></Notice>}

          <Tabs defaultValue="remedy">
            <TabsList className="w-full justify-start overflow-x-auto no-scrollbar">
              <TabsTrigger value="remedy">{pest ? (unknown ? "Nên làm gì" : d.healthy ? "Lưu ý" : "Phòng trừ") : "Cách xử lý"}</TabsTrigger>
              {(det.symptoms || det.pest) && <TabsTrigger value="info">{pest ? "Thông tin loài" : "Triệu chứng"}</TabsTrigger>}
              {others.length > 0 && <TabsTrigger value="others">Khả năng khác</TabsTrigger>}
            </TabsList>
            <TabsContent value="remedy" className="space-y-3 text-[15px] leading-relaxed">
              <p>{d.remedy}</p>
              <p className="text-sm text-muted-foreground">Kết quả chỉ mang tính tham khảo. Đọc kỹ nhãn thuốc, tuân thủ thời gian cách ly; bệnh nặng hãy hỏi cán bộ khuyến nông.</p>
            </TabsContent>
            <TabsContent value="info" className="space-y-3">
              {det.pest && (
                <dl className="divide-y rounded-2xl border bg-card">
                  {[["Tên khoa học", <i key="s">{det.pest.sci}</i>], ["Nhóm", det.pest.group_name], [det.pest.beneficial ? "Vai trò" : "Cây bị hại", det.pest.hosts]].map(([k, v]) => (
                    <div key={k as string} className="flex justify-between gap-4 px-4 py-3 text-sm"><dt className="font-semibold">{k}</dt><dd className="text-right text-muted-foreground">{v}</dd></div>
                  ))}
                </dl>
              )}
              {det.symptoms && <p className="leading-relaxed">{det.symptoms}</p>}
              {det.ai?.differential && <p className="text-sm text-muted-foreground"><b>Bệnh dễ nhầm:</b> {det.ai.differential}</p>}
            </TabsContent>
            <TabsContent value="others">
              <p className="mb-2 text-sm text-muted-foreground">{unknown ? "Mô hình đoán, chưa đủ tin cậy để xử lý theo." : "Các khả năng khác mô hình cân nhắc."}</p>
              <ul className="divide-y rounded-2xl border bg-card">{others.map((t) => <li key={t.raw} className="flex justify-between gap-4 px-4 py-3 text-sm"><b>{t.disease}</b><span className="text-muted-foreground">{t.plant}, {pct(t.prob)}</span></li>)}</ul>
            </TabsContent>
          </Tabs>

          <div className="grid gap-2 sm:grid-cols-2">
            <Button asChild size="lg" className="sm:col-span-2"><Link to={`/chat/${d.id}`}><MessageCircle />Hỏi trợ lý AI về kết quả này</Link></Button>
            {!unknown && !notPlant && <Button variant="paddy" size="lg" className="sm:col-span-2" onClick={() => setTrack(true)}><NotebookPen />Theo dõi điều trị, đặt lịch nhắc</Button>}
            {d.image_url && <Button asChild variant="outline"><Link to={`/share/${d.id}`}><Share2 />Chia sẻ lên cộng đồng</Link></Button>}
            <Button asChild variant="outline"><Link to="/scan"><ScanLine />Tra cứu ảnh khác</Link></Button>
            <Button asChild variant="outline"><Link to={`/diagnosis/${d.id}/print`}><Printer />Phiếu chẩn đoán (in / PDF)</Link></Button>
            <SpeakButton text={`${d.plant}. ${d.disease}. ${det.symptoms ? "Triệu chứng: " + det.symptoms + ". " : ""}${pest ? "Hướng phòng trừ" : "Cách xử lý"}: ${d.remedy}`} />
            {retryAlt && <Button variant="ghost" className="sm:col-span-2" loading={retrying} onClick={retry}><Sparkles />Kết quả chưa đúng? Phân tích lại bằng AI</Button>}
          </div>
          <RateBlock d={d} onSaved={() => { q.refetch(); qc.invalidateQueries({ queryKey: ["history"] }); }} />
          <Button variant="ghost" className="text-destructive hover:text-destructive" onClick={() => setConfirm(true)}><Trash2 />Xóa khỏi lịch sử</Button>
          {track && <TrackDialog open={track} onOpenChange={setTrack} diagnosis={{ id: d.id, plant: d.plant, disease: d.disease }} />}
          <ConfirmDialog open={confirm} onOpenChange={setConfirm} title="Xóa kết quả tra cứu này?" description="Cuộc trò chuyện và đánh giá kèm theo cũng bị xóa." confirmText="Xóa" danger
            onConfirm={async () => { await del(`/api/diagnoses/${d.id}`); toast.success("Đã xóa khỏi lịch sử"); qc.invalidateQueries({ queryKey: ["history"] }); nav("/history"); }} />
        </div>
      </div>
    </div>
  );
}

function RateBlock({ d, onSaved }: { d: Diag; onSaved: () => void }) {
  const [stars, setStars] = useState(d.rating?.stars || 0), [comment, setComment] = useState(d.rating?.comment || ""), [busy, setBusy] = useState(false);
  const save = async () => {
    if (!stars) return toast.error("Hãy chọn số sao");
    setBusy(true);
    try { await send("/api/rating", { diagnosis_id: d.id, stars, comment }); toast.success("Đã lưu đánh giá"); onSaved(); }
    catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <section className="rounded-3xl border bg-card p-5">
      <h2 className="font-bold">Kết quả này có đúng không?</h2>
      <p className="text-sm text-muted-foreground">Chấm sao để giúp hệ thống chính xác hơn.</p>
      <Stars value={stars} onChange={setStars} size="lg" className="my-3" />
      <Textarea rows={2} maxLength={500} placeholder="Nhận xét thêm (không bắt buộc)" value={comment} onChange={(e) => setComment(e.target.value)} />
      <Button variant="secondary" className="mt-3" loading={busy} onClick={save}>{d.rating ? "Cập nhật đánh giá" : "Gửi đánh giá"}</Button>
    </section>
  );
}
