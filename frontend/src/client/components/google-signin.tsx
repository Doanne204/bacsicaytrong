import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, send } from "@/shared/lib/api";
import { cn } from "@/shared/lib/utils";

/* eslint-disable @typescript-eslint/no-explicit-any */
const GSI = "https://accounts.google.com/gsi/client";
let gsiLoading: Promise<void> | null = null;
function loadGsi() {
  if ((window as any).google?.accounts?.id) return Promise.resolve();
  gsiLoading ||= new Promise((resolve, reject) => {
    const s = Object.assign(document.createElement("script"), { src: GSI, async: true, defer: true });
    s.onload = () => resolve(); s.onerror = () => { gsiLoading = null; reject(new Error("Không tải được nút Google (cần Internet)")); };
    document.head.appendChild(s);
  });
  return gsiLoading;
}

/** Nút "Đăng ký / Đăng nhập với Google" (Google Identity Services). Chỉ hiện khi máy chủ đã cấu hình GOOGLE_CLIENT_ID.
 *  Google trả về ID token, máy chủ kiểm tra rồi tạo tài khoản mới hoặc đăng nhập vào tài khoản cùng email.
 *  below: đặt dưới biểu mẫu (đường kẻ "hoặc" nằm trên nút); mặc định đặt trên biểu mẫu (đường kẻ nằm dưới nút). */
export function GoogleSignIn({ mode, next = "/home", below = false }: { mode: "signup" | "signin"; next?: string; below?: boolean }) {
  const cfg = useQuery({ queryKey: ["auth-config"], queryFn: () => api<{ google_client_id: string | null }>("/api/auth/config"), staleTime: Infinity });
  const box = useRef<HTMLDivElement>(null), nav = useNavigate(), qc = useQueryClient();
  const [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const cid = cfg.data?.google_client_id;
  useEffect(() => {
    if (!cid) return;
    let dead = false;
    loadGsi().then(() => {
      if (dead || !box.current) return;
      const g = (window as any).google.accounts.id;
      g.initialize({
        client_id: cid, ux_mode: "popup", cancel_on_tap_outside: true,
        callback: async ({ credential }: { credential: string }) => {
          setBusy(true); setErr("");
          try {
            const r = await send<{ username: string; created: boolean; need_phone: boolean }>("/api/auth/google", { credential });
            await qc.invalidateQueries({ queryKey: ["me"] });
            toast.success(r.created ? `Đã tạo tài khoản ${r.username}` : `Chào ${r.username}`);
            nav(r.created && r.need_phone ? "/profile" : next, { replace: true });
            if (r.created && r.need_phone) toast("Hãy bổ sung số điện thoại trong hồ sơ để bà con liên hệ được khi cần");
          } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
        },
      });
      box.current.innerHTML = "";
      g.renderButton(box.current, { type: "standard", theme: "outline", size: "large", shape: "pill", logo_alignment: "center",
        text: mode === "signup" ? "signup_with" : "signin_with", locale: "vi", width: Math.min(400, box.current.clientWidth || 320) });
    }).catch((e) => setErr(e.message));
    return () => { dead = true; };
  }, [cid, mode, next, nav, qc]);
  if (!cid) return null;
  const divider = (
    <div className={cn("flex items-center gap-3 text-xs text-muted-foreground", below ? "mb-5" : "mt-5")} aria-hidden>
      <span className="h-px flex-1 bg-border" />{below ? "hoặc" : mode === "signup" ? "hoặc tạo tài khoản bằng email" : "hoặc đăng nhập bằng tài khoản"}<span className="h-px flex-1 bg-border" />
    </div>
  );
  return (
    <div className={below ? "mt-5" : "mb-5"}>
      {below && divider}
      <div ref={box} className="flex min-h-[44px] w-full justify-center" aria-busy={busy} />
      {busy && <p className="mt-2 text-center text-sm text-muted-foreground">Đang đăng nhập bằng Google…</p>}
      {err && <p role="alert" className="mt-2 rounded-xl bg-destructive/10 px-4 py-2 text-center text-sm font-semibold text-destructive">{err}</p>}
      {!below && divider}
    </div>
  );
}
