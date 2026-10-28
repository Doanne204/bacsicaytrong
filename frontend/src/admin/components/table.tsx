import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Skeleton } from "@/shared/ui/misc";

export interface Column<T> { key: string; header: string; cell: (row: T) => React.ReactNode; sort?: (row: T) => string | number; className?: string; hide?: "sm" | "md" }

/** Bảng dữ liệu: tìm kiếm, sắp xếp theo cột, phân trang; trên điện thoại hiện dạng thẻ (card) nếu có renderCard. */
export function DataTable<T>({ rows, columns, keyOf, loading, empty, pageSize = 20, toolbar, renderCard, search, onSearch, searchPlaceholder }: {
  rows: T[]; columns: Column<T>[]; keyOf: (r: T) => string | number; loading?: boolean; empty?: React.ReactNode; pageSize?: number; toolbar?: React.ReactNode;
  renderCard?: (row: T) => React.ReactNode; search?: string; onSearch?: (q: string) => void; searchPlaceholder?: string;
}) {
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null), [page, setPage] = useState(0);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sort) return rows;
    return [...rows].sort((a, b) => { const x = col.sort!(a), y = col.sort!(b); return (x < y ? -1 : x > y ? 1 : 0) * sort.dir; });
  }, [rows, sort, columns]);
  const pages = Math.max(1, Math.ceil(sorted.length / pageSize)), cur = Math.min(page, pages - 1);
  const slice = sorted.slice(cur * pageSize, cur * pageSize + pageSize);
  const toggle = (key: string) => setSort((s) => (s?.key === key ? (s.dir === 1 ? { key, dir: -1 } : null) : { key, dir: 1 }));
  const hide = (h?: "sm" | "md") => (h === "sm" ? "hidden sm:table-cell" : h === "md" ? "hidden md:table-cell" : "");
  return (
    <div className="space-y-3">
      {(toolbar || onSearch) && (
        <div className="flex flex-wrap items-center gap-2">
          {toolbar}
          {onSearch && <div className="relative ml-auto w-full sm:w-72"><Search className="pointer-events-none absolute left-3 top-3 h-5 w-5 text-muted-foreground" /><Input type="search" value={search} onChange={(e) => { onSearch(e.target.value); setPage(0); }} placeholder={searchPlaceholder} className="pl-10" aria-label="Tìm kiếm" /></div>}
        </div>
      )}
      {loading ? <div className="space-y-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}</div> : !rows.length ? <div className="rounded-2xl border bg-card">{empty}</div> : (
        <>
          {renderCard && <div className="space-y-3 md:hidden">{slice.map((r) => <div key={keyOf(r)}>{renderCard(r)}</div>)}</div>}
          <div className={cn("overflow-x-auto rounded-2xl border bg-card", renderCard && "hidden md:block")}>
            <table className="w-full text-sm">
              <thead className="bg-muted/60 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>{columns.map((c) => (
                  <th key={c.key} className={cn("px-4 py-3 font-semibold", hide(c.hide), c.className)}>
                    {c.sort ? <button type="button" onClick={() => toggle(c.key)} className="inline-flex items-center gap-1 hover:text-foreground">{c.header}{sort?.key === c.key ? (sort.dir === 1 ? <ArrowUp className="h-3.5 w-3.5" /> : <ArrowDown className="h-3.5 w-3.5" />) : <ArrowUpDown className="h-3.5 w-3.5 opacity-50" />}</button> : c.header}
                  </th>
                ))}</tr>
              </thead>
              <tbody className="divide-y">{slice.map((r) => <tr key={keyOf(r)} className="align-top hover:bg-muted/40">{columns.map((c) => <td key={c.key} className={cn("px-4 py-3", hide(c.hide), c.className)}>{c.cell(r)}</td>)}</tr>)}</tbody>
            </table>
          </div>
          {pages > 1 && (
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>{cur * pageSize + 1}–{Math.min(sorted.length, (cur + 1) * pageSize)} / {sorted.length}</span>
              <div className="flex items-center gap-1"><Button variant="outline" size="icon-sm" disabled={cur === 0} onClick={() => setPage(cur - 1)} aria-label="Trang trước"><ChevronLeft className="h-4 w-4" /></Button><span className="px-2">Trang {cur + 1}/{pages}</span><Button variant="outline" size="icon-sm" disabled={cur >= pages - 1} onClick={() => setPage(cur + 1)} aria-label="Trang sau"><ChevronRight className="h-4 w-4" /></Button></div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/** Nhóm nút lọc (segmented). */
export function Segmented<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: [T, string][] }) {
  return (
    <div className="inline-flex flex-wrap rounded-xl bg-muted p-1" role="tablist">
      {options.map(([k, l]) => <button key={k} type="button" role="tab" aria-selected={value === k} onClick={() => onChange(k)} className={cn("rounded-lg px-3 py-1.5 text-sm font-semibold text-muted-foreground transition", value === k && "bg-card text-foreground shadow-sm")}>{l}</button>)}
    </div>
  );
}
