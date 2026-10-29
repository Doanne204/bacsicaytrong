import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bug, Check, Leaf, Search } from "lucide-react";
import { api, type Library } from "@/shared/lib/api";
import { cn } from "@/shared/lib/utils";
import { Input } from "@/shared/ui/input";
import { Skeleton } from "@/shared/ui/misc";

/** Bỏ dấu tiếng Việt để tìm "dao on" ra "đạo ôn". */
export const fold = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();

export const useLibrary = () => useQuery({ queryKey: ["library"], queryFn: () => api<Library>("/api/library"), staleTime: 30 * 60_000 });

export interface LabelOption { class_name: string; title: string; sub: string; pest: boolean }

/** Danh sách nhãn chọn được: bệnh lá (kèm "lá khỏe" của từng cây) và/hoặc sâu hại. */
export function labelOptions(lib: Library | undefined, kind: "leaf" | "pest" | "all"): LabelOption[] {
  if (!lib) return [];
  const leaf: LabelOption[] = kind === "pest" ? [] : [
    ...lib.diseases.map((d) => ({ class_name: d.class_name, title: d.disease, sub: d.plant, pest: false })),
    ...lib.plants.filter((p) => p.healthy_class).map((p) => ({ class_name: p.healthy_class!, title: "Lá khỏe mạnh", sub: p.name, pest: false })),
  ].sort((a, b) => a.sub.localeCompare(b.sub, "vi") || a.title.localeCompare(b.title, "vi"));
  const pest: LabelOption[] = kind === "leaf" ? [] : lib.pests.map((p) => ({ class_name: p.class_name, title: p.name, sub: `${p.group_name} · ${p.class_name}`, pest: true }));
  return [...leaf, ...pest];
}

/** Ô tìm + danh sách để chọn bệnh / loài đúng (báo kết quả sai, quản trị viên sửa nhãn). */
export function LabelPicker({ kind, value, onChange, exclude, className }: {
  kind: "leaf" | "pest" | "all"; value: string | null; onChange: (c: string) => void; exclude?: string | null; className?: string;
}) {
  const lib = useLibrary();
  const [q, setQ] = useState("");
  const all = useMemo(() => labelOptions(lib.data, kind).filter((o) => o.class_name !== exclude), [lib.data, kind, exclude]);
  const shown = useMemo(() => {
    const words = fold(q).split(/\s+/).filter(Boolean);
    return all.filter((o) => words.every((w) => fold(`${o.title} ${o.sub}`).includes(w))).slice(0, 80);
  }, [all, q]);
  return (
    <div className={cn("min-w-0", className)}>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={kind === "pest" ? "Tìm tên sâu, nhóm…" : "Tìm tên cây, tên bệnh…"} className="pl-9" aria-label="Tìm nhãn" />
      </div>
      {lib.isLoading ? <Skeleton className="mt-2 h-48" /> : (
        <ul className="mt-2 max-h-64 divide-y overflow-y-auto rounded-xl border" role="listbox" aria-label="Chọn bệnh đúng">
          {shown.map((o) => {
            const on = value === o.class_name, Icon = o.pest ? Bug : Leaf;
            return (
              <li key={o.class_name}>
                <button type="button" role="option" aria-selected={on} onClick={() => onChange(o.class_name)}
                  className={cn("flex w-full items-center gap-3 px-3 py-2 text-left text-sm transition", on ? "bg-secondary" : "hover:bg-muted")}>
                  <Icon className="h-4 w-4 shrink-0 text-primary" />
                  <span className="min-w-0 flex-1"><b className="block truncate">{o.title}</b><span className="block truncate text-xs text-muted-foreground">{o.sub}</span></span>
                  {on && <Check className="h-4 w-4 text-primary" />}
                </button>
              </li>
            );
          })}
          {!shown.length && <li className="px-3 py-4 text-center text-sm text-muted-foreground">Không thấy trong danh sách.</li>}
        </ul>
      )}
    </div>
  );
}
