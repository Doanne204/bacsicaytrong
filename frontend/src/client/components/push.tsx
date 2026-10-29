import { useEffect, useState } from "react";
import { toast } from "sonner";
import { BellRing, Download, Send, Smartphone } from "lucide-react";
import { send } from "@/shared/lib/api";
import { canInstall, currentSub, disablePush, enablePush, install, isStandalone, onInstallChange, pushSupported } from "@/shared/lib/pwa";
import { Button } from "@/shared/ui/button";
import { Switch } from "@/shared/ui/misc";

/** Thẻ "Ứng dụng trên điện thoại": cài lên màn hình chính và bật thông báo đẩy (nhắc việc, cảnh báo thời tiết, kết quả duyệt...). */
export function AppCard() {
  const [on, setOn] = useState(false), [busy, setBusy] = useState(false), [installable, setInstallable] = useState(canInstall());
  const supported = pushSupported(), ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  useEffect(() => { currentSub().then((s) => setOn(!!s && Notification.permission === "granted")).catch(() => {}); }, []);
  useEffect(() => onInstallChange(() => setInstallable(canInstall())), []);
  const toggle = async (want: boolean) => {
    setBusy(true);
    try {
      if (want) { await enablePush(); toast.success("Đã bật thông báo trên thiết bị này"); } else { await disablePush(); toast.success("Đã tắt thông báo trên thiết bị này"); }
      setOn(want);
    } catch (e) { toast.error((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <section className="rounded-2xl border bg-card p-4">
      <h2 className="flex items-center gap-2 font-bold"><Smartphone className="h-5 w-5 text-primary" />Ứng dụng trên điện thoại</h2>
      {installable && !isStandalone() && (
        <div className="mt-3 flex items-center gap-3 rounded-xl bg-secondary/60 p-3 text-sm">
          <span className="flex-1">Cài lên màn hình chính để mở nhanh như ứng dụng, xem lại kết quả khi mất mạng.</span>
          <Button size="sm" onClick={() => install()}><Download />Cài đặt</Button>
        </div>
      )}
      <div className="mt-3 flex items-start gap-3">
        <BellRing className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
        <label htmlFor="push-on" className="min-w-0 flex-1 text-sm">
          <b className="block">Thông báo trên thiết bị này</b>
          <span className="text-muted-foreground">Nhắc việc đến hạn, cảnh báo sâu bệnh theo thời tiết, kết quả duyệt bài và báo cáo, kể cả khi không mở app.</span>
        </label>
        <Switch id="push-on" checked={on} disabled={!supported || busy} onCheckedChange={toggle} aria-label="Bật thông báo trên thiết bị này" />
      </div>
      {!supported && (
        <p className="mt-2 text-xs text-muted-foreground">
          {!window.isSecureContext ? "Cần mở app qua HTTPS (trên điện thoại: https://<địa chỉ máy chủ>:5443) mới bật được thông báo."
            : ios && !isStandalone() ? "Trên iPhone: bấm nút Chia sẻ, chọn \"Thêm vào MH chính\", rồi mở app từ màn hình chính để bật thông báo."
            : "Trình duyệt này chưa hỗ trợ thông báo đẩy."}
        </p>
      )}
      {on && <Button variant="ghost" size="sm" className="mt-2" onClick={() => send("/api/push/test", {}).then(() => toast.success("Đã gửi, thông báo sẽ hiện sau vài giây")).catch((e) => toast.error(e.message))}><Send />Gửi thông báo thử</Button>}
    </section>
  );
}
