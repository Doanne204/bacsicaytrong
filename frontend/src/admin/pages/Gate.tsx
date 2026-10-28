import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Shield } from "lucide-react";
import { send, ApiError, type Me } from "@/shared/lib/api";
import { Brand } from "@/shared/components/brand";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Field, Notice } from "@/shared/ui/misc";

/** Màn hình đăng nhập quản trị: tài khoản thường bị từ chối, phiên hiện có giữ nguyên. */
export default function Gate({ me }: { me: Me | null }) {
  const qc = useQueryClient();
  const [u, setU] = useState(""), [p, setP] = useState(""), [err, setErr] = useState<Record<string, string>>({}), [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const er: Record<string, string> = {};
    if (!u.trim()) er.u = "Hãy nhập tên đăng nhập, email hoặc số điện thoại";
    if (!p) er.p = "Hãy nhập mật khẩu";
    setErr(er); if (Object.keys(er).length) return;
    setBusy(true);
    try { await send("/api/admin/login", { username: u.trim(), password: p }); await qc.invalidateQueries({ queryKey: ["me"] }); }
    catch (e) { setErr({ form: e instanceof ApiError ? e.message : "Không kết nối được máy chủ" }); } finally { setBusy(false); }
  };
  return (
    <main className="grid min-h-dvh place-items-center bg-[#1F4A28] p-4 leaf-pattern">
      <div className="w-full max-w-md rounded-3xl bg-background p-6 shadow-lift sm:p-8 animate-fade-up">
        <div className="mb-6 rounded-2xl bg-[#1F4A28] p-3"><Brand light sub="Trang quản trị" /></div>
        <h1 className="text-2xl font-extrabold">Đăng nhập quản trị</h1>
        <p className="mb-5 text-sm text-muted-foreground">Chỉ tài khoản quản trị viên mới vào được trang này.</p>
        {me && <Notice tone="warn" icon={Shield} className="mb-4">Bạn đang đăng nhập bằng tài khoản thường <b>{me.username}</b>. Đăng nhập tài khoản quản trị bên dưới để tiếp tục.</Notice>}
        <form onSubmit={submit} noValidate className="space-y-4">
          {err.form && <p role="alert" className="rounded-xl bg-destructive/10 px-4 py-3 text-sm font-semibold text-destructive">{err.form}</p>}
          <Field label="Tài khoản quản trị" htmlFor="u" error={err.u}><Input id="u" autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} aria-invalid={!!err.u} autoFocus /></Field>
          <Field label="Mật khẩu" htmlFor="p" error={err.p}><Input id="p" type="password" autoComplete="current-password" value={p} onChange={(e) => setP(e.target.value)} aria-invalid={!!err.p} /></Field>
          <Button type="submit" size="lg" className="w-full" loading={busy}><Shield />Vào trang quản trị</Button>
        </form>
        <a href="/" className="mt-5 inline-flex items-center gap-1 text-sm font-semibold text-muted-foreground hover:text-primary"><ArrowLeft className="h-4 w-4" />Về ứng dụng người dùng</a>
      </div>
    </main>
  );
}
