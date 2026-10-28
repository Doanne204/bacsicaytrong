import { Bell, Clock, CloudSun, Home, MessageCircle, NotebookPen, PanelLeftClose, PanelLeftOpen, PenSquare, ScanLine, Shield, Star, User } from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useMe } from "@/shared/hooks/use-me";
import { useSidebar } from "@/shared/hooks/use-sidebar";
import { Brand, Logo } from "@/shared/components/brand";
import { ThemeToggle } from "@/shared/components/common";
import { Avatar } from "@/shared/ui/misc";
import { Button } from "@/shared/ui/button";
import { cn } from "@/shared/lib/utils";

const TABS = [
  { to: "/home", label: "Trang chủ", icon: Home, match: ["/home", "/post", "/p/", "/kq/"] },
  { to: "/history", label: "Lịch sử", icon: Clock, match: ["/history"] },
  { to: "/scan", label: "Quét lá", icon: ScanLine, match: ["/scan", "/diagnosis"], primary: true },
  { to: "/journal", label: "Nhật ký", icon: NotebookPen, match: ["/journal"] },
  { to: "/profile", label: "Hồ sơ", icon: User, match: ["/profile", "/notifications", "/ratings"] },
];
const EXTRA = [
  { to: "/weather", label: "Cảnh báo thời tiết", icon: CloudSun, match: ["/weather"] },
  { to: "/chat", label: "Hỏi trợ lý AI", icon: MessageCircle, match: ["/chat"] },
  { to: "/post", label: "Đăng bài", icon: PenSquare, match: ["/post"] },
  { to: "/ratings", label: "Đánh giá", icon: Star, match: ["/ratings"] },
];

/** Khung ứng dụng: thanh trên + thanh tab dưới (điện thoại); thanh bên trái thu gọn được (máy tính ≥ lg). */
export function Shell() {
  const { me } = useMe();
  const { collapsed, toggle } = useSidebar();
  const loc = useLocation();
  const active = (m: string[]) => m.some((p) => loc.pathname === p || loc.pathname.startsWith(p.endsWith("/") ? p : p + "/"));
  const chat = loc.pathname.startsWith("/chat"), post = /^\/p\//.test(loc.pathname);
  const hideTabbar = chat || post;
  const item = (t: { to: string; label: string; icon: React.ComponentType<{ className?: string }>; match: string[] }) => (
    <NavLink key={t.to} to={t.to} title={collapsed ? t.label : undefined}
      className={cn("relative flex h-11 items-center gap-3 rounded-lg px-3 text-sm font-semibold text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground", active(t.match) && "bg-secondary text-secondary-foreground", collapsed && "justify-center px-0")}>
      <t.icon className="h-5 w-5 shrink-0" /><span className={cn("truncate", collapsed && "lg:hidden")}>{t.label}</span>
      {t.to === "/journal" && !!me?.due && <span className={cn("ml-auto min-w-[20px] rounded-full bg-destructive px-1.5 text-center text-[11px] font-bold leading-5 text-white", collapsed && "lg:absolute lg:right-3 lg:top-1.5 lg:ml-0 lg:h-2.5 lg:min-w-0 lg:w-2.5 lg:p-0 lg:text-[0]")}>{me.due}</span>}
    </NavLink>
  );
  return (
    <div className={cn("min-h-dvh transition-[padding] duration-300", collapsed ? "lg:pl-[72px]" : "lg:pl-64")}>
      <aside className={cn("fixed inset-y-0 left-0 z-30 hidden flex-col border-r bg-card transition-[width] duration-300 lg:flex", collapsed ? "w-[72px]" : "w-64")}>
        <div className={cn("flex h-16 items-center border-b px-3", collapsed ? "justify-center" : "justify-between pl-4")}>
          <NavLink to="/home" aria-label="Trang chủ">{collapsed ? <Logo size={36} /> : <Brand />}</NavLink>
          {!collapsed && <Button variant="ghost" size="icon-sm" onClick={toggle} aria-label="Thu gọn thanh bên"><PanelLeftClose className="h-5 w-5" /></Button>}
        </div>
        {collapsed && <Button variant="ghost" size="icon-sm" onClick={toggle} aria-label="Mở rộng thanh bên" className="mx-auto mt-2"><PanelLeftOpen className="h-5 w-5" /></Button>}
        <nav className="flex-1 space-y-1 px-3 py-3" aria-label="Điều hướng chính">
          <NavLink to="/scan" title={collapsed ? "Quét lá, sâu hại" : undefined} className={cn("mb-3 flex h-11 items-center gap-3 rounded-lg bg-primary px-3 text-sm font-bold text-primary-foreground shadow-soft transition hover:bg-primary/90", active(["/scan", "/diagnosis"]) && "ring-2 ring-paddy", collapsed && "justify-center px-0")}>
            <ScanLine className="h-5 w-5 shrink-0" /><span className={cn(collapsed && "lg:hidden")}>Quét lá, sâu hại</span>
          </NavLink>
          {[...TABS.filter((t) => !t.primary), ...EXTRA].map(item)}
          {me?.role === "admin" && (
            <a href="/admin" title={collapsed ? "Trang quản trị" : undefined} className={cn("flex h-11 items-center gap-3 rounded-lg px-3 text-sm font-semibold text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground", collapsed && "justify-center px-0")}>
              <Shield className="h-5 w-5 shrink-0" /><span className={cn(collapsed && "lg:hidden")}>Trang quản trị</span>
            </a>
          )}
        </nav>
        <div className="border-t p-3">
          <div className={cn("flex items-center gap-3", collapsed && "flex-col")}>
            <NavLink to="/profile" aria-label="Hồ sơ" className={cn("flex min-w-0 flex-1 items-center gap-3 rounded-lg px-1 py-1 hover:bg-accent", collapsed && "flex-none px-0")}>
              <Avatar name={me?.username} size="sm" />
              <span className={cn("min-w-0 flex-1 leading-tight", collapsed && "lg:hidden")}><b className="block truncate text-sm">{me?.username}</b><small className="text-muted-foreground">{me?.role === "admin" ? "Quản trị viên" : "Thành viên"}</small></span>
            </NavLink>
            <ThemeToggle />
          </div>
        </div>
      </aside>

      <header className="sticky top-0 z-30 flex h-14 items-center gap-1 border-b bg-background/85 px-3 backdrop-blur lg:hidden">
        <NavLink to="/home" className="mr-auto"><Brand /></NavLink>
        <Button asChild variant="ghost" size="icon" aria-label={`Thông báo${me?.unread ? `, ${me.unread} chưa đọc` : ""}`}>
          <NavLink to="/notifications" className="relative">
            <Bell className="h-5 w-5" />
            {!!me?.unread && <span className="absolute right-1.5 top-1.5 min-w-[18px] rounded-full bg-destructive px-1 text-center text-[11px] font-bold leading-[18px] text-white">{me.unread > 9 ? "9+" : me.unread}</span>}
          </NavLink>
        </Button>
        <NavLink to="/profile" aria-label="Hồ sơ"><Avatar name={me?.username} size="sm" /></NavLink>
      </header>

      <main className={cn("mx-auto w-full", chat ? "max-w-none" : "max-w-[1480px] px-4 py-5 md:px-8 md:py-8 xl:px-10", !hideTabbar && "pb-[calc(5.5rem+var(--safe-b))] lg:pb-10")}>
        <Outlet />
      </main>

      {!hideTabbar && (
        <nav className="fixed inset-x-0 bottom-0 z-30 grid h-[calc(4.25rem+var(--safe-b))] grid-cols-5 border-t bg-card pb-[var(--safe-b)] lg:hidden" aria-label="Điều hướng chính">
          {TABS.map((t) =>
            t.primary ? (
              <NavLink key={t.to} to={t.to} className="flex flex-col items-center justify-end gap-1 pb-2 text-[11px] font-semibold text-muted-foreground" aria-current={active(t.match) ? "page" : undefined}>
                <span className={cn("-mt-7 grid h-14 w-14 place-items-center rounded-2xl border-4 border-background bg-primary text-primary-foreground shadow-lift transition", active(t.match) && "bg-paddy text-paddy-foreground")}><t.icon className="h-6 w-6" /></span>{t.label}
              </NavLink>
            ) : (
              <NavLink key={t.to} to={t.to} className={cn("relative flex flex-col items-center justify-center gap-1 text-[11px] font-semibold text-muted-foreground transition", active(t.match) && "text-primary")} aria-current={active(t.match) ? "page" : undefined}>
                <t.icon className={cn("h-5 w-5", active(t.match) && "fill-primary/15")} />{t.label}
                {t.to === "/journal" && !!me?.due && <span className="absolute right-[calc(50%-18px)] top-2 h-2.5 w-2.5 rounded-full bg-destructive ring-2 ring-card" aria-label={`${me.due} việc đến hạn`} />}
              </NavLink>
            ),
          )}
        </nav>
      )}
    </div>
  );
}
