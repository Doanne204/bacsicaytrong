import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Clock, MessageCircle, ScanLine, User } from "lucide-react";
import { api } from "@/shared/lib/api";
import { fmtDate, fmtTime, toDate } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";
import { Notice } from "@/shared/ui/misc";
import { ConfidenceRing } from "@/shared/components/common";
import { PageSkeleton } from "../layout/PageSkeleton";

interface Shared { post_id: number; username: string; is_mine: boolean; diagnosis_id: number; plant: string; plant_id: string; disease: string; healthy: boolean; confidence: number; remedy: string; symptoms: string; differential: string; image_url: string | null; created: string }

/** Chi tiết kết quả tra cứu được chia sẻ trong bài viết (chỉ đọc). */
export default function SharedResult() {
  const { id } = useParams();
  const q = useQuery({ queryKey: ["shared", id], queryFn: () => api<Shared>(`/api/posts/${id}/result`) });
  if (q.isLoading) return <PageSkeleton />;
  if (!q.data) return <Notice tone="danger">{(q.error as Error)?.message || "Không tìm thấy kết quả"}</Notice>;
  const r = q.data, unknown = r.plant_id === "unknown" || r.plant_id === "background";
  const state = unknown ? ["Chưa xác định", "warning"] : r.healthy ? ["Khỏe mạnh", "success"] : ["Có dấu hiệu bệnh", "destructive"];
  const when = toDate(r.created);
  return (
    <div className="animate-fade-up">
      <Link to={`/p/${id}`} className="mb-3 inline-flex items-center gap-1 text-sm font-semibold text-muted-foreground hover:text-primary"><ArrowLeft className="h-4 w-4" />Bài viết của {r.username}</Link>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div>{r.image_url && <img src={r.image_url} alt="Ảnh đã tra cứu" className="aspect-[4/3] w-full rounded-3xl bg-secondary object-cover lg:aspect-square" />}</div>
        <div className="space-y-5">
          <section className="rounded-3xl border bg-card p-5 shadow-soft">
            <div className="flex items-start gap-4">
              <div className="min-w-0 flex-1"><p className="font-semibold text-muted-foreground">{r.plant}</p><h1 className="mt-0.5 text-2xl font-extrabold md:text-3xl">{r.disease}</h1><Badge variant={state[1] as "warning"} className="mt-2">{state[0]}</Badge></div>
              {!unknown && <ConfidenceRing value={r.confidence} />}
            </div>
            <p className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground"><span className="inline-flex items-center gap-1.5"><User className="h-4 w-4" />Tra cứu bởi {r.username}</span><span className="inline-flex items-center gap-1.5"><Clock className="h-4 w-4" />{fmtTime(when)}, {fmtDate(when)}</span></p>
          </section>
          {r.symptoms && <section><h2 className="mb-1 font-bold">Triệu chứng nhìn thấy</h2><p className="leading-relaxed">{r.symptoms}</p>{r.differential && <p className="mt-1 text-sm text-muted-foreground"><b>Bệnh dễ nhầm:</b> {r.differential}</p>}</section>}
          <section><h2 className="mb-1 font-bold">Cách xử lý</h2><p className="leading-relaxed">{r.remedy}</p><p className="mt-2 text-sm text-muted-foreground">Kết quả chỉ mang tính tham khảo. Đọc kỹ nhãn thuốc, tuân thủ thời gian cách ly; bệnh nặng hãy hỏi cán bộ khuyến nông.</p></section>
          <div className="grid gap-2 sm:grid-cols-2">
            <Button asChild size="lg" className="sm:col-span-2"><Link to={`/p/${id}`}><MessageCircle />Xem bài viết và bình luận</Link></Button>
            {r.is_mine && <Button asChild variant="outline"><Link to={`/diagnosis/${r.diagnosis_id}`}><Clock />Mở trong lịch sử của tôi</Link></Button>}
            <Button asChild variant="outline"><Link to="/scan"><ScanLine />Tra cứu lá cây của tôi</Link></Button>
          </div>
        </div>
      </div>
    </div>
  );
}
