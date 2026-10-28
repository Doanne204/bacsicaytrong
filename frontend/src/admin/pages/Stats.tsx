import { useQuery } from "@tanstack/react-query";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/shared/lib/api";
import { ddmm } from "@/shared/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";
import { Skeleton } from "@/shared/ui/misc";
import { Badge } from "@/shared/ui/badge";

interface Analytics {
  months: string[]; monthly: { month: string; model: number; ai: number; memory: number; pest: number }[];
  diseases: { name: string; total: number; months: number[] }[];
  accuracy: { name: string; n: number; avg: number; good: number; bad: number; accuracy: number | null }[];
  ai_usage: { day: string; vision: number; chat: number }[]; top_users: { username: string; n: number }[]; keys: { ok: number; fail: number };
}
const mmyy = (m: string) => `${m.slice(5)}/${m.slice(2, 4)}`;
const tip = { contentStyle: { borderRadius: 10, border: "1px solid hsl(var(--border))", background: "hsl(var(--card))", color: "hsl(var(--foreground))" } };
const axis = { tick: { fontSize: 11, fill: "hsl(var(--muted-foreground))" }, axisLine: false, tickLine: false } as const;

export default function Stats() {
  const q = useQuery({ queryKey: ["admin", "analytics"], queryFn: () => api<Analytics>("/api/admin/analytics") });
  if (!q.data) return <div className="grid gap-4 lg:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-72" />)}</div>;
  const a = q.data, totalAI = a.ai_usage.reduce((s, d) => s + d.vision + d.chat, 0);
  return (
    <div className="space-y-5 animate-fade-up">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Lượt tra cứu 12 tháng</CardTitle><CardDescription>Chia theo nguồn kết quả: mô hình bệnh lá, AI Gemini, bộ nhớ ảnh AI, mô hình sâu hại.</CardDescription></CardHeader>
          <CardContent><div className="h-64"><ResponsiveContainer width="100%" height="100%">
            <BarChart data={a.monthly.map((m) => ({ ...m, label: mmyy(m.month) }))} margin={{ top: 8, right: 4, left: -24, bottom: 0 }}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="label" {...axis} /><YAxis allowDecimals={false} {...axis} />
              <Tooltip {...tip} cursor={{ fill: "hsl(var(--muted))" }} /><Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="model" name="Mô hình bệnh lá" stackId="a" fill="hsl(var(--primary))" />
              <Bar dataKey="ai" name="AI Gemini" stackId="a" fill="hsl(var(--paddy))" />
              <Bar dataKey="memory" name="Bộ nhớ ảnh AI" stackId="a" fill="hsl(var(--primary) / .45)" />
              <Bar dataKey="pest" name="Sâu hại" stackId="a" fill="hsl(var(--destructive) / .7)" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer></div></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Lượt dùng AI 30 ngày</CardTitle><CardDescription>Phân tích ảnh bằng Gemini và tin nhắn chat; tổng {totalAI} lượt. Khóa Gemini: {a.keys.ok} lượt thành công, {a.keys.fail} lượt lỗi.</CardDescription></CardHeader>
          <CardContent><div className="h-64"><ResponsiveContainer width="100%" height="100%">
            <AreaChart data={a.ai_usage.map((d) => ({ ...d, label: ddmm(d.day) }))} margin={{ top: 8, right: 4, left: -24, bottom: 0 }}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="label" {...axis} interval={4} /><YAxis allowDecimals={false} {...axis} />
              <Tooltip {...tip} /><Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
              <Area type="monotone" dataKey="vision" name="Phân tích ảnh" stackId="1" stroke="hsl(var(--paddy))" fill="hsl(var(--paddy) / .4)" />
              <Area type="monotone" dataKey="chat" name="Chat" stackId="1" stroke="hsl(var(--primary))" fill="hsl(var(--primary) / .3)" />
            </AreaChart>
          </ResponsiveContainer></div></CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader><CardTitle>Bệnh, sâu hại theo tháng</CardTitle><CardDescription>8 loại gặp nhiều nhất trong 12 tháng; ô đậm hơn là tháng có nhiều lượt hơn.</CardDescription></CardHeader>
        <CardContent className="overflow-x-auto">
          {a.diseases.length ? (
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs uppercase text-muted-foreground"><th className="py-2 pr-3">Bệnh / sâu hại</th>{a.months.map((m) => <th key={m} className="px-1 py-2 text-center font-semibold">{mmyy(m)}</th>)}<th className="py-2 pl-3 text-right">Tổng</th></tr></thead>
              <tbody className="divide-y">{a.diseases.map((d) => { const mx = Math.max(1, ...d.months); return (
                <tr key={d.name}><td className="max-w-[260px] truncate py-2 pr-3 font-medium">{d.name}</td>
                  {d.months.map((n, i) => <td key={i} className="px-1 py-1 text-center"><span className="inline-block min-w-[32px] rounded-md px-1 py-1 tabular-nums" style={{ background: n ? `hsl(var(--primary) / ${0.15 + 0.6 * (n / mx)})` : "transparent", color: n / mx > 0.5 ? "hsl(var(--primary-foreground))" : "inherit" }}>{n || ""}</span></td>)}
                  <td className="py-2 pl-3 text-right font-bold tabular-nums">{d.total}</td></tr>
              ); })}</tbody>
            </table>
          ) : <p className="text-sm text-muted-foreground">Chưa có lượt tra cứu nào ra bệnh.</p>}
        </CardContent>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Độ chính xác suy từ đánh giá sao</CardTitle><CardDescription>Người dùng chấm 4-5 sao coi là kết quả đúng, 1-2 sao là sai, 3 sao không tính. Càng nhiều đánh giá con số càng tin cậy.</CardDescription></CardHeader>
          <CardContent>
            {a.accuracy.length ? <ul className="divide-y">{a.accuracy.map((r) => (
              <li key={r.name} className="flex items-center gap-3 py-2.5 text-sm">
                <span className="flex-1"><b>{r.name}</b><span className="block text-xs text-muted-foreground">{r.n} đánh giá · trung bình {r.avg.toFixed(1).replace(".", ",")} sao · {r.good} đúng, {r.bad} sai</span></span>
                {r.accuracy === null ? <Badge variant="muted">chưa đủ dữ liệu</Badge> : <Badge variant={r.accuracy >= 0.8 ? "success" : r.accuracy >= 0.6 ? "warning" : "destructive"}>{Math.round(r.accuracy * 100)}% đúng</Badge>}
              </li>
            ))}</ul> : <p className="text-sm text-muted-foreground">Chưa có đánh giá nào.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Người tra cứu nhiều nhất (30 ngày)</CardTitle></CardHeader>
          <CardContent>{a.top_users.length ? <ol className="divide-y">{a.top_users.map((u, i) => <li key={u.username} className="flex items-center gap-3 py-2.5 text-sm"><span className="grid h-7 w-7 place-items-center rounded-full bg-secondary text-xs font-bold text-secondary-foreground">{i + 1}</span><b className="flex-1">{u.username}</b><span className="tabular-nums text-muted-foreground">{u.n} lượt</span></li>)}</ol> : <p className="text-sm text-muted-foreground">Chưa có dữ liệu.</p>}</CardContent>
        </Card>
      </div>
    </div>
  );
}
