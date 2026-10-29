import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FlaskConical, Leaf, Loader2, RefreshCw, Search, ShieldAlert, Sparkles, Store as StoreIcon } from "lucide-react";
import { api, type Diagnosis, type Product, type ProductReport } from "@/shared/lib/api";
import { cn, toDate } from "@/shared/lib/utils";
import { useMe } from "@/shared/hooks/use-me";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";
import { Notice, Skeleton } from "@/shared/ui/misc";

const vnd = (n: number) => n.toLocaleString("vi-VN") + " đ";
const STORE_QUERY = "cửa hàng thuốc bảo vệ thực vật";
const host = (u: string) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };

/** Gợi ý thuốc và nơi mua cho một kết quả tra cứu: tự tìm khi mở kết quả (bệnh đã có người tìm trong 7 ngày thì dùng lại ngay,
 *  không tốn lượt AI; tìm mới tính một lượt). */
export function ShopSuggestions({ d }: { d: Diagnosis }) {
  const [refresh, setRefresh] = useState(0);
  const q = useQuery({
    queryKey: ["products", d.id, refresh],
    queryFn: () => api<ProductReport>(`/api/diagnoses/${d.id}/products${refresh ? "?refresh=1" : ""}`),
    retry: false, staleTime: Infinity,
  });
  return (
    <section className="rounded-3xl border bg-card p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold"><FlaskConical className="h-5 w-5 text-primary" />Thuốc nên dùng và nơi mua</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">AI tìm trên Google các sản phẩm đang bán ở Việt Nam trị {d.disease.toLowerCase()}, kèm giá tham khảo; bên dưới là bản đồ cửa hàng gần bạn.</p>
        </div>
      </div>
      {q.isLoading || q.isFetching ? (
        <div className="mt-4 space-y-3">
          <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />AI đang tìm sản phẩm và kiểm tra trang bán (khoảng 20-40 giây)…</p>
          {[0, 1].map((i) => <Skeleton key={i} className="h-28" />)}
        </div>
      ) : q.isError ? (
        <div className="mt-4">
          <Notice tone="warn" icon={ShieldAlert}>{(q.error as Error).message}</Notice>
          <Button variant="outline" className="mt-2" onClick={() => q.refetch()}><Sparkles />Thử tìm lại</Button>
        </div>
      ) : q.data && (
        <div className="mt-4 space-y-3">
          {!q.data.products.length && <p className="text-sm text-muted-foreground">AI chưa tìm được sản phẩm phù hợp đang bán trên mạng. Hãy hỏi cửa hàng vật tư theo hướng xử lý ở trên.</p>}
          {q.data.products.map((p, i) => <ProductCard key={i} p={p} />)}
          <Notice tone="warn" icon={ShieldAlert} className="p-3 text-xs">
            {q.data.note ? `${q.data.note} ` : ""}Giá chỉ để tham khảo, có thể đã đổi. Chỉ mua thuốc có trong danh mục được phép, đọc kỹ nhãn, dùng đúng liều, mang đồ bảo hộ và tuân thủ thời gian cách ly trước khi thu hoạch.
          </Notice>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>{q.data.cached_at ? `Tìm lúc ${toDate(q.data.cached_at).toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" })}` : ""}
              {q.data.sources.length ? `, nguồn: ${[...new Set(q.data.sources.map((s) => host(s.url)))].slice(0, 4).join(", ")}` : ""}</span>
            <button type="button" className="inline-flex items-center gap-1 font-semibold text-primary hover:underline" onClick={() => setRefresh((x) => x + 1)}><RefreshCw className="h-3.5 w-3.5" />Tìm lại</button>
          </div>
        </div>
      )}
      <NearbyStores className="mt-5 border-t pt-5" />
    </section>
  );
}

function ProductCard({ p }: { p: Product }) {
  const [broken, setBroken] = useState(false);
  return (
    <article className="flex gap-3 rounded-2xl border p-3">
      <div className="h-24 w-24 shrink-0 overflow-hidden rounded-xl bg-secondary">
        {p.image && !broken ? <img src={p.image} alt={p.name} loading="lazy" referrerPolicy="no-referrer" onError={() => setBroken(true)} className="h-full w-full object-contain bg-white" />
          : <span className="grid h-full w-full place-items-center text-primary">{p.kind === "sinh_hoc" ? <Leaf className="h-8 w-8" /> : <FlaskConical className="h-8 w-8" />}</span>}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <b className="text-[15px] leading-tight">{p.name}</b>
          <Badge variant={p.kind === "sinh_hoc" ? "success" : "muted"}>{p.kind === "sinh_hoc" ? "Sinh học" : "Hóa học"}</Badge>
        </div>
        {p.active_ingredient && <p className="mt-0.5 text-xs text-muted-foreground">Hoạt chất: {p.active_ingredient}{p.pack ? `. ${p.pack}` : ""}</p>}
        {p.description && <p className="mt-1 text-sm leading-snug">{p.description}</p>}
        {p.usage && <p className="mt-1 text-xs text-muted-foreground">Cách dùng: {p.usage}</p>}
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <span className={cn("text-sm font-bold", p.price_vnd ? "text-primary" : "text-muted-foreground")}>{p.price_vnd ? `~ ${vnd(p.price_vnd)}` : "Chưa rõ giá"}</span>
          {p.url ? <a href={p.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"><ExternalLink className="h-3.5 w-3.5" />Xem nơi bán{p.shop ? ` (${p.shop})` : ""}</a>
            : <a href={`https://www.google.com/search?q=${encodeURIComponent(p.name + " giá")}`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm font-semibold text-muted-foreground hover:text-primary"><Search className="h-3.5 w-3.5" />Tìm nơi bán</a>}
        </div>
      </div>
    </article>
  );
}

/** Bản đồ Google Maps nhúng, tìm sẵn cửa hàng thuốc BVTV quanh vị trí vườn đã lưu (Google tự ghim cửa hàng, không tốn lượt AI). */
export function NearbyStores({ className, mapClass = "h-80 sm:h-96" }: { className?: string; mapClass?: string }) {
  const { me } = useMe();
  const loc = me?.location;
  if (!loc) return (
    <div className={className}>
      <h3 className="flex items-center gap-2 font-bold"><StoreIcon className="h-5 w-5 text-primary" />Cửa hàng gần bạn</h3>
      <p className="mt-1 text-sm text-muted-foreground">Đặt vị trí vườn để xem cửa hàng thuốc, vật tư nông nghiệp gần nhất trên bản đồ. <Link to="/weather" className="font-semibold text-primary">Đặt vị trí</Link></p>
    </div>
  );
  const what = encodeURIComponent(STORE_QUERY);
  return (
    <div className={className}>
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 font-bold"><StoreIcon className="h-5 w-5 text-primary" />Cửa hàng gần bạn</h3>
        <a href={`https://www.google.com/maps/search/${what}/@${loc.lat},${loc.lon},14z`} target="_blank" rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-sm font-semibold text-primary"><ExternalLink className="h-4 w-4" />Mở Google Maps</a>
      </div>
      <iframe title="Cửa hàng thuốc bảo vệ thực vật gần bạn" loading="lazy" referrerPolicy="no-referrer-when-downgrade"
        src={`https://maps.google.com/maps?q=${what}&ll=${loc.lat},${loc.lon}&z=13&hl=vi&output=embed`}
        className={cn("mt-3 w-full rounded-2xl border", mapClass)} />
      <p className="mt-2 text-xs text-muted-foreground">Bấm vào ghim đỏ để xem địa chỉ, giờ mở cửa, số điện thoại và chỉ đường; gọi trước để hỏi còn hàng.</p>
    </div>
  );
}
