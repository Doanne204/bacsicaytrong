import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Bell, Bug, KeyRound, MessageSquare, PenSquare, ScanLine, Star, Users } from "lucide-react";
import { send } from "@/shared/lib/api";
import { ddmm } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Textarea } from "@/shared/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { Progress, Skeleton } from "@/shared/ui/misc";
import { ConfirmDialog } from "@/shared/components/common";
import type { Stats } from "../lib/types";

export default function Overview({ stats: st, refetch }: { stats?: Stats; refetch: () => void }) {
  const [content, setContent] = useState(""), [confirm, setConfirm] = useState(false), [err, setErr] = useState("");
  if (!st) return <div className="grid gap-4 md:grid-cols-3">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-28" />)}</div>;
  const tiles = [
    { label: "Người dùng", value: st.users, sub: st.locked ? `${st.locked} tài khoản bị khóa` : "Không có tài khoản bị khóa", to: "/users", icon: Users },
    { label: "Lượt tra cứu", value: st.diagnoses, sub: `${st.today} lượt hôm nay`, icon: ScanLine },
    { label: "Bài chờ duyệt", value: st.pending, sub: `${st.posts.approved || 0} bài đã đăng`, to: "/posts", icon: PenSquare, warn: st.pending > 0 },
    { label: "Bình luận", value: st.comments, sub: st.flagged ? `${st.flagged} bình luận AI chưa duyệt` : "AI đã duyệt hết", to: "/comments", icon: MessageSquare, warn: st.flagged > 0 },
    { label: "Đánh giá trung bình", value: st.ratings ? `${st.rating_avg.toFixed(1).replace(".", ",")}/5` : "–", sub: `${st.ratings} lượt đánh giá`, to: "/ratings", icon: Star },
    { label: "Khóa Gemini đang bật", value: `${st.keys.enabled}/${st.keys.total}`, sub: st.keys.cooling ? `${st.keys.cooling} khóa đang tạm hết lượt` : "Không khóa nào hết lượt", to: "/keys", icon: KeyRound, warn: st.keys.cooling > 0 },
  ];
  const topMax = Math.max(1, ...st.top.map((t) => t.n));
  const broadcast = async () => {
    try { const r = await send<{ sent: number }>("/api/admin/broadcast", { content: content.trim() }); toast.success(`Đã gửi tới ${r.sent} người`); setContent(""); }
    catch (e) { setErr((e as Error).message); throw e; }
  };
  return (
    <div className="space-y-6 animate-fade-up">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        {tiles.map((t) => {
          const inner = (
            <>
              <div className="flex items-center justify-between text-sm text-muted-foreground"><span>{t.label}</span><t.icon className="h-4 w-4" /></div>
              <b className={`mt-1 block text-3xl font-extrabold ${t.warn ? "text-warning" : ""}`}>{t.value}</b>
              <small className="text-muted-foreground">{t.sub}</small>
            </>
          );
          const cls = "block rounded-2xl border bg-card p-4 shadow-soft transition";
          return t.to ? <Link key={t.label} to={t.to} className={`${cls} hover:border-primary`}>{inner}</Link> : <div key={t.label} className={cls}>{inner}</div>;
        })}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Lượt tra cứu 14 ngày qua</CardTitle></CardHeader>
          <CardContent>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={st.daily.map((d) => ({ ...d, label: ddmm(d.day) }))} margin={{ top: 8, right: 4, left: -24, bottom: 0 }}>
                  <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="label" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} interval={1} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} />
                  <Tooltip cursor={{ fill: "hsl(var(--muted))" }} contentStyle={{ borderRadius: 12, border: "1px solid hsl(var(--border))", background: "hsl(var(--card))", color: "hsl(var(--foreground))" }} formatter={(v: number) => [`${v} lượt`, "Tra cứu"]} labelFormatter={(l) => `Ngày ${l}`} />
                  <Bar dataKey="n" fill="hsl(var(--primary))" radius={[6, 6, 0, 0]} maxBarSize={28} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Bệnh gặp nhiều nhất</CardTitle></CardHeader>
          <CardContent>
            {st.top.length ? <ul className="space-y-3">{st.top.map((t) => (
              <li key={t.plant + t.disease} className="text-sm"><div className="mb-1 flex justify-between gap-3"><span className="truncate">{t.plant}: {t.disease}</span><b className="tabular-nums">{t.n}</b></div><Progress value={(t.n / topMax) * 100} className="h-2" /></li>
            ))}</ul> : <p className="text-sm text-muted-foreground">Chưa có lượt tra cứu nào ra bệnh.</p>}
            {st.classes.length > 0 && <p className="mt-4 flex items-center gap-2 text-sm text-muted-foreground"><Bug className="h-4 w-4" />{st.samples} ảnh AI đã lưu trong {st.classes.length} lớp. <Link to="/data" className="font-semibold text-primary">Xem dữ liệu AI</Link></p>}
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader><CardTitle>Gửi thông báo cho mọi người</CardTitle></CardHeader>
        <CardContent>
          <Textarea rows={2} maxLength={300} value={content} onChange={(e) => { setContent(e.target.value); setErr(""); }} placeholder="VD: Mưa nhiều tuần này, bà con chú ý phòng bệnh đạo ôn trên lúa." aria-label="Nội dung thông báo" />
          {err && <p className="mt-1 text-sm font-medium text-destructive">{err}</p>}
          <div className="mt-3 flex items-center justify-between gap-3"><span className="text-xs text-muted-foreground">{content.length}/300</span><Button disabled={!content.trim()} onClick={() => setConfirm(true)}><Bell />Gửi thông báo</Button></div>
          <ConfirmDialog open={confirm} onOpenChange={setConfirm} title={`Gửi thông báo tới ${st.users - st.locked} người dùng?`} description={content} confirmText="Gửi" onConfirm={async () => { await broadcast(); refetch(); }} />
        </CardContent>
      </Card>
    </div>
  );
}
