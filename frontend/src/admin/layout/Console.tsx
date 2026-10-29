import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { BarChart3, Cpu, Database, ExternalLink, KeyRound, LayoutGrid, LogOut, Menu, MessageSquare, PanelLeftClose, PanelLeftOpen, PenSquare, Star, Users, X } from "lucide-react";
import { useLogout, useMe } from "@/shared/hooks/use-me";
import { useSidebar } from "@/shared/hooks/use-sidebar";
import { Brand, Logo } from "@/shared/components/brand";
import { ThemeToggle } from "@/shared/components/common";
import { Avatar } from "@/shared/ui/misc";
import { Button } from "@/shared/ui/button";
import { cn } from "@/shared/lib/utils";
import type { Stats } from "../lib/types";

export const NAV = [
  { to: "/overview", label: "Tổng quan", icon: LayoutGrid, desc: "Số liệu hoạt động và gửi thông báo cho mọi người." },
  { to: "/posts", label: "Bài viết", icon: PenSquare, desc: "Duyệt các bài AI chưa chắc chắn, gỡ bài đã đăng khi cần.", count: (s: Stats) => s.pending },
  { to: "/comments", label: "Bình luận", icon: MessageSquare, desc: "Xem lại bình luận AI chưa duyệt, xóa bình luận vi phạm.", count: (s: Stats) => s.flagged },
  { to: "/users", label: "Người dùng", icon: Users, desc: "Khóa tài khoản, cấp quyền quản trị, đặt lại mật khẩu." },
  { to: "/ratings", label: "Đánh giá", icon: Star, desc: "Đánh giá của người dùng về kết quả tra cứu." },
  { to: "/stats", label: "Thống kê", icon: BarChart3, desc: "Tra cứu theo tháng, bệnh theo mùa, độ chính xác suy từ đánh giá, lượt AI." },
  { to: "/models", label: "Đánh giá mô hình", icon: Cpu, desc: "Ma trận nhầm lẫn, precision/recall/F1 từng lớp của hai mô hình." },
  { to: "/data", label: "Dữ liệu AI", icon: Database, desc: "Duyệt nhãn ảnh AI và báo kết quả sai trước khi huấn luyện lại mô hình.", count: (s: Stats) => s.samples_pending + s.reports_open },
  { to: "/keys", label: "Khóa Gemini", icon: KeyRound, desc: "Thêm nhiều khóa API, xoay vòng khi một khóa hết lượt." },
];

/** Khung trang quản trị: thanh bên xanh đậm (máy tính), thanh trên + menu trượt (điện thoại). */
export function Console({ stats, children }: { stats?: Stats; children: React.ReactNode }) {
  const { me } = useMe();
  const logout = useLogout();
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const { collapsed, toggle } = useSidebar();
  const cur = NAV.find((n) => loc.pathname.startsWith(n.to)) || NAV[0];
  // mini: thanh bên máy tính đang thu gọn (chỉ biểu tượng); menu trượt trên điện thoại luôn đầy đủ
  const nav = (mini: boolean) => (
    <nav className="space-y-1" aria-label="Mục quản trị">
      {NAV.map((n) => {
        const c = stats && n.count ? n.count(stats) : 0;
        return (
          <NavLink key={n.to} to={n.to} onClick={() => setOpen(false)} title={mini ? n.label : undefined} className={({ isActive }) => cn("relative flex h-11 items-center gap-3 rounded-lg px-3 text-sm font-semibold text-[#CFE3C9] transition hover:bg-white/10 hover:text-white", isActive && "bg-white/15 text-white shadow-[inset_3px_0_0_hsl(var(--paddy))]", mini && "justify-center px-0")}>
            <n.icon className="h-5 w-5 shrink-0" />{!mini && <span className="flex-1 truncate">{n.label}</span>}
            {c > 0 && <span className={cn("min-w-[20px] rounded-full bg-paddy px-1.5 text-center text-xs font-bold leading-5 text-[#33291F]", mini && "absolute -right-1 -top-1 min-w-[18px] leading-[18px]")}>{c > 99 ? "99+" : c}</span>}
          </NavLink>
        );
      })}
    </nav>
  );
  const foot = (mini: boolean) => (
    <div className={cn("mt-auto space-y-2 border-t border-white/10 pt-3", mini && "flex flex-col items-center")}>
      <a href="/" target="_blank" rel="noopener" title="Mở ứng dụng người dùng" className={cn("flex h-11 items-center gap-3 rounded-lg px-3 text-sm font-semibold text-[#CFE3C9] hover:bg-white/10 hover:text-white", mini && "w-11 justify-center px-0")}><ExternalLink className="h-5 w-5 shrink-0" />{!mini && "Mở ứng dụng người dùng"}</a>
      <div className={cn("flex items-center gap-2 px-1", mini && "flex-col")}>
        <Avatar name={me?.username} size="sm" className="bg-white/15 text-white" />
        {!mini && <span className="min-w-0 flex-1 leading-tight"><b className="block truncate text-sm text-white">{me?.username}</b><small className="block whitespace-nowrap text-xs text-[#CFE3C9]">Quản trị viên</small></span>}
        <ThemeToggle className="text-[#CFE3C9] hover:bg-white/10 hover:text-white" />
        <Button variant="ghost" size="icon-sm" className="text-[#CFE3C9] hover:bg-white/10 hover:text-white" aria-label="Đăng xuất" onClick={() => logout().then(() => location.reload())}><LogOut className="h-5 w-5" /></Button>
      </div>
    </div>
  );
  return (
    <div className={cn("min-h-dvh transition-[grid-template-columns] duration-300 lg:grid", collapsed ? "lg:grid-cols-[72px_minmax(0,1fr)]" : "lg:grid-cols-[264px_minmax(0,1fr)]")}>
      <aside className={cn("sticky top-0 hidden h-dvh flex-col bg-[#1F4A28] dark:bg-[#0E2416] lg:flex", collapsed ? "p-3" : "p-4")}>
        <div className={cn("mb-4 flex items-center", collapsed ? "flex-col gap-2" : "justify-between px-1")}>
          <NavLink to="/overview" aria-label="Tổng quan">{collapsed ? <Logo size={36} className="rounded-full bg-white p-0.5" /> : <Brand light sub="Trang quản trị" />}</NavLink>
          <Button variant="ghost" size="icon-sm" onClick={toggle} className="text-[#CFE3C9] hover:bg-white/10 hover:text-white" aria-label={collapsed ? "Mở rộng thanh bên" : "Thu gọn thanh bên"}>{collapsed ? <PanelLeftOpen className="h-5 w-5" /> : <PanelLeftClose className="h-5 w-5" />}</Button>
        </div>
        {nav(collapsed)}{foot(collapsed)}
      </aside>
      <header className="sticky top-0 z-30 flex h-14 items-center gap-2 bg-[#1F4A28] px-3 text-white lg:hidden">
        <Button variant="ghost" size="icon-sm" className="text-white hover:bg-white/10 hover:text-white" aria-label="Mở menu" onClick={() => setOpen(true)}><Menu className="h-5 w-5" /></Button>
        <Brand light sub="Quản trị" className="mr-auto" />
        <a href="/" target="_blank" rel="noopener" className="rounded-lg p-2 hover:bg-white/10" aria-label="Mở ứng dụng người dùng"><ExternalLink className="h-5 w-5" /></a>
      </header>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-72 flex-col bg-[#1F4A28] p-4 animate-in slide-in-from-left">
            <div className="mb-4 flex items-center justify-between"><Brand light sub="Trang quản trị" /><Button variant="ghost" size="icon-sm" className="text-white hover:bg-white/10" aria-label="Đóng" onClick={() => setOpen(false)}><X className="h-5 w-5" /></Button></div>
            {nav(false)}{foot(false)}
          </aside>
        </div>
      )}
      <main className="mx-auto w-full max-w-[1560px] px-4 py-5 md:px-8 md:py-8 xl:px-10">
        <header className="mb-6"><h1 className="text-2xl font-extrabold md:text-3xl">{cur.label}</h1><p className="text-muted-foreground">{cur.desc}</p></header>
        {children}
      </main>
    </div>
  );
}
