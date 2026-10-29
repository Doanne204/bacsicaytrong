import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, Camera, ImagePlus, Leaf, RotateCcw, Send, X } from "lucide-react";
import { api, send, upload, type ChatMsg, type Diagnosis } from "@/shared/lib/api";
import { cn, fmtTime, liveCamera, pct, pickFile, shrink, toDate } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Skeleton } from "@/shared/ui/misc";
import { MicButton, SpeakButton } from "@/shared/components/speech";

const SOURCE: Record<string, string> = { gemini: "Trả lời bởi Gemini", claude: "Trả lời bởi Claude", offline: "Trả lời tự động (chưa kết nối AI)" };
type Msg = ChatMsg & { failed?: boolean; file?: File; fresh?: boolean };

/** Làm sạch câu trả lời của AI (kể cả tin nhắn cũ đã lưu trước khi máy chủ lọc): bỏ dấu ngoặc kép, dòng "* " thành gạch đầu dòng. */
export const noQuotes = (t: string) => t.replace(/^(\s*)\*\s+/gm, "$1- ").replace(/["“”„«»]/g, "").replace(/[ \t]{2,}/g, " ");
/** Văn bản không còn dấu * (để đọc thành tiếng). */
export const plainText = (t: string) => noQuotes(t).replace(/\*/g, "");

/** Phần trong **...** hoặc *...* hiện thành chữ in đậm; dấu * lẻ (chưa đóng, VD khi đang hiện dần từng chữ) bị bỏ. */
function Inline({ t }: { t: string }) {
  const out: React.ReactNode[] = [];
  const re = /\*\*(.+?)\*\*|\*(?!\s)([^*\n]+?)\*/g;
  let last = 0, m: RegExpExecArray | null;
  while ((m = re.exec(t))) {
    if (m.index > last) out.push(t.slice(last, m.index).replace(/\*/g, ""));
    out.push(<b key={m.index} className="font-bold">{m[1] ?? m[2]}</b>);
    last = re.lastIndex;
  }
  if (last < t.length) out.push(t.slice(last).replace(/\*/g, ""));
  return <>{out}</>;
}

/** Văn bản từ AI -> đoạn, danh sách gạch đầu dòng, chữ in đậm. */
function Rich({ t }: { t: string }) {
  const blocks = noQuotes(t).replace(/\r/g, "").split(/\n{2,}/);
  return (
    <>
      {blocks.map((b, i) => {
        const lines = b.split("\n");
        if (lines.length > 1 && lines.every((l) => /^\s*[-•]\s+/.test(l))) return <ul key={i} className="my-1 list-disc space-y-1 pl-5">{lines.map((l, j) => <li key={j}><Inline t={l.replace(/^\s*[-•]\s+/, "")} /></li>)}</ul>;
        return <p key={i} className="my-1 whitespace-pre-wrap"><Inline t={b} /></p>;
      })}
    </>
  );
}

/** Hiệu ứng đang soạn câu trả lời: 3 chấm nhảy và dòng chữ đổi theo thời gian chờ (có ảnh thì báo đang xem ảnh). */
function Typing({ withImage }: { withImage: boolean }) {
  const [t, setT] = useState(0);
  useEffect(() => { const id = setInterval(() => setT((x) => x + 1), 1000); return () => clearInterval(id); }, []);
  const text = withImage ? (t < 3 ? "Đang xem ảnh" : t < 8 ? "Đang phân tích vết bệnh trên ảnh" : "Sắp xong, chờ chút nhé")
    : t < 2 ? "Trợ lý đang suy nghĩ" : t < 6 ? "Đang soạn câu trả lời" : "Câu hỏi hơi dài, chờ chút nhé";
  return (
    <div className="mb-3 flex items-end gap-2" role="status" aria-live="polite">
      <span className="relative grid h-8 w-8 shrink-0 place-items-center rounded-[10px_4px_10px_4px] bg-primary text-primary-foreground">
        <Leaf className="h-4 w-4" /><span className="absolute inset-0 animate-ping rounded-[10px_4px_10px_4px] bg-primary/40" />
      </span>
      <div className="rounded-2xl rounded-bl-md border bg-card px-4 py-3">
        <span className="flex items-center gap-1.5" aria-hidden>
          {[0, 1, 2].map((i) => <i key={i} className="h-2 w-2 rounded-full bg-primary" style={{ animation: "chat-dot 1.2s ease-in-out infinite", animationDelay: `${i * 0.18}s` }} />)}
        </span>
        <span className="mt-1.5 block text-xs text-muted-foreground">{text}…</span>
      </div>
    </div>
  );
}

/** Câu trả lời mới hiện dần từng chữ như đang gõ (tối đa ~2,5 giây), xong thì hiển thị đầy đủ định dạng. */
function TypeOut({ t, onTick, onDone }: { t: string; onTick: () => void; onDone: () => void }) {
  const [n, setN] = useState(0);
  useEffect(() => {
    const step = Math.max(2, Math.ceil(t.length / 120));  // ~120 nhịp x 20 ms
    const id = setInterval(() => setN((x) => { const v = Math.min(t.length, x + step); if (v >= t.length) clearInterval(id); return v; }), 20);
    return () => clearInterval(id);
  }, [t]);
  useEffect(() => { onTick(); if (n >= t.length) onDone(); }, [n]);  // eslint-disable-line react-hooks/exhaustive-deps
  if (n >= t.length) return <Rich t={t} />;
  return <p className="my-1 whitespace-pre-wrap"><Inline t={noQuotes(t).slice(0, n)} /><span className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 bg-primary" style={{ animation: "chat-caret 0.8s step-end infinite" }} /></p>;
}

export default function Chat() {
  const { id } = useParams();
  const diag = useQuery({ queryKey: ["diagnosis", id], queryFn: () => api<Diagnosis>(`/api/diagnoses/${id}`), enabled: !!id });
  const hist = useQuery({ queryKey: ["chat", id || "general"], queryFn: () => api<ChatMsg[]>("/api/chat" + (id ? `?diagnosis_id=${id}` : "")) });
  const [params] = useSearchParams();  // ?q=: câu hỏi soạn sẵn (VD từ Thư viện sâu bệnh), người dùng bấm gửi
  const [msgs, setMsgs] = useState<Msg[]>([]), [text, setText] = useState(params.get("q")?.slice(0, 1000) || ""), [busy, setBusy] = useState(false);
  const [img, setImg] = useState<File | null>(null), [imgUrl, setImgUrl] = useState(""), [dragging, setDragging] = useState(false);
  const [pendingImage, setPendingImage] = useState(false);
  const toBottom = () => log.current?.scrollTo({ top: log.current.scrollHeight });
  const log = useRef<HTMLDivElement>(null), ta = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { if (hist.data) setMsgs(hist.data); }, [hist.data]);
  useEffect(() => { log.current?.scrollTo({ top: log.current.scrollHeight, behavior: "smooth" }); }, [msgs, busy]);
  const attach = async (f: File | null) => { if (!f) return; const s = await shrink(f); setImg(s); setImgUrl(URL.createObjectURL(s)); ta.current?.focus(); };
  const fromList = (list?: DataTransfer | null) => {
    const f = [...(list?.files || [])].find((x) => x.type.startsWith("image/"))
      || [...(list?.items || [])].map((i) => (i.kind === "file" && i.type.startsWith("image/") ? i.getAsFile() : null)).find(Boolean);
    if (f) attach(f);
    return !!f;
  };
  useEffect(() => {  // dán ảnh (Ctrl+V) ở bất kỳ đâu trong trang chat
    const onPaste = (e: ClipboardEvent) => { if (fromList(e.clipboardData)) e.preventDefault(); };
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const d = diag.data, pest = d?.details?.kind === "pest";
  const suggestions = d
    ? pest ? (d.healthy ? ["Loài này ăn những sâu hại nào?", "Làm sao bảo vệ thiên địch trên ruộng?", "Phun thuốc nào ít hại thiên địch?"] : ["Loài này gây hại thế nào?", "Cách phòng trừ sinh học?", "Khi nào mới cần phun thuốc?", "Vòng đời và thời điểm phát sinh?"])
      : d.healthy ? ["Làm sao giữ cây khỏe?", "Lịch bón phân hợp lý?", "Dấu hiệu bệnh cần theo dõi?"] : ["Nên phun thuốc gì?", "Bệnh có lây sang cây khác không?", "Cách phòng bệnh cho vụ sau?", "Bao lâu cây hồi phục?"]
    : ["Cách nhận biết cây thiếu dinh dưỡng?", "Trồng cà chua mùa mưa cần lưu ý gì?", "Thuốc sinh học trị nấm phổ biến?"];
  const ask = async (m: string, file: File | null = img, retryIndex?: number) => {
    const content = m.trim();
    if ((!content && !file) || busy) return;
    setText(""); setImg(null); setImgUrl(""); setBusy(true); setPendingImage(!!file);
    const shown = content || "Hãy xem ảnh này và cho tôi biết cây có bị gì không, cách xử lý ra sao.";
    setMsgs((cur) => retryIndex !== undefined ? cur.map((x, i) => (i === retryIndex ? { ...x, failed: false } : x))
      : [...cur, { role: "user", content: shown, image_url: file ? URL.createObjectURL(file) : null, file: file || undefined }]);
    try {
      let r: { reply: string; source: string };
      if (file) {
        const fd = new FormData(); fd.append("message", content); fd.append("image", file); if (id) fd.append("diagnosis_id", id);
        r = await upload("/api/chat", fd);
      } else r = await send("/api/chat", { message: content, diagnosis_id: id ? +id : null });
      setMsgs((cur) => [...cur, { role: "assistant", content: r.reply, source: r.source, fresh: true }]);
    } catch (e) {
      setMsgs((cur) => cur.map((x, i) => (i === cur.length - 1 && x.role === "user" ? { ...x, failed: true } : x)));
      toast.error((e as Error).message);
    } finally { setBusy(false); ta.current?.focus(); }
  };
  const autosize = () => { const t = ta.current; if (t) { t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 140) + "px"; } };
  return (
    <div className="flex h-[calc(100dvh-3.5rem)] flex-col lg:h-dvh" onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(e) => { e.preventDefault(); setDragging(false); fromList(e.dataTransfer); }}>
      <header className="flex items-center gap-3 border-b bg-card px-3 py-2.5 lg:px-6">
        <Button asChild variant="ghost" size="icon-sm" aria-label="Quay lại"><Link to={id ? `/diagnosis/${id}` : "/home"}><ArrowLeft className="h-5 w-5" /></Link></Button>
        {d?.image_url ? <img src={d.image_url} alt="" className="h-11 w-11 rounded-xl object-cover" /> : <span className="grid h-11 w-11 place-items-center rounded-[12px_4px_12px_4px] bg-primary text-primary-foreground"><Leaf className="h-5 w-5" /></span>}
        <div className="min-w-0 flex-1 leading-tight">
          <b className="block truncate">{d ? d.disease : "Trợ lý cây trồng"}</b>
          <span className="block truncate text-xs text-muted-foreground">{d ? `${d.plant}, độ tin cậy ${pct(d.confidence)}` : "Hỏi bất cứ điều gì về trồng trọt, sâu bệnh; gửi ảnh để AI xem"}</span>
        </div>
      </header>
      <div ref={log} className={cn("relative flex-1 overflow-y-auto px-3 py-4 [overscroll-behavior:contain] lg:px-8", dragging && "bg-secondary/60")} aria-live="polite">
        {dragging && <div className="pointer-events-none sticky top-0 z-10 rounded-xl border-2 border-dashed border-primary bg-card/90 p-4 text-center font-semibold text-primary">Thả ảnh vào đây để gửi cho trợ lý</div>}
        {hist.isLoading ? <div className="space-y-3"><Skeleton className="h-14 w-2/3" /><Skeleton className="ml-auto h-10 w-1/2" /></div> : !msgs.length && (
          <div className="mx-auto max-w-md py-8 text-center text-muted-foreground">
            <span className="mx-auto mb-3 grid h-14 w-14 place-items-center rounded-[16px_6px_16px_6px] bg-primary text-primary-foreground"><Leaf /></span>
            <p>{d ? `Hỏi tôi về ${d.disease.toLowerCase()} của cây ${d.plant.toLowerCase()}: cách xử lý, phòng ngừa, thuốc dùng…` : "Tôi là trợ lý AI về trồng trọt và sâu bệnh. Hãy đặt câu hỏi, chọn gợi ý bên dưới, hoặc chụp ảnh lá, con sâu gửi lên để tôi xem."}</p>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={cn("mb-3 flex items-end gap-2", m.role === "user" && "justify-end", m.failed && "opacity-60")}>
            {m.role === "assistant" && <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[10px_4px_10px_4px] bg-primary text-primary-foreground"><Leaf className="h-4 w-4" /></span>}
            <div className={cn("max-w-[82%] rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed sm:max-w-[640px] xl:max-w-[760px]", m.role === "user" ? "whitespace-pre-wrap rounded-br-md bg-primary text-primary-foreground" : "rounded-bl-md border bg-card")}>
              {m.image_url && <img src={m.image_url} alt="Ảnh đã gửi" className="mb-2 max-h-64 w-full rounded-lg object-cover" />}
              {m.role === "user" ? m.content : m.fresh ? <TypeOut t={m.content} onTick={toBottom} onDone={() => setMsgs((cur) => cur.map((x, j) => (j === i ? { ...x, fresh: false } : x)))} /> : <Rich t={m.content} />}
              {m.role === "assistant" && !m.fresh && <SpeakButton text={plainText(m.content)} variant="ghost" label="Nghe" className="-ml-2 mt-1 h-8 px-2 text-xs text-muted-foreground" />}
              {(m.source || m.created) && <small className={cn("mt-1 block text-xs", m.role === "user" ? "opacity-75" : "text-muted-foreground")}>{m.source ? SOURCE[m.source] || m.source : ""}{m.source && m.created ? " · " : ""}{m.created ? fmtTime(toDate(m.created)) : ""}</small>}
              {m.failed && <button type="button" onClick={() => ask(m.content, m.file || null, i)} className="mt-1 inline-flex items-center gap-1 text-xs font-bold underline"><RotateCcw className="h-3 w-3" />Gửi lại</button>}
            </div>
          </div>
        ))}
        {busy && <Typing withImage={pendingImage} />}
      </div>
      {!img && <div className="flex gap-2 overflow-x-auto px-3 pb-2 no-scrollbar lg:px-8">{suggestions.map((s) => <button key={s} type="button" onClick={() => ask(s, null)} disabled={busy} className="shrink-0 rounded-full border bg-card px-3.5 py-1.5 text-sm font-semibold text-primary transition hover:border-primary disabled:opacity-50">{s}</button>)}</div>}
      <form onSubmit={(e) => { e.preventDefault(); ask(text); }} className="border-t bg-card px-3 pb-[calc(0.75rem+var(--safe-b))] pt-3 lg:px-8">
        {img && (
          <div className="mb-2 flex items-center gap-3 rounded-xl border bg-background p-2">
            <img src={imgUrl} alt="Ảnh sẽ gửi" className="h-16 w-16 rounded-lg object-cover" />
            <span className="flex-1 text-sm text-muted-foreground">Ảnh sẽ gửi kèm. Viết câu hỏi hoặc bấm gửi để AI xem và nhận xét.</span>
            <Button type="button" variant="ghost" size="icon-sm" aria-label="Bỏ ảnh" onClick={() => { setImg(null); setImgUrl(""); }}><X className="h-4 w-4" /></Button>
          </div>
        )}
        <div className="flex items-end gap-2">
          <Button type="button" variant="ghost" size="icon" aria-label="Chụp ảnh" title="Chụp ảnh" disabled={busy} onClick={async () => attach(await pickFile(true))}><Camera /></Button>
          <Button type="button" variant="ghost" size="icon" aria-label="Chọn ảnh" title="Chọn ảnh có sẵn" disabled={busy} className={cn(!liveCamera() && "hidden sm:inline-flex")} onClick={async () => attach(await pickFile(false))}><ImagePlus /></Button>
          <MicButton disabled={busy} onInterim={(t) => { setText(t); autosize(); }} onText={(t) => ask(t)} />
          <textarea ref={ta} rows={1} maxLength={1000} value={text} onChange={(e) => { setText(e.target.value); autosize(); }} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); ask(text); } }}
            placeholder={img ? "Hỏi gì về ảnh này? (không bắt buộc)" : "Nhập câu hỏi…"} aria-label="Câu hỏi" className="max-h-[140px] min-h-[46px] flex-1 resize-none rounded-3xl border bg-background px-4 py-3 leading-relaxed focus:border-primary focus:outline-none" />
          <Button type="submit" size="icon" className="rounded-full" disabled={(!text.trim() && !img) || busy} aria-label="Gửi"><Send /></Button>
        </div>
      </form>
      <p className="bg-card pb-1 text-center text-xs text-muted-foreground">AI có thể sai. Hãy hỏi cán bộ khuyến nông trước khi dùng thuốc.</p>
    </div>
  );
}
