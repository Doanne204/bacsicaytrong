import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { MailCheck } from "lucide-react";
import { send, ApiError } from "@/shared/lib/api";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Field, Notice } from "@/shared/ui/misc";
import { AuthLayout } from "./AuthLayout";

type State = { email?: string; debug_code?: string; note?: string };

/** Nhập mã 6 số gửi qua email sau khi đăng ký (hoặc khi đăng nhập tài khoản chưa xác thực). */
export default function Verify() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const st = (useLocation().state as State) || {};
  const [email, setEmail] = useState(st.email || ""), [code, setCode] = useState(""), [err, setErr] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false), [wait, setWait] = useState(60), [debug, setDebug] = useState(st.debug_code);
  useEffect(() => { if (wait <= 0) return; const t = setTimeout(() => setWait(wait - 1), 1000); return () => clearTimeout(t); }, [wait]);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!/^\d{6}$/.test(code)) return setErr({ code: "Mã gồm 6 chữ số" });
    setBusy(true); setErr({});
    try { await send("/api/verify", { email, code }); await qc.invalidateQueries({ queryKey: ["me"] }); toast.success("Đã xác thực email"); nav("/home", { replace: true }); }
    catch (e) { setErr({ [e instanceof ApiError && e.field ? e.field : "form"]: (e as Error).message }); } finally { setBusy(false); }
  };
  const resend = async () => {
    try { const r = await send<{ debug_code?: string }>("/api/verify/resend", { email }); setWait(60); setDebug(r.debug_code); toast.success(r.debug_code ? "Mã mới hiện bên dưới (chưa cấu hình gửi email)" : "Đã gửi lại mã, hãy kiểm tra hộp thư"); }
    catch (e) { toast.error((e as Error).message); }
  };
  return (
    <AuthLayout title="Xác thực email" text="Nhập mã 6 số vừa gửi tới email của bạn. Mã có hiệu lực 15 phút.">
      <form onSubmit={submit} noValidate className="space-y-4">
        {err.form && <p role="alert" className="rounded-xl bg-destructive/10 px-4 py-3 text-sm font-semibold text-destructive">{err.form}</p>}
        {debug && <Notice tone="warn" icon={MailCheck}>Máy chủ chưa cấu hình gửi email (SMTP), mã thử là <b className="text-base tracking-widest">{debug}</b>.</Notice>}
        <Field label="Email" htmlFor="email"><Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} readOnly={!!st.email} /></Field>
        <Field label="Mã xác thực" htmlFor="code" error={err.code}>
          <Input id="code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className="text-center text-2xl font-bold tracking-[.4em]" autoFocus aria-invalid={!!err.code} />
        </Field>
        <Button type="submit" size="lg" className="w-full" loading={busy}><MailCheck />Xác nhận</Button>
        <Button type="button" variant="ghost" className="w-full" disabled={wait > 0 || !email} onClick={resend}>{wait > 0 ? `Gửi lại mã sau ${wait}s` : "Gửi lại mã"}</Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted-foreground">Nhầm email? <Link to="/register" className="font-semibold text-primary hover:underline">Đăng ký lại</Link> · <Link to="/login" className="font-semibold text-primary hover:underline">Đăng nhập</Link></p>
    </AuthLayout>
  );
}
