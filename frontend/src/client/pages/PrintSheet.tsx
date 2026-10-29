import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import QRCode from "qrcode";
import { ArrowLeft, Printer } from "lucide-react";
import { api, type Diagnosis } from "@/shared/lib/api";
import { fmtDate, fmtTime, pct, toDate } from "@/shared/lib/utils";
import { useMe } from "@/shared/hooks/use-me";
import { Button } from "@/shared/ui/button";
import { Logo } from "@/shared/components/brand";
import { PageSkeleton } from "../layout/PageSkeleton";

/** Phiếu chẩn đoán để in ra giấy hoặc lưu PDF (Ctrl+P -> Lưu dưới dạng PDF); mã QR mở lại kết quả trong ứng dụng. */
export default function PrintSheet() {
  const { id } = useParams();
  const { me } = useMe();
  const q = useQuery({ queryKey: ["diagnosis", id], queryFn: () => api<Diagnosis>(`/api/diagnoses/${id}`) });
  const [qr, setQr] = useState("");
  const url = `${location.origin}/diagnosis/${id}`;
  useEffect(() => { QRCode.toDataURL(url, { width: 220, margin: 1, color: { dark: "#1F4A28" } }).then(setQr); }, [url]);
  if (q.isLoading) return <PageSkeleton full />;
  if (!q.data) return <p className="p-8">Không tìm thấy kết quả.</p>;
  const d = q.data, det = d.details || {}, pest = det.kind === "pest", when = toDate(d.created);
  const unknown = d.plant_id === "unknown" || d.plant_id === "background";
  const state = unknown ? "Chưa xác định" : pest ? (d.healthy ? "Thiên địch có ích" : "Sâu hại") : d.healthy ? "Khỏe mạnh" : "Có dấu hiệu bệnh";
  return (
    <div className="min-h-dvh bg-muted print:bg-white">
      <div className="mx-auto flex max-w-[210mm] items-center gap-2 px-4 py-3 print:hidden">
        <Button asChild variant="ghost"><Link to={`/diagnosis/${id}`}><ArrowLeft />Quay lại</Link></Button>
        <span className="flex-1 text-sm text-muted-foreground">Bấm In rồi chọn "Lưu dưới dạng PDF" nếu muốn lưu file.</span>
        <Button onClick={() => window.print()}><Printer />In / Lưu PDF</Button>
      </div>
      <article className="mx-auto max-w-[210mm] bg-white p-8 text-[#33291F] shadow-soft print:max-w-none print:p-0 print:shadow-none">
        <header className="flex items-center gap-3 border-b-2 border-[#2F6B3A] pb-4">
          <Logo size={48} />
          <div className="flex-1"><h1 className="text-xl font-extrabold text-[#2F6B3A]">PHIẾU CHẨN ĐOÁN SÂU BỆNH CÂY TRỒNG</h1><p className="text-sm text-[#6B6358]">Bác sĩ cây trồng · ứng dụng nhận diện sâu bệnh bằng AI</p></div>
          <div className="text-right text-xs text-[#6B6358]"><div>Số phiếu: #{d.id}</div><div>{fmtTime(when)}, {fmtDate(when)}</div><div>Người tra cứu: {me?.username}</div></div>
        </header>
        <div className="mt-5 grid grid-cols-[1fr_1.2fr] gap-6">
          {d.image_url ? <img src={d.image_url} alt="Ảnh đã tra cứu" className="aspect-square w-full rounded-lg border object-cover" /> : <div className="aspect-square rounded-lg border bg-muted" />}
          <div>
            <p className="text-sm font-semibold text-[#6B6358]">{pest ? "Loài nhận diện" : d.plant}</p>
            <h2 className="text-2xl font-extrabold leading-tight">{d.disease}</h2>
            <p className="mt-1 text-sm"><b>Trạng thái:</b> {state}{!unknown && <> · <b>Độ tin cậy:</b> {pct(d.confidence)}</>}</p>
            <p className="text-sm"><b>Nguồn:</b> {d.source === "ai" ? "Hệ thống phân tích" : d.source === "memory" ? "Dữ liệu hệ thống đã học" : pest ? "Mô hình nhận diện sâu hại YOLO11m (INSECT204)" : "Mô hình MobileNetV3 (PlantVillage)"}</p>
            {det.pest && <dl className="mt-2 text-sm"><div><b>Tên khoa học:</b> <i>{det.pest.sci}</i></div><div><b>Nhóm:</b> {det.pest.group_name}</div><div><b>{det.pest.beneficial ? "Vai trò" : "Cây bị hại"}:</b> {det.pest.hosts}</div></dl>}
            {det.symptoms && <p className="mt-2 text-sm"><b>Triệu chứng:</b> {det.symptoms}</p>}
            {!!det.top?.length && !unknown && <p className="mt-2 text-xs text-[#6B6358]"><b>Khả năng khác:</b> {det.top.filter((t) => t.raw !== d.raw).slice(0, 2).map((t) => `${t.disease} (${pct(t.prob)})`).join(", ")}</p>}
          </div>
        </div>
        <section className="mt-5"><h3 className="font-bold text-[#2F6B3A]">{pest ? (d.healthy ? "Lưu ý" : "Hướng phòng trừ") : "Hướng xử lý"}</h3><p className="mt-1 text-[15px] leading-relaxed">{d.remedy}</p></section>
        <footer className="mt-6 flex items-end justify-between gap-4 border-t pt-4">
          <div className="text-xs text-[#6B6358]">
            <p>Kết quả do máy tính nhận diện, chỉ mang tính tham khảo. Hãy mang phiếu này tới đại lý vật tư nông nghiệp hoặc cán bộ khuyến nông để được tư vấn; đọc kỹ nhãn thuốc, tuân thủ liều lượng và thời gian cách ly.</p>
            <p className="mt-2">Quét mã QR để mở lại kết quả trong ứng dụng (cần đăng nhập tài khoản đã tra cứu).</p>
            <div className="mt-6 grid grid-cols-2 gap-8 text-center"><div>Người tra cứu<br /><br /><br />{me?.username}</div><div>Cán bộ tư vấn<br /><br /><br />(ký, ghi rõ họ tên)</div></div>
          </div>
          {qr && <img src={qr} alt="Mã QR mở kết quả" className="h-28 w-28 shrink-0" />}
        </footer>
      </article>
    </div>
  );
}
