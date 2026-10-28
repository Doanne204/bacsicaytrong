import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { KeyRound, MailCheck } from "lucide-react";
import { send, ApiError } from "@/shared/lib/api";
import { RE, MSG } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Field, Notice } from "@/shared/ui/misc";
import { AuthLayout } from "./AuthLayout";

/** Quên mật khẩu: bước 1 nhập email nhận mã, bước 2 nhập mã và mật khẩu mới. */
export default function Forgot() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [step, setStep] = useState<1 | 2>(1), [email, setEmail] = useState(""), [code, setCode] = useState(""), [pw, setPw] = useState("");
  const [err, setErr] = useState<Record<string, string>>({}), [busy, setBusy] = useState(false), [debug, setDebug] = useState<string | undefined>();
  const sendCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!RE.email.test(email.trim())) return setErr({ email: MSG.email });
    setBusy(true); setErr({});
    try { const r = await send<{ debug_code?: string }>("/api/password/forgot", { email: email.trim() }); setDebug(r.debug_code); setStep(2); }
    catch (e) { setErr({ form: (e as Error).message }); } finally { setBusy(false); }
  };
  const reset = async (e: React.FormEvent) => {
    e.preventDefault();
    const er: Record<string, string> = {};
    if (!/^\d{6}$/.test(code)) er.code = "Mã gồm 6 chữ số";
    if (pw.length < 6) er.new_password = MSG.password;
    setErr(er); if (Object.keys(er).length) return;
    setBusy(true);
    try { await send("/api/password/reset", { email: email.trim(), code, new_password: pw }); await qc.invalidateQueries({ queryKey: ["me"] }); toast.success("Đã đổi mật khẩu"); nav("/home", { replace: true }); }
    catch (e) { setErr({ [e instanceof ApiError && e.field ? e.field : "form"]: (e as Error).message }); } finally { setBusy(false); }
  };
  return (
    <AuthLayout title="Quên mật khẩu" text={step === 1 ? "Nhập email đã đăng ký, chúng tôi sẽ gửi mã đặt lại mật khẩu." : `Nhập mã đã gửi tới ${email} và mật khẩu mới.`}>
      {step === 1 ? (
        <form onSubmit={sendCode} noValidate className="space-y-4">
          {err.form && <p role="alert" className="rounded-xl bg-destructive/10 px-4 py-3 text-sm font-semibold text-destructive">{err.form}</p>}
          <Field label="Email" htmlFor="email" error={err.email}><Input id="email" type="email" inputMode="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus aria-invalid={!!err.email} /></Field>
          <Button type="submit" size="lg" className="w-full" loading={busy}><MailCheck />Gửi mã</Button>
        </form>
      ) : (
        <form onSubmit={reset} noValidate className="space-y-4">
          {err.form && <p role="alert" className="rounded-xl bg-destructive/10 px-4 py-3 text-sm font-semibold text-destructive">{err.form}</p>}
          {debug && <Notice tone="warn" icon={MailCheck}>Máy chủ chưa cấu hình gửi email (SMTP), mã thử là <b className="text-base tracking-widest">{debug}</b>.</Notice>}
          <Field label="Mã đặt lại" htmlFor="code" error={err.code}><Input id="code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} className="text-center text-2xl font-bold tracking-[.4em]" autoFocus aria-invalid={!!err.code} /></Field>
          <Field label="Mật khẩu mới" htmlFor="new_password" error={err.new_password}><Input id="new_password" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} aria-invalid={!!err.new_password} /></Field>
          <Button type="submit" size="lg" className="w-full" loading={busy}><KeyRound />Đổi mật khẩu</Button>
          <Button type="button" variant="ghost" className="w-full" onClick={() => setStep(1)}>Gửi lại mã / đổi email</Button>
        </form>
      )}
      <p className="mt-6 text-center text-sm text-muted-foreground"><Link to="/login" className="font-semibold text-primary hover:underline">Quay lại đăng nhập</Link></p>
    </AuthLayout>
  );
}
