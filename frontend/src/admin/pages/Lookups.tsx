import { useMemo, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Leaf, ScanSearch, Search, Trash2, User, X } from "lucide-react";
import { api, send } from "@/shared/lib/api";
import { ago, cn, pct } from "@/shared/lib/utils";
import { fold } from "@/shared/components/label-picker";
import { ConfirmDialog } from "@/shared/components/common";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { EmptyState, Skeleton } from "@/shared/ui/misc";
import { Segmented } from "../components/table";
import type { LookupList, LookupRow, LookupSummary } from "../lib/types";

const SOURCE: Record<string, string> = { ai: "AI Gemini", model: "Mô hình", memory: "Bộ nhớ ảnh" };

/** Lượt tra cứu: người dùng nào tra cứu những cây gì, cây nào có những ai tra cứu; lọc, xem và xóa lượt tra cứu của người dùng. */
export default function Lookups({ onChange }: { onChange: () => void }) {
  const [view, setView] = useState<"user" | "plant">("user"), [find, setFind] = useState(""), [q, setQ] = useState("");
  const [user, setUser] = useState<{ id: number; name: string } | null>(null), [plant, setPlant] = useState<string | null>(null);
  const [picked, setPicked] = useState<number[]>([]), [victims, setVictims] = useState<number[] | null>(null);
  const listRef = useRef<HTMLElement>(null);
  const sum = useQuery({ queryKey: ["admin", "lookups", "summary"], queryFn: () => api<LookupSummary>("/api/admin/lookups/summary") });
  const params = new URLSearchParams({ q, ...(user ? { user_id: String(user.id) } : {}), ...(plant ? { plant } : {}) });
  const list = useQuery({ queryKey: ["admin", "lookups", "list", params.toString()], queryFn: () => api<LookupList>(`/api/admin/lookups?${params}`), placeholderData: keepPreviousData });
  const words = fold(find).split(/\s+/).filter(Boolean);
  const hit = (text: string) => words.every((w) => fold(text).includes(w));
  const users = useMemo(() => (sum.data?.by_user || []).filter((u) => hit(`${u.username} ${u.plants.map((p) => p.plant).join(" ")}`)), [sum.data, find]); // eslint-disable-line react-hooks/exhaustive-deps
  const plants = useMemo(() => (sum.data?.by_plant || []).filter((p) => hit(`${p.plant} ${p.users.map((u) => u.username).join(" ")}`)), [sum.data, find]); // eslint-disable-line react-hooks/exhaustive-deps
  const rows = list.data?.rows || [];
  const allOn = !!rows.length && rows.every((r) => picked.includes(r.id));
  const show = (u: { id: number; name: string } | null, p: string | null) => {
    setUser(u); setPlant(p); setPicked([]);
    listRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const toggle = (id: number) => setPicked((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const remove = async () => {
    if (!victims) return;
    const r = await send<{ deleted: number }>("/api/admin/lookups/delete", { ids: victims });
    toast.success(`Đã xóa ${r.deleted} lượt tra cứu`);
    setPicked((s) => s.filter((id) => !victims.includes(id)));
    sum.refetch(); list.refetch(); onChange();
  };
  const chip = "inline-flex items-center gap-1 rounded-full border bg-card px-2.5 py-1 text-xs font-semibold transition hover:border-primary hover:text-primary";
  return (
    <div className="space-y-5 animate-fade-up">
      <div className="grid grid-cols-3 gap-3">
        {[["Lượt tra cứu", sum.data?.total], ["Người dùng đã tra cứu", sum.data?.by_user.length], ["Loại cây", sum.data?.by_plant.length]].map(([l, n]) => (
          <div key={l as string} className="rounded-2xl border bg-card p-4"><span className="text-xs text-muted-foreground">{l}</span><b className="block text-2xl tabular-nums">{n ?? "…"}</b></div>
        ))}
      </div>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <section className="min-w-0 space-y-3">
          <Segmented value={view} onChange={setView} options={[["user", "Theo người dùng"], ["plant", "Theo cây"]]} />
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-3 h-5 w-5 text-muted-foreground" />
            <Input type="search" value={find} onChange={(e) => setFind(e.target.value)} placeholder={view === "user" ? "Tìm người dùng hoặc tên cây…" : "Tìm tên cây hoặc người dùng…"} className="pl-10" aria-label="Tìm trong tổng hợp" />
          </div>
          {sum.isLoading ? <Skeleton className="h-64" /> : view === "user" ? (
            !users.length ? <div className="rounded-2xl border bg-card"><EmptyState icon={User} title="Không có người dùng khớp" /></div> : (
              <ul className="divide-y rounded-2xl border bg-card">
                {users.map((u) => (
                  <li key={u.user_id} className="p-3">
                    <button type="button" onClick={() => show({ id: u.user_id, name: u.username }, null)} className="flex w-full items-center gap-2 text-left text-sm hover:text-primary">
                      <User className="h-4 w-4 shrink-0 text-primary" /><b className="min-w-0 flex-1 truncate">{u.username}</b>
                      <span className="shrink-0 text-xs text-muted-foreground">{u.n} lượt, {u.plants.length} cây · {ago(u.last)}</span>
                    </button>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {u.plants.map((p) => <button key={p.plant} type="button" className={chip} onClick={() => show({ id: u.user_id, name: u.username }, p.plant)}>{p.plant} <span className="text-muted-foreground">{p.n}</span></button>)}
                    </div>
                  </li>
                ))}
              </ul>
            )
          ) : (
            !plants.length ? <div className="rounded-2xl border bg-card"><EmptyState icon={Leaf} title="Không có cây nào khớp" /></div> : (
              <ul className="divide-y rounded-2xl border bg-card">
                {plants.map((p) => (
                  <li key={p.plant} className="p-3">
                    <button type="button" onClick={() => show(null, p.plant)} className="flex w-full items-center gap-2 text-left text-sm hover:text-primary">
                      <Leaf className="h-4 w-4 shrink-0 text-primary" /><b className="min-w-0 flex-1 truncate">{p.plant}</b>
                      <span className="shrink-0 text-xs text-muted-foreground">{p.n} lượt, {p.users.length} người · {ago(p.last)}</span>
                    </button>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {p.users.map((u) => <button key={u.user_id} type="button" className={chip} onClick={() => show({ id: u.user_id, name: u.username }, p.plant)}>{u.username} <span className="text-muted-foreground">{u.n}</span></button>)}
                    </div>
                  </li>
                ))}
              </ul>
            )
          )}
        </section>
        <section ref={listRef} className="min-w-0 scroll-mt-20 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-bold">Các lượt tra cứu</h2>
            {user && <button type="button" className={cn(chip, "border-primary")} onClick={() => setUser(null)} aria-label={`Bỏ lọc người dùng ${user.name}`}><User className="h-3.5 w-3.5" />{user.name}<X className="h-3.5 w-3.5" /></button>}
            {plant && <button type="button" className={cn(chip, "border-primary")} onClick={() => setPlant(null)} aria-label={`Bỏ lọc cây ${plant}`}><Leaf className="h-3.5 w-3.5" />{plant}<X className="h-3.5 w-3.5" /></button>}
          </div>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-3 h-5 w-5 text-muted-foreground" />
            <Input type="search" value={q} onChange={(e) => { setQ(e.target.value); setPicked([]); }} placeholder="Tìm tên người dùng, cây, bệnh (gõ có dấu)…" className="pl-10" aria-label="Tìm lượt tra cứu" />
          </div>
          {list.isLoading ? <Skeleton className="h-64" /> : !rows.length ? <div className="rounded-2xl border bg-card"><EmptyState icon={ScanSearch} title="Không có lượt tra cứu nào khớp" /></div> : (
            <>
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <label className="flex cursor-pointer items-center gap-2 font-semibold"><input type="checkbox" className="h-4 w-4 accent-[hsl(var(--primary))]" checked={allOn} onChange={() => setPicked(allOn ? [] : rows.map((r) => r.id))} />Chọn tất cả đang hiện</label>
                <span className="text-muted-foreground">{list.data && list.data.total > rows.length ? `${rows.length} mới nhất / ${list.data.total} lượt` : `${rows.length} lượt`}</span>
                {!!picked.length && <Button size="sm" variant="destructive" className="ml-auto" onClick={() => setVictims(picked)}><Trash2 />Xóa {picked.length} lượt đã chọn</Button>}
              </div>
              <ul className="divide-y rounded-2xl border bg-card">
                {rows.map((r) => <Row key={r.id} r={r} on={picked.includes(r.id)} onToggle={() => toggle(r.id)} onDelete={() => setVictims([r.id])} />)}
              </ul>
            </>
          )}
        </section>
      </div>
      <ConfirmDialog open={!!victims} onOpenChange={(o) => !o && setVictims(null)} title={victims?.length === 1 ? "Xóa lượt tra cứu này?" : `Xóa ${victims?.length} lượt tra cứu?`}
        description="Xóa vĩnh viễn kết quả khỏi lịch sử của người dùng, cùng cuộc trò chuyện, đánh giá kèm theo và ảnh đã tải lên. Không thể hoàn tác. Ảnh đã lưu trong dữ liệu AI (dataset_ai) vẫn giữ." confirmText="Xóa vĩnh viễn" danger
        onConfirm={async () => { try { await remove(); } catch (e) { toast.error((e as Error).message); throw e; } }} />
    </div>
  );
}

function Row({ r, on, onToggle, onDelete }: { r: LookupRow; on: boolean; onToggle: () => void; onDelete: () => void }) {
  return (
    <li className={cn("flex items-center gap-3 p-3", on && "bg-secondary/50")}>
      <input type="checkbox" className="h-4 w-4 shrink-0 accent-[hsl(var(--primary))]" checked={on} onChange={onToggle} aria-label={`Chọn lượt tra cứu ${r.plant}: ${r.disease}`} />
      {r.image_url ? <a href={r.image_url} target="_blank" rel="noreferrer" className="shrink-0"><img src={r.image_url} alt="" loading="lazy" className="h-14 w-14 rounded-xl object-cover" /></a>
        : <span className="grid h-14 w-14 shrink-0 place-items-center rounded-xl bg-secondary text-primary"><Leaf /></span>}
      <div className="min-w-0 flex-1 text-sm">
        <b className="block truncate">{r.plant}: {r.disease}</b>
        <p className="truncate text-xs text-muted-foreground">{r.username || "(đã xóa)"} · {ago(r.created)}</p>
        <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground"><Badge variant="muted">{SOURCE[r.source || ""] || "Mô hình"}</Badge>{r.confidence != null && pct(r.confidence)}</p>
      </div>
      <Button variant="ghost" size="icon-sm" className="shrink-0 text-destructive hover:text-destructive" aria-label="Xóa lượt tra cứu" onClick={onDelete}><Trash2 className="h-4 w-4" /></Button>
    </li>
  );
}
