import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff } from "lucide-react";
import { send, ApiError } from "@/shared/lib/api";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Field } from "@/shared/ui/misc";
import { AuthLayout } from "./AuthLayout";
import { GoogleSignIn } from "../components/google-signin";

export default function Login() {
  const nav = useNavigate();
  const loc = useLocation();
  const qc = useQueryClient();
  const [u, setU] = useState(""), [p, setP] = useState(""), [show, setShow] = useState(false);
  const [err, setErr] = useState<Record<string, string>>({}), [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const er: Record<string, string> = {};
    if (!u.trim()) er.u = "Hãy nhập tên đăng nhập, email hoặc số điện thoại";
    if (!p) er.p = "Hãy nhập mật khẩu";
    setErr(er);
    if (Object.keys(er).length) return;
    setBusy(true);
    try {
      await send("/api/login", { username: u.trim(), password: p });
      await qc.invalidateQueries({ queryKey: ["me"] });
      nav((loc.state as { from?: string })?.from || "/home", { replace: true });
    } catch (e) {
      if (e instanceof ApiError && e.field === "unverified") return nav("/verify", { state: { email: e.email } });
      setErr({ form: e instanceof ApiError ? e.message : "Không kết nối được máy chủ" });
    } finally { setBusy(false); }
  };
  return (
    <AuthLayout title="Đăng nhập" text="Dùng tên đăng nhập, email hoặc số điện thoại.">
      <GoogleSignIn mode="signin" next={(loc.state as { from?: string })?.from || "/home"} />
      <form onSubmit={submit} noValidate className="space-y-4">
        {err.form && <p role="alert" className="rounded-xl bg-destructive/10 px-4 py-3 text-sm font-semibold text-destructive">{err.form}</p>}
        <Field label="Tài khoản" htmlFor="u" error={err.u}><Input id="u" autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} aria-invalid={!!err.u} autoFocus /></Field>
        <Field label="Mật khẩu" htmlFor="p" error={err.p}>
          <div className="relative">
            <Input id="p" type={show ? "text" : "password"} autoComplete="current-password" value={p} onChange={(e) => setP(e.target.value)} aria-invalid={!!err.p} className="pr-12" />
            <button type="button" onClick={() => setShow(!show)} className="absolute right-1 top-1 rounded-lg p-2 text-muted-foreground hover:bg-accent" aria-label={show ? "Ẩn mật khẩu" : "Hiện mật khẩu"}>{show ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}</button>
          </div>
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={busy}>Đăng nhập</Button>
        <p className="text-right text-sm"><Link to="/forgot" className="font-semibold text-primary hover:underline">Quên mật khẩu?</Link></p>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">Chưa có tài khoản? <Link to="/register" className="font-semibold text-primary hover:underline">Đăng ký</Link></p>
    </AuthLayout>
  );
}
