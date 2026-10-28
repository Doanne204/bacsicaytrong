import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle, ArrowLeft, ImagePlus, Sparkles, X } from "lucide-react";
import { api, upload, ApiError, type Diagnosis, type Post } from "@/shared/lib/api";
import { pickFile, shrink } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Textarea } from "@/shared/ui/input";
import { Field, Notice } from "@/shared/ui/misc";
import { PageHeader } from "@/shared/components/common";
import { DiagCardView } from "../components/posts";

export default function NewPost() {
  const { did } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const dq = useQuery({ queryKey: ["diagnosis", did], queryFn: () => api<Diagnosis>(`/api/diagnoses/${did}`), enabled: !!did });
  const [content, setContent] = useState(""), [file, setFile] = useState<File | null>(null), [preview, setPreview] = useState("");
  const [withDiag, setWithDiag] = useState(true), [err, setErr] = useState(""), [rejected, setRejected] = useState(""), [busy, setBusy] = useState(false);
  const diag = withDiag ? dq.data : undefined;
  const addImage = async () => { const f = await pickFile(); if (f) { const s = await shrink(f); setFile(s); setPreview(URL.createObjectURL(s)); } };
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const c = content.trim();
    if (!c && !file && !diag) return setErr("Hãy viết nội dung hoặc thêm ảnh");
    const fd = new FormData(); fd.append("content", c); if (file) fd.append("image", file); if (diag) fd.append("diagnosis_id", String(diag.id));
    setBusy(true); setErr(""); setRejected("");
    try {
      const r = await upload<{ status: string; message: string; post: Post }>("/api/posts", fd);
      qc.invalidateQueries({ queryKey: ["posts"] });
      if (r.status === "approved") { toast.success("Đã đăng bài viết"); return nav("/home"); }
      if (r.status === "pending") { toast("Bài viết đang chờ duyệt"); return nav("/home/mine"); }
      setRejected(r.post.feedback || r.message);
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Không gửi được bài viết"); } finally { setBusy(false); }
  };
  return (
    <div className="mx-auto max-w-2xl animate-fade-up">
      <PageHeader
        back={<Link to={did ? `/diagnosis/${did}` : "/home"} className="mb-2 inline-flex items-center gap-1 text-sm font-semibold text-muted-foreground hover:text-primary"><ArrowLeft className="h-4 w-4" />{did ? "Kết quả tra cứu" : "Trang chủ"}</Link>}
        title={did ? "Chia sẻ kết quả tra cứu" : "Đăng bài"}
        text={did ? "Hỏi bà con kinh nghiệm xử lý, hoặc báo cho người trồng cùng loại cây biết để phòng bệnh." : "Chia sẻ kinh nghiệm, hỏi bà con về sâu bệnh hoặc khoe vụ mùa."}
      />
      <Notice icon={Sparkles} className="mb-4">AI kiểm tra bài trước khi đăng. Bài có lời lẽ thô tục, quảng cáo, lừa đảo, hình ảnh nhạy cảm hoặc không liên quan đến trồng trọt sẽ bị từ chối kèm lý do.</Notice>
      <form onSubmit={submit} noValidate className="space-y-4">
        <Field label={<span className="flex justify-between">Nội dung<span className="font-medium text-muted-foreground">{content.length}/2000</span></span>} htmlFor="content" error={err}>
          <Textarea id="content" rows={6} maxLength={2000} value={content} onChange={(e) => { setContent(e.target.value); setErr(""); }} placeholder={did ? "Ví dụ: Ruộng nhà tôi bị như ảnh, bà con đã trị bằng cách nào hiệu quả?" : "Ví dụ: Lá cà chua nhà tôi có đốm nâu viền vàng, đã phun… nhưng chưa đỡ."} />
        </Field>
        {diag && <div><DiagCardView d={{ ...diag, image_url: diag.image_url }} className="mt-0" /><Button type="button" variant="ghost" size="sm" className="mt-1" onClick={() => setWithDiag(false)}><X />Bỏ kết quả tra cứu</Button></div>}
        {file && <div className="relative"><img src={preview} alt="Ảnh sẽ đăng" className="max-h-[360px] w-full rounded-2xl object-cover" /><Button type="button" variant="secondary" size="icon-sm" className="absolute right-2 top-2 bg-black/60 text-white hover:bg-black/70" aria-label="Bỏ ảnh" onClick={() => setFile(null)}><X className="h-4 w-4" /></Button></div>}
        <Button type="button" variant="outline" onClick={addImage}><ImagePlus />{file ? "Đổi ảnh" : "Thêm ảnh"}</Button>
        {rejected && <Notice tone="danger" icon={AlertTriangle}><b>Bài viết chưa được đăng</b><p>{rejected}</p><p className="mt-1 text-muted-foreground">Sửa nội dung rồi bấm Đăng bài để gửi lại.</p></Notice>}
        <Button type="submit" size="lg" className="w-full" loading={busy}>{busy ? "AI đang kiểm duyệt…" : "Đăng bài"}</Button>
      </form>
    </div>
  );
}
