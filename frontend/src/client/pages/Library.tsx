import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Bug, Leaf, MessageCircle, ScanLine, Search, ShieldCheck, Sparkles } from "lucide-react";
import { libImage, type LibDisease, type LibPest } from "@/shared/lib/api";
import { cn } from "@/shared/lib/utils";
import { fold, useLibrary } from "@/shared/components/label-picker";
import { PageHeader } from "@/shared/components/common";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { EmptyState, Skeleton } from "@/shared/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/shared/ui/dialog";

type Item = { key: string; title: string; sub: string; remedy: string; hosts?: string; pest: boolean; tag?: string; good?: boolean };
const PAGE = 48;

/** Thư viện bệnh lá và sâu hại: xem không cần chụp ảnh, tìm theo tên (không dấu cũng được), lọc theo cây / nhóm sâu. */
export default function Library() {
  const lib = useLibrary();
  const [tab, setTab] = useState("leaf"), [q, setQ] = useState(""), [filter, setFilter] = useState(""), [limit, setLimit] = useState(PAGE);
  const [open, setOpen] = useState<Item | null>(null);
  const items = useMemo<Item[]>(() => {
    if (!lib.data) return [];
    return tab === "leaf"
      ? lib.data.diseases.filter((d) => !filter || d.plant_id === filter).map(leafItem)
      : lib.data.pests.filter((p) => !filter || (filter === "_good" ? p.beneficial : p.group === filter)).map(pestItem);
  }, [lib.data, tab, filter]);
  const shown = useMemo(() => {
    const words = fold(q).split(/\s+/).filter(Boolean);
    return items.filter((i) => words.every((w) => fold(`${i.title} ${i.sub} ${i.hosts || ""}`).includes(w)));
  }, [items, q]);
  const chips = !lib.data ? [] : tab === "leaf"
    ? lib.data.plants.map((p) => [p.id, p.name])
    : [["_good", "Thiên địch có ích"], ...lib.data.groups.filter((g) => g.id !== "thien_dich").map((g) => [g.id, g.name])];
  const switchTab = (t: string) => { setTab(t); setFilter(""); setLimit(PAGE); };
  return (
    <div className="animate-fade-up">
      <PageHeader title="Thư viện sâu bệnh" text="Tra cứu bệnh trên lá và sâu hại, thiên địch mà hệ thống nhận diện được, kèm cách phòng trừ. Không cần chụp ảnh." />
      <Tabs value={tab} onValueChange={switchTab}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <TabsList>
            <TabsTrigger value="leaf"><Leaf className="mr-1.5 h-4 w-4" />Bệnh trên lá{lib.data ? ` (${lib.data.diseases.length})` : ""}</TabsTrigger>
            <TabsTrigger value="pest"><Bug className="mr-1.5 h-4 w-4" />Sâu hại, thiên địch{lib.data ? ` (${lib.data.pests.length})` : ""}</TabsTrigger>
          </TabsList>
          <div className="relative sm:ml-auto sm:w-72">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => { setQ(e.target.value); setLimit(PAGE); }} placeholder={tab === "leaf" ? "Tìm bệnh, tên cây…" : "Tìm tên sâu, cây bị hại…"} className="pl-9" aria-label="Tìm trong thư viện" />
          </div>
        </div>
        <div className="mt-3 flex gap-2 overflow-x-auto pb-1 no-scrollbar">
          {[["", "Tất cả"], ...chips].map(([id, name]) => (
            <button key={id} type="button" onClick={() => { setFilter(id); setLimit(PAGE); }} aria-pressed={filter === id}
              className={cn("h-8 shrink-0 rounded-full border px-3 text-sm font-semibold transition", filter === id ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:border-primary")}>{name}</button>
          ))}
        </div>
        {["leaf", "pest"].map((t) => (
          <TabsContent key={t} value={t} className="mt-4">
            {lib.isLoading ? <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-52" />)}</div>
              : !shown.length ? <div className="rounded-2xl border bg-card"><EmptyState icon={Search} title="Không tìm thấy" text="Thử từ khóa khác, hoặc chụp ảnh lá để hệ thống nhận diện." /></div>
              : (
                <>
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">{shown.slice(0, limit).map((i) => <Card key={i.key} item={i} onOpen={() => setOpen(i)} />)}</div>
                  {shown.length > limit && <div className="mt-4 text-center"><Button variant="outline" onClick={() => setLimit((n) => n + PAGE)}>Xem thêm ({shown.length - limit})</Button></div>}
                </>
              )}
          </TabsContent>
        ))}
      </Tabs>
      {open && <Detail item={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

const leafItem = (d: LibDisease): Item => ({ key: d.class_name, title: d.healthy ? "Lá khỏe mạnh" : d.disease, sub: d.plant, remedy: d.remedy, pest: false,
  good: d.healthy, tag: d.healthy ? "Lá khỏe" : d.source === "ai" ? "AI học thêm" : undefined });
const pestItem = (p: LibPest): Item => ({ key: p.class_name, title: p.name, sub: p.group_name, remedy: p.remedy, hosts: p.hosts, pest: true, good: p.beneficial, tag: p.beneficial ? "Có ích" : undefined });

function Thumb({ item, className }: { item: Item; className?: string }) {
  const [broken, setBroken] = useState(false);
  const Icon = item.pest ? Bug : Leaf;
  return broken ? <span className={cn("grid place-items-center bg-secondary text-primary", className)}><Icon className="h-8 w-8" /></span>
    : <img src={libImage(item.key)} alt="" loading="lazy" onError={() => setBroken(true)} className={cn("bg-muted object-cover", className)} />;
}

function Card({ item, onOpen }: { item: Item; onOpen: () => void }) {
  return (
    <button type="button" onClick={onOpen} className="group min-w-0 overflow-hidden rounded-2xl border bg-card text-left transition hover:border-primary hover:shadow-soft">
      <Thumb item={item} className="aspect-[4/3] w-full" />
      <div className="p-3">
        <b className="line-clamp-2 text-sm leading-snug group-hover:text-primary">{item.title}</b>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">{item.sub}</p>
        {item.tag && <Badge variant={item.good ? "success" : "muted"} className="mt-1.5">{item.good ? <ShieldCheck className="mr-1 h-3 w-3" /> : <Sparkles className="mr-1 h-3 w-3" />}{item.tag}</Badge>}
      </div>
    </button>
  );
}

function Detail({ item, onClose }: { item: Item; onClose: () => void }) {
  const ask = item.pest ? `${item.title} (${item.key}) gây hại thế nào và phòng trừ ra sao?` : `Bệnh ${item.title.toLowerCase()} trên cây ${item.sub.toLowerCase()}: nhận biết và cách xử lý?`;
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <Thumb item={item} className="aspect-[16/10] w-full rounded-2xl" />
        <DialogHeader>
          <DialogTitle>{item.title}</DialogTitle>
          <DialogDescription>{item.pest ? <>{item.sub} · <i>{item.key}</i></> : `Cây ${item.sub.toLowerCase()}`}</DialogDescription>
        </DialogHeader>
        {item.hosts && <p className="text-sm"><b>{item.good ? "Vai trò: " : "Cây bị hại: "}</b>{item.hosts}</p>}
        <div>
          <h3 className="text-sm font-bold">{item.good ? "Lưu ý" : item.pest ? "Phòng trừ" : "Cách xử lý"}</h3>
          <p className="mt-1 text-[15px] leading-relaxed">{item.remedy}</p>
          <p className="mt-2 text-xs text-muted-foreground">Chỉ để tham khảo. Đọc kỹ nhãn thuốc, tuân thủ thời gian cách ly; bệnh nặng hãy hỏi cán bộ khuyến nông.</p>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <Button asChild><Link to={`/chat?q=${encodeURIComponent(ask)}`}><MessageCircle />Hỏi trợ lý AI</Link></Button>
          <Button asChild variant="outline"><Link to="/scan"><ScanLine />Chụp ảnh để kiểm tra</Link></Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
