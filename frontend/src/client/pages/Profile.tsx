import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Bell, CloudSun, LogOut, PenSquare, Shield, ChevronRight, Star } from "lucide-react";
import { send, ApiError } from "@/shared/lib/api";
import { fmtDate, MSG, normPhone, RE, toDate } from "@/shared/lib/utils";
import { useLogout, useMe } from "@/shared/hooks/use-me";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Avatar, Field } from "@/shared/ui/misc";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { ThemeToggle } from "@/shared/components/common";
import { LocationPicker } from "../components/weather";

export default function Profile() {
  const { me } = useMe();
  const qc = useQueryClient();
  const nav = useNavigate();
  const logout = useLogout();
  const [phone, setPhone] = useState(me?.phone || ""), [email, setEmail] = useState(me?.email || "");
  const [oldPw, setOldPw] = useState(""), [newPw, setNewPw] = useState("");
  const [err, setErr] = useState<Record<string, string>>({}), [busy, setBusy] = useState("");
  if (!me) return null;
  const saveInfo = async (e: React.FormEvent) => {
    e.preventDefault();
    const ph = normPhone(phone), em = email.trim(), er: Record<string, string> = {};
    if (!RE.phone.test(ph)) er.phone = MSG.phone;
    if (!RE.email.test(em)) er.email = MSG.email;
    setErr(er); if (Object.keys(er).length) return;
    setBusy("info");
    try { await send("/api/me", { phone: ph, email: em }, "PUT"); toast.success("Đã lưu thay đổi"); qc.invalidateQueries({ queryKey: ["me"] }); }
    catch (e) { if (e instanceof ApiError && e.field) setErr({ [e.field]: e.message }); else toast.error((e as Error).message); } finally { setBusy(""); }
  };
  const savePw = async (e: React.FormEvent) => {
    e.preventDefault();
    const er: Record<string, string> = {};
    if (!oldPw) er.old_password = "Hãy nhập mật khẩu hiện tại";
    if (newPw.length < 6) er.new_password = MSG.password;
    setErr(er); if (Object.keys(er).length) return;
    setBusy("pw");
    try { await send("/api/me/password", { old_password: oldPw, new_password: newPw }); toast.success("Đã đổi mật khẩu"); setOldPw(""); setNewPw(""); }
    catch (e) { if (e instanceof ApiError && e.field) setErr({ [e.field]: e.message }); else toast.error((e as Error).message); } finally { setBusy(""); }
  };
  const menu = (
    <nav className="divide-y rounded-2xl border bg-card">
      {[["/notifications", Bell, `Thông báo${me.unread ? ` (${me.unread} chưa đọc)` : ""}`], ["/home/mine", PenSquare, "Bài viết của tôi"], ["/ratings", Star, "Đánh giá của tôi"], ["/weather", CloudSun, "Cảnh báo thời tiết"], ...(me.role === "admin" ? [["/admin", Shield, "Trang quản trị"]] : [])].map(([to, Icon, l]) => {
        const I = Icon as React.ComponentType<{ className?: string }>, href = to as string;
        const inner = <><I className="h-5 w-5 text-primary" /><span className="flex-1">{l as string}</span><ChevronRight className="h-4 w-4 text-muted-foreground" /></>;
        const cls = "flex items-center gap-3 px-4 py-3.5 text-sm font-semibold transition hover:bg-accent";
        return href === "/admin" ? <a key={href} href={href} className={cls}>{inner}</a> : <Link key={href} to={href} className={cls}>{inner}</Link>;
      })}
      <div className="flex items-center gap-3 px-4 py-2 text-sm font-semibold"><span className="flex-1">Giao diện sáng/tối</span><ThemeToggle /></div>
      <button type="button" onClick={async () => { await logout(); nav("/login"); }} className="flex w-full items-center gap-3 px-4 py-3.5 text-sm font-semibold text-destructive transition hover:bg-destructive/10"><LogOut className="h-5 w-5" />Đăng xuất</button>
    </nav>
  );
  return (
    <div className="grid grid-cols-1 gap-6 animate-fade-up lg:grid-cols-[340px_minmax(0,1fr)]">
      <aside className="space-y-5">
        <section className="flex items-center gap-4"><Avatar name={me.username} size="lg" /><div><h1 className="text-2xl font-extrabold">{me.username}</h1><p className="text-sm text-muted-foreground">{me.role === "admin" ? "Quản trị viên, " : ""}tham gia {fmtDate(toDate(me.created))}</p></div></section>
        <nav className="grid grid-cols-3 divide-x rounded-2xl border bg-card text-center">
          {[["/history", me.stats.scans, "Lần tra cứu"], ["/journal", me.stats.treatments, "Đang điều trị"], ["/home/mine", me.stats.posts, "Bài đã đăng"]].map(([to, n, l]) => <Link key={to as string} to={to as string} className="py-3.5 hover:bg-accent"><b className="block text-2xl">{n as number}</b><span className="text-xs text-muted-foreground">{l as string}</span></Link>)}
        </nav>
        <div className="hidden lg:block">{menu}</div>
      </aside>
      <section className="space-y-5">
        <Card>
          <CardHeader><CardTitle>Vị trí vườn / ruộng</CardTitle></CardHeader>
          <CardContent><LocationPicker value={me.location} compact /><p className="mt-2 text-xs text-muted-foreground">Dùng cho cảnh báo sâu bệnh theo thời tiết và ghim ca bệnh lên bản đồ chung (ẩn danh, làm tròn ~1 km).</p></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Thông tin liên hệ</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={saveInfo} noValidate className="space-y-4">
              <Field label="Số điện thoại" htmlFor="phone" error={err.phone}><Input id="phone" type="tel" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="0912 345 678" aria-invalid={!!err.phone} /></Field>
              <Field label="Email" htmlFor="email" error={err.email}><Input id="email" type="email" inputMode="email" value={email} onChange={(e) => setEmail(e.target.value)} aria-invalid={!!err.email} /></Field>
              <Button type="submit" loading={busy === "info"}>Lưu thay đổi</Button>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Đổi mật khẩu</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={savePw} noValidate className="space-y-4">
              <Field label="Mật khẩu hiện tại" htmlFor="old_password" error={err.old_password}><Input id="old_password" type="password" autoComplete="current-password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} aria-invalid={!!err.old_password} /></Field>
              <Field label="Mật khẩu mới" htmlFor="new_password" error={err.new_password}><Input id="new_password" type="password" autoComplete="new-password" value={newPw} onChange={(e) => setNewPw(e.target.value)} aria-invalid={!!err.new_password} /></Field>
              <Button type="submit" variant="secondary" loading={busy === "pw"}>Đổi mật khẩu</Button>
            </form>
          </CardContent>
        </Card>
        <div className="lg:hidden">{menu}</div>
      </section>
    </div>
  );
}
