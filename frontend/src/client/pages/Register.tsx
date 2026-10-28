import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { send, ApiError } from "@/shared/lib/api";
import { RE, MSG, normPhone } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Field } from "@/shared/ui/misc";
import { AuthLayout } from "./AuthLayout";

type F = { username: string; phone: string; email: string; password: string; password2: string };
const check: Record<keyof F, (v: string, f: F) => string> = {
  username: (v) => (RE.username.test(v) ? "" : MSG.username),
  phone: (v) => (RE.phone.test(normPhone(v)) ? "" : MSG.phone),
  email: (v) => (RE.email.test(v) ? "" : MSG.email),
  password: (v) => (v.length >= 6 ? "" : MSG.password),
  password2: (v, f) => (v === f.password ? "" : "Mật khẩu nhập lại không khớp"),
};

export default function Register() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [f, setF] = useState<F>({ username: "", phone: "", email: "", password: "", password2: "" });
  const [err, setErr] = useState<Partial<Record<keyof F | "form", string>>>({}), [busy, setBusy] = useState(false);
  const set = (k: keyof F) => (e: React.ChangeEvent<HTMLInputElement>) => { setF({ ...f, [k]: e.target.value }); if (err[k]) setErr({ ...err, [k]: "" }); };
  const blur = (k: keyof F) => () => { if (f[k]) setErr({ ...err, [k]: check[k](f[k].trim(), f) }); };
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const er: typeof err = {};
    (Object.keys(check) as (keyof F)[]).forEach((k) => { const m = check[k](k.startsWith("password") ? f[k] : f[k].trim(), f); if (m) er[k] = m; });
    setErr(er);
    if (Object.keys(er).length) { document.getElementById(Object.keys(er)[0])?.focus(); return; }
    setBusy(true);
    try {
      const body = { username: f.username.trim(), phone: normPhone(f.phone), email: f.email.trim().toLowerCase(), password: f.password };
      const r = await send<{ sent: boolean; debug_code?: string; note?: string }>("/api/register", body);
      toast.success(r.sent ? "Đã gửi mã xác thực tới email của bạn" : "Đã tạo tài khoản, hãy nhập mã xác thực");
      nav("/verify", { state: { email: body.email, debug_code: r.debug_code, note: r.note } });
    } catch (e) {
      if (e instanceof ApiError && e.field) { setErr({ [e.field]: e.message }); document.getElementById(e.field)?.focus(); }
      else setErr({ form: e instanceof ApiError ? e.message : "Không kết nối được máy chủ" });
    } finally { setBusy(false); }
  };
  const pw = (id: "password" | "password2", label: string, ac: string) => (
    <Field label={label} htmlFor={id} error={err[id]}><Input id={id} type="password" autoComplete={ac} value={f[id]} onChange={set(id)} onBlur={blur(id)} aria-invalid={!!err[id]} /></Field>
  );
  return (
    <AuthLayout title="Tạo tài khoản" text="Mỗi số điện thoại và email chỉ đăng ký được một tài khoản.">
      <form onSubmit={submit} noValidate className="space-y-4">
        {err.form && <p role="alert" className="rounded-xl bg-destructive/10 px-4 py-3 text-sm font-semibold text-destructive">{err.form}</p>}
        <Field label="Tên đăng nhập" htmlFor="username" error={err.username} hint="Chữ không dấu, số, dấu _ hoặc ."><Input id="username" autoComplete="username" maxLength={30} value={f.username} onChange={set("username")} onBlur={blur("username")} aria-invalid={!!err.username} /></Field>
        <Field label="Số điện thoại" htmlFor="phone" error={err.phone}><Input id="phone" type="tel" inputMode="tel" autoComplete="tel" placeholder="0912 345 678" value={f.phone} onChange={set("phone")} onBlur={blur("phone")} aria-invalid={!!err.phone} /></Field>
        <Field label="Email" htmlFor="email" error={err.email}><Input id="email" type="email" inputMode="email" autoComplete="email" placeholder="ten@gmail.com" value={f.email} onChange={set("email")} onBlur={blur("email")} aria-invalid={!!err.email} /></Field>
        {pw("password", "Mật khẩu", "new-password")}
        {pw("password2", "Nhập lại mật khẩu", "new-password")}
        <Button type="submit" size="lg" className="w-full" loading={busy}>Tạo tài khoản</Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">Đã có tài khoản? <Link to="/login" className="font-semibold text-primary hover:underline">Đăng nhập</Link></p>
    </AuthLayout>
  );
}
