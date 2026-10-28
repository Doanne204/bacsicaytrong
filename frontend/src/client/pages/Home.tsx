import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlarmClock, Camera, CheckCircle2, ChevronRight, Clock, CloudSun, ImagePlus, Info, Leaf, MessageCircle, NotebookPen, PenSquare, ShieldAlert, Star } from "lucide-react";
import { toast } from "sonner";
import { api, send, type DueReminder, type HistoryItem, type WeatherReport } from "@/shared/lib/api";
import { ago, cn, dayKey, ddmm, liveCamera, pct, pickFile, toDate } from "@/shared/lib/utils";
import { useMe } from "@/shared/hooks/use-me";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";
import { Avatar, EmptyState, Notice, Skeleton } from "@/shared/ui/misc";
import { Tabs, TabsList, TabsTrigger } from "@/shared/ui/tabs";
import { PostCard, fetchPosts } from "../components/posts";
import { LEVEL } from "../components/weather";
import { WxIcon } from "../components/sky";
import { dueLabel } from "../components/journal";
import { pending } from "./Scan";

const WEEKDAYS = ["Chủ nhật", "Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy"];

/** Dữ liệu dùng chung của trang chủ (cùng khóa truy vấn với trang Nhật ký, Thời tiết nên không tải hai lần). */
function useToday() {
  const { me } = useMe();
  const loc = me?.location || null;
  const weather = useQuery({ queryKey: ["weather", loc?.lat, loc?.lon], queryFn: () => api<WeatherReport>("/api/weather"), enabled: !!loc, staleTime: 15 * 60_000, retry: false });
  const todo = useQuery({ queryKey: ["reminders"], queryFn: () => api<DueReminder[]>("/api/reminders") });
  const today = dayKey(new Date());
  const now = (todo.data || []).filter((r) => r.overdue || dayKey(toDate(r.due)) === today);
  return { loc, weather, todo, now, later: (todo.data || []).filter((r) => !now.includes(r)) };
}

export default function Home({ mine = false }: { mine?: boolean }) {
  const { me } = useMe();
  const nav = useNavigate();
  const posts = useQuery({ queryKey: ["posts", mine], queryFn: () => fetchPosts(mine) });
  const t = useToday();
  const pick = async (capture: boolean) => {
    if (capture && liveCamera()) return nav("/scan/camera");
    const f = await pickFile(capture);
    if (f) { pending.file = f; nav("/scan"); }
  };
  return (
    <div className="animate-fade-up">
      <Hero name={me?.username} t={t} onPick={pick} />
      {me && !me.phone && <Notice icon={Info} className="mb-5">Tài khoản chưa có số điện thoại. <Link to="/profile" className="font-semibold text-primary">Bổ sung trong hồ sơ</Link>.</Notice>}
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-8">
          <TodayTasks t={t} />
          <RecentScans />
          <section>
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="text-lg font-bold">Cộng đồng nhà nông</h2>
              <Tabs value={mine ? "mine" : "all"} onValueChange={(v) => nav(v === "mine" ? "/home/mine" : "/home")}>
                <TabsList><TabsTrigger value="all">Tất cả</TabsTrigger><TabsTrigger value="mine">Bài của tôi</TabsTrigger></TabsList>
              </Tabs>
            </div>
            <Link to="/post" className="mb-3 flex items-center gap-3 rounded-2xl border-2 border-dashed p-3 text-muted-foreground transition hover:border-primary"><Avatar name={me?.username} size="sm" /><span className="flex-1">Hỏi bà con hoặc chia sẻ kinh nghiệm trồng trọt…</span><ImagePlus className="h-5 w-5" /></Link>
            {posts.isLoading ? <div className="space-y-4">{[0, 1].map((i) => <Skeleton key={i} className="h-48" />)}</div>
              : posts.data?.length ? <div>{posts.data.map((p) => <PostCard key={p.id} p={p} onChange={() => posts.refetch()} />)}</div>
              : <EmptyState icon={PenSquare} title={mine ? "Bạn chưa đăng bài nào" : "Chưa có bài viết nào"} text="Chia sẻ kinh nghiệm hoặc hỏi bà con về sâu bệnh." action={<Button asChild variant="outline"><Link to="/post">Viết bài đầu tiên</Link></Button>} />}
          </section>
        </div>
        <aside className="space-y-6">
          <AlertsCard t={t} />
          <nav aria-label="Lối tắt">
            <h2 className="mb-2 font-bold">Lối tắt</h2>
            <ul className="overflow-hidden rounded-2xl border bg-card">
              {([["/journal", NotebookPen, "Nhật ký điều trị", "Lịch phun, kiểm tra cây"], ["/weather", CloudSun, "Thời tiết, cảnh báo", "Dự báo 7 ngày cho vườn"],
                ["/chat", MessageCircle, "Hỏi trợ lý AI", "Hỏi về sâu bệnh, thuốc"], ["/history", Clock, "Lịch sử tra cứu", "Các lần chụp trước"],
                ["/ratings", Star, "Đánh giá của tôi", "Kết quả bạn đã chấm"]] as const).map(([to, Icon, l, sub]) => (
                <li key={to} className="border-b last:border-0">
                  <Link to={to} className="flex items-center gap-3 px-4 py-3 transition hover:bg-secondary/60">
                    <Icon className="h-5 w-5 shrink-0 text-primary" />
                    <span className="min-w-0 flex-1"><b className="block text-sm">{l}</b><span className="text-xs text-muted-foreground">{sub}</span></span>
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </aside>
      </div>
    </div>
  );
}

type Today = ReturnType<typeof useToday>;

/** Đầu trang: lời chào, nút chụp ảnh lớn và tình hình hôm nay của vườn (thời tiết, việc cần làm, cảnh báo cao nhất). */
function Hero({ name, t, onPick }: { name?: string; t: Today; onPick: (capture: boolean) => void }) {
  const d = new Date(), w = t.weather.data, cur = w?.current;
  const alert = w?.alerts.find((a) => a.level === "cao") || w?.alerts.find((a) => a.level === "vua");
  const hour = d.getHours(), hi = hour < 11 ? "Chào buổi sáng" : hour < 14 ? "Chào buổi trưa" : hour < 18 ? "Chào buổi chiều" : "Chào buổi tối";
  return (
    <section className="home-hero relative mb-6 overflow-hidden rounded-[28px] p-5 sm:p-7 md:p-8">
      <svg aria-hidden className="pointer-events-none absolute -right-10 -top-6 h-[120%] w-auto opacity-[0.13]" viewBox="0 0 200 260" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
        <path d="M100 250C40 200 18 120 60 50c18-30 52-44 80-40-6 30 2 70-10 110-14 48-26 86-30 130z" />
        <path d="M100 250c4-60 10-120 34-200" /><path d="M108 200c-22-12-40-30-52-56" /><path d="M114 160c16-14 30-34 36-58" />
        <path d="M118 120c-20-10-34-26-42-46" /><path d="M124 86c12-12 20-28 22-44" />
      </svg>
      <div className="relative">
        <p className="text-sm font-medium opacity-80">{WEEKDAYS[d.getDay()]}, {ddmm(dayKey(d))}{t.loc?.place ? `, ${t.loc.place.split(",")[0]}` : ""}</p>
        <h1 className="mt-1 text-2xl font-extrabold leading-tight sm:text-[1.75rem] md:text-4xl">{hi}, {name}</h1>
        <p className="mt-1 max-w-[42ch] text-sm opacity-90 sm:text-[15px]">Lá có đốm lạ hay thấy sâu trên cây? Chụp một tấm để biết bệnh gì và cách xử lý.</p>
        <div className="mt-5 grid grid-cols-2 gap-2.5 sm:flex">
          <Button variant="paddy" size="lg" className="h-12 px-4 text-base sm:px-6" onClick={() => onPick(true)}><Camera className="!h-5 !w-5" />Chụp ảnh<span className="hidden sm:inline">&nbsp;lá, sâu</span></Button>
          <Button size="lg" className="h-12 border border-white/40 bg-white/10 px-4 text-white hover:bg-white/20" onClick={() => onPick(false)}><ImagePlus />Chọn ảnh<span className="hidden sm:inline">&nbsp;có sẵn</span></Button>
        </div>
        {/* điện thoại: vuốt ngang; màn rộng: 3 cột */}
        <div className="-mx-5 mt-5 flex snap-x scroll-px-5 gap-2 overflow-x-auto px-5 pb-0.5 no-scrollbar sm:mx-0 sm:mt-6 sm:grid sm:grid-cols-3 sm:overflow-visible sm:px-0 [&>a]:w-[15rem] [&>a]:shrink-0 [&>a]:snap-start sm:[&>a]:w-auto">
          <Link to="/weather" className="home-chip">
            {cur ? <WxIcon code={cur.code} isDay={cur.is_day} size={30} /> : <CloudSun className="h-6 w-6" />}
            <span className="min-w-0"><b className="block truncate">{cur ? `${Math.round(cur.temp)}°C, ${cur.desc.toLowerCase()}` : t.loc ? "Đang tải thời tiết" : "Đặt vị trí vườn"}</b>
              <span className="block truncate text-xs opacity-80">{cur ? `Độ ẩm ${cur.rh ?? "-"}%` : "Để nhận dự báo, cảnh báo"}</span></span>
          </Link>
          <Link to="/journal" className="home-chip">
            <AlarmClock className="h-6 w-6 shrink-0" />
            <span className="min-w-0"><b className="block truncate">{t.now.length ? `${t.now.length} việc cần làm hôm nay` : "Hôm nay chưa có việc"}</b>
              <span className="block truncate text-xs opacity-80">{t.later.length ? `${t.later.length} việc trong 7 ngày tới` : "Xem lịch chăm sóc"}</span></span>
          </Link>
          <Link to="/weather" className="home-chip">
            <ShieldAlert className={cn("h-6 w-6 shrink-0", alert?.level === "cao" && "text-paddy")} />
            <span className="min-w-0"><b className="block truncate">{alert ? alert.name : w ? "Chưa có nguy cơ sâu bệnh" : "Cảnh báo sâu bệnh"}</b>
              <span className="block truncate text-xs opacity-80">{alert ? `${LEVEL[alert.level].label}, ${alert.days.slice(0, 2).map(ddmm).join(", ")}` : w ? "Trong 5 ngày tới" : "Theo thời tiết nơi bạn ở"}</span></span>
          </Link>
        </div>
      </div>
    </section>
  );
}

/** Việc hôm nay (kể cả quá hạn) đánh dấu xong ngay tại chỗ; việc các ngày tới chỉ đếm, xem chi tiết trong lịch chăm sóc. */
function TodayTasks({ t }: { t: Today }) {
  const qc = useQueryClient();
  if (t.todo.isLoading) return <Skeleton className="h-28" />;
  if (!t.todo.data?.length) return null;
  const done = async (r: DueReminder) => {
    try { await send(`/api/reminders/${r.id}`, { done: 1 }, "PUT"); toast.success("Đã ghi vào nhật ký"); ["reminders", "me", "treatments", "agenda"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })); }
    catch (e) { toast.error((e as Error).message); }
  };
  const list = t.now.length ? t.now : t.later.slice(0, 3);
  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-lg font-bold">{t.now.length ? "Việc hôm nay" : "Việc sắp tới"}</h2>
        <Link to="/journal" className="text-sm font-semibold text-primary">Lịch chăm sóc</Link>
      </div>
      <ul className="divide-y rounded-2xl border bg-card">
        {list.map((r) => (
          <li key={r.id} className="flex items-center gap-3 px-4 py-3 text-sm">
            <button type="button" onClick={() => done(r)} className="grid h-8 w-8 shrink-0 place-items-center rounded-full border-2 border-primary text-primary transition hover:bg-primary hover:text-primary-foreground" aria-label={`Đánh dấu đã làm: ${r.content}`}><CheckCircle2 className="h-4 w-4" /></button>
            <Link to={`/journal/${r.treatment_id}`} className="min-w-0 flex-1"><b className="block">{r.content}</b>
              <span className="text-xs text-muted-foreground">{r.name || `${r.plant}: ${r.disease}`}<span className={cn("sm:hidden", r.overdue && "font-semibold text-destructive")}>, {dueLabel(r.due)}</span></span></Link>
            <span className={cn("hidden shrink-0 text-xs font-semibold sm:block", r.overdue ? "text-destructive" : "text-muted-foreground")}>{dueLabel(r.due)}</span>
          </li>
        ))}
      </ul>
      {t.now.length > 0 && t.later.length > 0 && <p className="mt-1.5 text-xs text-muted-foreground">Còn {t.later.length} việc trong 7 ngày tới.</p>}
    </section>
  );
}

/** Dải ảnh tra cứu gần đây, vuốt ngang trên điện thoại. */
function RecentScans() {
  const q = useQuery({ queryKey: ["history"], queryFn: () => api<HistoryItem[]>("/api/history") });
  if (q.isLoading) return <Skeleton className="h-40" />;
  if (!q.data?.length) return null;
  return (
    <section>
      <div className="mb-2 flex items-center justify-between"><h2 className="text-lg font-bold">Tra cứu gần đây</h2><Link to="/history" className="text-sm font-semibold text-primary">Xem tất cả</Link></div>
      <div className="-mx-4 flex snap-x scroll-px-4 gap-3 overflow-x-auto px-4 pb-1 no-scrollbar lg:mx-0 lg:scroll-px-0 lg:px-0">
        {q.data.slice(0, 8).map((it) => (
          <Link key={it.id} to={`/diagnosis/${it.id}`} className="group w-40 shrink-0 snap-start">
            <div className="relative aspect-square overflow-hidden rounded-2xl bg-secondary">
              {it.image_url ? <img src={it.image_url} alt="" loading="lazy" className="h-full w-full object-cover transition group-hover:scale-[1.03]" /> : <Leaf className="m-auto h-8 w-8 text-primary" />}
              {!it.healthy && it.confidence > 0 && <span className="absolute bottom-1.5 left-1.5 rounded-md bg-black/60 px-1.5 py-0.5 text-[11px] font-semibold text-white">{pct(it.confidence)}</span>}
            </div>
            <b className="mt-1.5 block truncate text-sm">{it.disease}</b>
            <span className="block truncate text-xs text-muted-foreground">{it.plant}, {ago(it.created)}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}

/** Cảnh báo sâu bệnh theo thời tiết (khi đã lưu vị trí). */
function AlertsCard({ t }: { t: Today }) {
  if (!t.loc) return (
    <Link to="/weather" className="flex items-center gap-3 rounded-2xl border border-dashed p-4 text-sm transition hover:border-primary">
      <CloudSun className="h-7 w-7 shrink-0 text-primary" /><span><b className="block">Cảnh báo sâu bệnh theo thời tiết</b><span className="text-muted-foreground">Đặt vị trí vườn để nhận dự báo và cảnh báo.</span></span>
    </Link>
  );
  if (t.weather.isLoading) return <Skeleton className="h-36" />;
  const w = t.weather.data;
  if (!w) return null;
  const alerts = w.alerts.filter((a) => a.level !== "thap").slice(0, 4);
  return (
    <section>
      <div className="mb-2 flex items-center justify-between"><h2 className="font-bold">Nguy cơ sâu bệnh 5 ngày tới</h2><Link to="/weather" className="text-sm font-semibold text-primary">Chi tiết</Link></div>
      <div className="rounded-2xl border bg-card p-4">
        {alerts.length ? <ul className="space-y-2.5">{alerts.map((a) => (
          <li key={a.key} className="text-sm">
            <div className="flex items-center gap-2"><Badge variant={LEVEL[a.level].badge} className="shrink-0">{LEVEL[a.level].label}</Badge><b className="min-w-0 flex-1 truncate">{a.name}</b></div>
            <p className="mt-0.5 text-xs text-muted-foreground">{a.mine ? "Liên quan cây của bạn. " : ""}Ngày {a.days.slice(0, 3).map(ddmm).join(", ")}</p>
          </li>
        ))}</ul> : <p className="text-sm text-muted-foreground">Thời tiết 5 ngày tới chưa thuận lợi cho sâu bệnh phát triển.</p>}
      </div>
    </section>
  );
}
