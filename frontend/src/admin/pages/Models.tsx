import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bug, Leaf, Scale } from "lucide-react";
import { api } from "@/shared/lib/api";
import { cn } from "@/shared/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";
import { Badge } from "@/shared/ui/badge";
import { Notice, Skeleton } from "@/shared/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs";
import { DataTable } from "../components/table";

interface PerClass { name: string; precision: number; recall: number; f1: number; support?: number; test?: number; label?: string }
interface Models {
  leaf: { overall: Record<string, number>; per_class: PerClass[]; images: string[]; trained: string; reevaluated?: Reevaluated } | null;
  pest: { classes: number; images: Record<string, number>; accuracy: number; top5: number; macro_f1: number; finetune: number; architecture: string; trained: string;
    worst: (PerClass & { label: string })[]; confused: { true_label: string; pred_label: string; n: number }[]; per_class: (PerClass & { label: string })[] } | null;
  compare: { rows: CompareRow[]; chart: boolean; trained: string } | null;
  model_loaded: boolean; pest_loaded: boolean; class_count: number; pest_class_count: number;
}
interface Reevaluated {
  model: string; model_time: string; evaluated: string; train_test_gap: number | null;
  subsets: Partial<Record<"train" | "val" | "test", { accuracy: number; macro_f1: number; images: number }>>;
}
interface CompareRow {
  arch: string; name: string; accuracy: number; top3: number | null; macro_f1: number; weighted_f1: number | null; params_m: number; size_mb: number; cpu_ms: number;
  batch_ms: number | null; train_min: number; epochs: number; best_val_acc: number | null; test_images: number; classes: number; image: boolean;
}
const num = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "–" : v.toFixed(d).replace(".", ","));
const pct = (v?: number) => (v === undefined || v === null ? "–" : `${(v * 100).toFixed(1).replace(".", ",")}%`);
const f1Badge = (f: number) => <Badge variant={f >= 0.8 ? "success" : f >= 0.5 ? "warning" : "destructive"}>{f.toFixed(2)}</Badge>;

/** Trang đánh giá mô hình: số liệu từ results/ do train.py và train_pests.py ghi ra (tập test chưa dùng khi học). */
export default function Models() {
  const q = useQuery({ queryKey: ["admin", "models"], queryFn: () => api<Models>("/api/admin/models") });
  const [search, setSearch] = useState("");
  if (!q.data) return <Skeleton className="h-96" />;
  const m = q.data;
  const filt = <T extends PerClass>(rows: T[]) => rows.filter((r) => `${r.name} ${r.label || ""}`.toLowerCase().includes(search.toLowerCase()));
  const cols = (labelKey: "label" | "name") => [
    { key: "name", header: "Lớp", cell: (r: PerClass) => <><b>{labelKey === "label" ? r.label : r.name}</b>{labelKey === "label" && <span className="block text-xs text-muted-foreground">{r.name}</span>}</>, sort: (r: PerClass) => r.name },
    { key: "p", header: "Precision", cell: (r: PerClass) => pct(r.precision), sort: (r: PerClass) => r.precision, className: "tabular-nums" },
    { key: "r", header: "Recall", cell: (r: PerClass) => pct(r.recall), sort: (r: PerClass) => r.recall, className: "tabular-nums" },
    { key: "f1", header: "F1", cell: (r: PerClass) => f1Badge(r.f1), sort: (r: PerClass) => r.f1 },
    { key: "n", header: "Ảnh test", cell: (r: PerClass) => r.support ?? r.test ?? "", sort: (r: PerClass) => r.support ?? r.test ?? 0, className: "tabular-nums", hide: "sm" as const },
  ];
  return (
    <div className="space-y-5 animate-fade-up">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex items-center gap-3 rounded-2xl border bg-card p-4"><Leaf className="h-6 w-6 text-primary" /><div><b>Mô hình bệnh lá</b><p className="text-sm text-muted-foreground">MobileNetV3Large, {m.class_count} lớp · {m.model_loaded ? "đang chạy" : "chưa nạp (chế độ DEMO)"}</p></div></div>
        <div className="flex items-center gap-3 rounded-2xl border bg-card p-4"><Bug className="h-6 w-6 text-primary" /><div><b>Mô hình sâu hại</b><p className="text-sm text-muted-foreground">{m.pest?.architecture || "YOLO11m-cls"} + INSECT204, {m.pest_class_count} lớp · {m.pest_loaded ? "đang chạy" : "chưa nạp"}</p></div></div>
      </div>
      <Tabs defaultValue={m.leaf ? "leaf" : "pest"}>
        <TabsList><TabsTrigger value="leaf"><Leaf />Bệnh lá</TabsTrigger><TabsTrigger value="pest"><Bug />Sâu hại</TabsTrigger><TabsTrigger value="compare"><Scale />So sánh kiến trúc</TabsTrigger></TabsList>
        <TabsContent value="compare" className="space-y-4">
          {!m.compare ? <Notice tone="warn">Chưa có <b>results/compare/summary.csv</b>. Mở <code className="rounded bg-muted px-1">notebooks/so_sanh_kien_truc.ipynb</code> trên Google Colab (GPU) để huấn luyện MobileNetV3Large, EfficientNet-B0 và ViT-B/16 trên cùng dữ liệu, rồi giải nén kết quả vào <b>results/compare/</b>. Chạy tại máy: <code className="rounded bg-muted px-1">python compare_models.py --all --data dataset/…</code>.</Notice> : (
            <>
              <p className="text-sm text-muted-foreground">Cùng dữ liệu, cùng cách chia 70/15/15, cùng augmentation và quy trình 2 giai đoạn; đánh giá trên {m.compare.rows[0].test_images.toLocaleString("vi-VN")} ảnh test, {m.compare.rows[0].classes} lớp. Thời gian suy luận đo từng ảnh trên CPU. Chạy lúc {m.compare.trained}.</p>
              <div className="overflow-x-auto rounded-2xl border bg-card">
                <table className="w-full min-w-[720px] text-sm">
                  <thead className="bg-muted/60 text-left text-xs uppercase text-muted-foreground"><tr>{["Kiến trúc", "Accuracy", "Top-3", "Macro-F1", "Tham số (triệu)", "Dung lượng", "CPU ms/ảnh", "Huấn luyện", "Val tốt nhất"].map((h) => <th key={h} className="px-3 py-2.5 font-semibold">{h}</th>)}</tr></thead>
                  <tbody className="divide-y">
                    {m.compare.rows.map((r) => {
                      const best = Math.max(...m.compare!.rows.map((x) => x.accuracy)) === r.accuracy;
                      return (
                        <tr key={r.arch} className={cn(r.arch === "mobilenetv3" && "bg-secondary/40")}>
                          <td className="px-3 py-2.5 font-semibold">{r.name}{r.arch === "mobilenetv3" && <span className="ml-2 text-xs font-normal text-muted-foreground">đang dùng</span>}</td>
                          <td className="px-3 py-2.5 tabular-nums">{pct(r.accuracy)}{best && <Badge variant="success" className="ml-1.5">cao nhất</Badge>}</td>
                          <td className="px-3 py-2.5 tabular-nums">{r.top3 === null ? "–" : pct(r.top3)}</td>
                          <td className="px-3 py-2.5 tabular-nums">{r.macro_f1.toFixed(3)}</td>
                          <td className="px-3 py-2.5 tabular-nums">{num(r.params_m, 2)}</td>
                          <td className="px-3 py-2.5 tabular-nums">{num(r.size_mb)} MB</td>
                          <td className="px-3 py-2.5 tabular-nums">{num(r.cpu_ms)}</td>
                          <td className="px-3 py-2.5 tabular-nums">{num(r.train_min)} phút, {r.epochs} epoch</td>
                          <td className="px-3 py-2.5 tabular-nums">{r.best_val_acc === null ? "–" : pct(r.best_val_acc)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {m.compare.chart && <Card><CardHeader><CardTitle className="text-sm">Accuracy, tốc độ CPU và số tham số</CardTitle></CardHeader><CardContent><img src="/api/admin/results/compare/summary.png" alt="Biểu đồ so sánh" className="w-full rounded-lg border bg-white" /></CardContent></Card>}
              <div className="grid gap-4 lg:grid-cols-3">{m.compare.rows.filter((r) => r.image).map((r) => <Card key={r.arch}><CardHeader><CardTitle className="text-sm">Ma trận nhầm lẫn: {r.name}</CardTitle></CardHeader><CardContent><img src={`/api/admin/results/compare/${r.arch}/confusion_matrix.png`} alt={r.name} loading="lazy" className="w-full rounded-lg border bg-white" /></CardContent></Card>)}</div>
            </>
          )}
        </TabsContent>
        <TabsContent value="leaf" className="space-y-4">
          {!m.leaf ? <Notice tone="warn">Chưa có kết quả đánh giá: chạy <code className="rounded bg-muted px-1">python train.py --data dataset/…</code> trên máy có GPU (hoặc Colab) rồi chép thư mục <b>results/</b> và <b>models/</b> về. Mô hình hiện tại được huấn luyện nơi khác nên thiếu file số liệu.</Notice> : (
            <>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                {Object.entries(m.leaf.overall).map(([k, v]) => <div key={k} className="rounded-2xl border bg-card p-4"><span className="text-xs uppercase text-muted-foreground">{k.replace(/_/g, " ")}</span><b className="block text-2xl">{v <= 1 ? pct(v) : v}</b></div>)}
              </div>
              {m.leaf.reevaluated ? (
                <Notice tone="warn">
                  <p><b>Đánh giá lại sau khi huấn luyện</b> (evaluate_leaf.py, {m.leaf.reevaluated.evaluated}) cho mô hình <code className="rounded bg-muted px-1">{m.leaf.reevaluated.model}</code> (lưu lúc {m.leaf.reevaluated.model_time}). Tập test chia giống train.py (15%, stratified, seed 42), nhưng không chắc mô hình chưa học các ảnh này, nên số liệu có thể cao hơn thực tế.</p>
                  <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1">{(["train", "val", "test"] as const).filter((k) => m.leaf!.reevaluated!.subsets[k]).map((k) => { const s = m.leaf!.reevaluated!.subsets[k]!; return <span key={k}><b>{{ train: "Train", val: "Val", test: "Test" }[k]}</b>: {pct(s.accuracy)} ({s.images.toLocaleString("vi-VN")} ảnh)</span>; })}</p>
                  {m.leaf.reevaluated.train_test_gap !== null && <p className="mt-1">Chênh lệch train - test: {(m.leaf.reevaluated.train_test_gap * 100).toFixed(2).replace(".", ",")} điểm %{Math.abs(m.leaf.reevaluated.train_test_gap) < 0.005 ? " (gần như bằng nhau, nên không xác định được ảnh test đã được học hay chưa)." : "."} Số liệu chuẩn cho báo cáo: xem tab So sánh kiến trúc (huấn luyện lại có tập test riêng).</p>}
                </Notice>
              ) : <p className="text-sm text-muted-foreground">Đánh giá trên tập test (15% ảnh, chia stratified theo lớp, không dùng khi học). Huấn luyện lúc {m.leaf.trained}.</p>}
              <div className="grid gap-4 lg:grid-cols-2">{m.leaf.images.map((f) => <Card key={f}><CardHeader><CardTitle className="text-sm">{({ "confusion_matrix.png": "Ma trận nhầm lẫn", "class_metrics.png": "Precision / Recall / F1 từng lớp", "training_accuracy.png": "Accuracy theo epoch", "training_loss.png": "Loss theo epoch",
                "gradcam_examples.png": "Grad-CAM: ca dự đoán đúng trên tập test", "gradcam_errors.png": "Grad-CAM: ca dự đoán sai (lớp đoán và lớp đúng)" } as Record<string, string>)[f] || f}</CardTitle></CardHeader><CardContent><img src={`/api/admin/results/${f}`} alt={f} className="w-full rounded-lg border bg-white" /></CardContent></Card>)}</div>
              <DataTable rows={filt(m.leaf.per_class)} keyOf={(r) => r.name} columns={cols("name")} pageSize={20} search={search} onSearch={setSearch} searchPlaceholder="Tìm lớp…" empty={<p className="p-6 text-sm text-muted-foreground">Không có lớp nào.</p>} />
            </>
          )}
        </TabsContent>
        <TabsContent value="pest" className="space-y-4">
          {!m.pest ? <Notice tone="warn">Chưa có results/pest_metrics.json: chạy <code className="rounded bg-muted px-1">python train_pests.py --data …</code>.</Notice> : (
            <>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                {[["Accuracy (top-1)", pct(m.pest.accuracy)], ["Top-5", pct(m.pest.top5)], ["Macro-F1", m.pest.macro_f1.toFixed(3)], ["Ảnh test", m.pest.images.test?.toLocaleString("vi-VN")]].map(([k, v]) => <div key={k as string} className="rounded-2xl border bg-card p-4"><span className="text-xs uppercase text-muted-foreground">{k}</span><b className="block text-2xl">{v as string}</b></div>)}
              </div>
              <p className="text-sm text-muted-foreground">{m.pest.classes} loài; train {m.pest.images.train?.toLocaleString("vi-VN")}, val {m.pest.images.val?.toLocaleString("vi-VN")}, test {m.pest.images.test?.toLocaleString("vi-VN")} ảnh (tỉ lệ 6:1:3 như bài báo INSECT204, đã bỏ ảnh trùng). {m.pest.architecture.startsWith("YOLO") ? `${m.pest.architecture} (Ultralytics) huấn luyện trên GPU, chạy trong app bằng ONNX trên CPU.` : m.pest.finetune ? `MobileNetV3Large tinh chỉnh ${m.pest.finetune} epoch.` : "Chỉ học lớp phân loại trên vector MobileNetV3 ImageNet."} Kết quả đánh giá ghi lúc {m.pest.trained}.</p>
              <div className="grid gap-4 lg:grid-cols-2">
                <Card><CardHeader><CardTitle>Nhầm lẫn nhiều nhất</CardTitle><CardDescription>Cặp (loài đúng → loài dự đoán) hay sai nhất trên tập test.</CardDescription></CardHeader>
                  <CardContent><ul className="divide-y text-sm">{m.pest.confused.slice(0, 10).map((c, i) => <li key={i} className="flex items-center gap-2 py-2"><span className="min-w-0 flex-1 truncate">{c.true_label}</span><span className="text-muted-foreground">→</span><span className="min-w-0 flex-1 truncate">{c.pred_label}</span><b className="tabular-nums">{c.n}</b></li>)}</ul></CardContent></Card>
                <Card><CardHeader><CardTitle>Lớp yếu nhất</CardTitle><CardDescription>F1 thấp nhất; thường là loài ít ảnh hoặc trùng họ với lớp khác.</CardDescription></CardHeader>
                  <CardContent><ul className="divide-y text-sm">{m.pest.worst.slice(0, 10).map((w) => <li key={w.name} className="flex items-center gap-2 py-2"><span className="min-w-0 flex-1 truncate">{w.label}</span><span className={cn("text-xs text-muted-foreground")}>{w.test} ảnh</span>{f1Badge(w.f1)}</li>)}</ul></CardContent></Card>
              </div>
              <DataTable rows={filt(m.pest.per_class)} keyOf={(r) => r.name} columns={cols("label")} pageSize={20} search={search} onSearch={setSearch} searchPlaceholder="Tìm loài…" empty={<p className="p-6 text-sm text-muted-foreground">Không có lớp nào.</p>} />
            </>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
