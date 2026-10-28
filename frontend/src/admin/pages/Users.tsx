import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Copy, KeyRound, Lock, MoreHorizontal, Shield, ShieldOff, Trash2, Unlock, Users as UsersIcon } from "lucide-react";
import { api, del, send } from "@/shared/lib/api";
import { copyText, fmtDate, toDate } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { Badge } from "@/shared/ui/badge";
import { Input } from "@/shared/ui/input";
import { Avatar, EmptyState } from "@/shared/ui/misc";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/shared/ui/dropdown-menu";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/shared/ui/dialog";
import { ConfirmDialog } from "@/shared/components/common";
import { DataTable } from "../components/table";
import type { AdminUser } from "../lib/types";

type Act = "lock" | "unlock" | "make_admin" | "make_user" | "reset_password" | "delete";
const MSG: Record<string, string> = { lock: "Đã khóa tài khoản", unlock: "Đã mở khóa tài khoản", make_admin: "Đã cấp quyền quản trị", make_user: "Đã bỏ quyền quản trị" };

export default function Users() {
  const [q, setQ] = useState(""), [pending, setPending] = useState<{ u: AdminUser; a: Act } | null>(null), [pw, setPw] = useState<{ u: AdminUser; password: string } | null>(null), [typed, setTyped] = useState("");
  const list = useQuery({ queryKey: ["admin", "users", q], queryFn: () => api<AdminUser[]>(`/api/admin/users?q=${encodeURIComponent(q)}`) });
  const run = async (u: AdminUser, a: Act) => {
    if (a === "delete") { await del(`/api/admin/users/${u.id}`); toast.success(`Đã xóa tài khoản ${u.username}`); }
    else {
      const r = await send<{ password?: string }>(`/api/admin/users/${u.id}`, { action: a });
      if (a === "reset_password" && r.password) setPw({ u, password: r.password }); else toast.success(MSG[a]);
    }
    list.refetch();
  };
  const menu = (u: AdminUser) => (
    <DropdownMenu>
      <DropdownMenuTrigger asChild><Button variant="ghost" size="icon-sm" aria-label="Thao tác"><MoreHorizontal className="h-4 w-4" /></Button></DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {!u.is_me && <DropdownMenuItem onClick={() => (u.locked ? run(u, "unlock").catch((e) => toast.error(e.message)) : setPending({ u, a: "lock" }))}>{u.locked ? <Unlock /> : <Lock />}{u.locked ? "Mở khóa" : "Khóa tài khoản"}</DropdownMenuItem>}
        {!u.is_me && <DropdownMenuItem onClick={() => setPending({ u, a: u.role === "admin" ? "make_user" : "make_admin" })}>{u.role === "admin" ? <ShieldOff /> : <Shield />}{u.role === "admin" ? "Bỏ quyền quản trị" : "Cấp quyền quản trị"}</DropdownMenuItem>}
        <DropdownMenuItem onClick={() => setPending({ u, a: "reset_password" })}><KeyRound />Đặt lại mật khẩu</DropdownMenuItem>
        {!u.is_me && <><DropdownMenuSeparator /><DropdownMenuItem danger onClick={() => { setTyped(""); setPending({ u, a: "delete" }); }}><Trash2 />Xóa tài khoản</DropdownMenuItem></>}
      </DropdownMenuContent>
    </DropdownMenu>
  );
  const badges = (u: AdminUser) => <>{u.role === "admin" && <Badge variant="success">Quản trị viên</Badge>}{!!u.locked && <Badge variant="destructive">Đã khóa</Badge>}{u.is_me && <Badge variant="muted">bạn</Badge>}</>;
  const titles: Record<Act, [string, string]> = {
    lock: [`Khóa tài khoản ${pending?.u.username}?`, "Người này sẽ bị đăng xuất và không đăng nhập được cho đến khi mở khóa."],
    unlock: ["Mở khóa?", ""], make_admin: [`Cấp quyền quản trị cho ${pending?.u.username}?`, "Người này sẽ vào được trang quản trị và mọi dữ liệu."],
    make_user: [`Bỏ quyền quản trị của ${pending?.u.username}?`, ""], reset_password: [`Đặt mật khẩu mới cho ${pending?.u.username}?`, "Mật khẩu cũ sẽ không dùng được nữa. Mật khẩu tạm chỉ hiện một lần."],
    delete: [`Xóa tài khoản ${pending?.u.username}?`, `Sẽ xóa vĩnh viễn ${pending?.u.posts} bài viết, ${pending?.u.comments} bình luận, ${pending?.u.scans} lần tra cứu và ${pending?.u.ratings} đánh giá. Không thể hoàn tác. Nếu chỉ muốn chặn, hãy dùng Khóa.`],
  };
  return (
    <div className="animate-fade-up">
      <DataTable rows={list.data || []} loading={list.isLoading} keyOf={(u) => u.id} search={q} onSearch={setQ} searchPlaceholder="Tìm tên, email hoặc số điện thoại…"
        empty={<EmptyState icon={UsersIcon} title="Không có người dùng khớp từ khóa" />}
        renderCard={(u) => (
          <div className="flex gap-3 rounded-2xl border bg-card p-3">
            <Avatar name={u.username} />
            <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-1.5"><b>{u.username}</b>{badges(u)}</div><p className="truncate text-sm text-muted-foreground">{u.email}{u.phone ? ` · ${u.phone}` : ""}</p><p className="mt-1 text-xs text-muted-foreground">{u.scans} tra cứu · {u.posts} bài · {u.comments} bình luận · {u.ratings} đánh giá · {fmtDate(toDate(u.created))}</p></div>
            {menu(u)}
          </div>
        )}
        columns={[
          { key: "user", header: "Tài khoản", cell: (u) => <span className="flex items-center gap-3"><Avatar name={u.username} size="sm" /><span className="min-w-0"><span className="flex flex-wrap items-center gap-1.5"><b>{u.username}</b>{badges(u)}</span><span className="block truncate text-xs text-muted-foreground">{u.email}{u.phone ? ` · ${u.phone}` : ""}</span></span></span>, sort: (u) => u.username },
          { key: "scans", header: "Tra cứu", cell: (u) => u.scans, sort: (u) => u.scans, className: "tabular-nums", hide: "sm" },
          { key: "posts", header: "Bài viết", cell: (u) => u.posts, sort: (u) => u.posts, className: "tabular-nums", hide: "sm" },
          { key: "comments", header: "Bình luận", cell: (u) => u.comments, sort: (u) => u.comments, className: "tabular-nums", hide: "md" },
          { key: "created", header: "Tham gia", cell: (u) => fmtDate(toDate(u.created)), sort: (u) => u.created, hide: "md" },
          { key: "act", header: "", cell: menu, className: "text-right" },
        ]} />
      <ConfirmDialog open={!!pending} onOpenChange={(o) => !o && setPending(null)} title={pending ? titles[pending.a][0] : ""} description={pending ? titles[pending.a][1] : ""} confirmText={pending?.a === "delete" ? "Xóa vĩnh viễn" : "Xác nhận"} danger={pending?.a === "delete" || pending?.a === "lock"}
        onConfirm={async () => { if (!pending) return; if (pending.a === "delete" && typed.trim() !== pending.u.username) { toast.error("Hãy gõ đúng tên đăng nhập để xác nhận"); throw new Error(); } try { await run(pending.u, pending.a); } catch (e) { if ((e as Error).message) toast.error((e as Error).message); throw e; } }}>
        {pending?.a === "delete" && <div className="space-y-1.5"><label htmlFor="cfu" className="text-sm font-semibold">Gõ <b>{pending.u.username}</b> để xác nhận</label><Input id="cfu" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" /></div>}
      </ConfirmDialog>
      <Dialog open={!!pw} onOpenChange={(o) => !o && setPw(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Mật khẩu mới của {pw?.u.username}</DialogTitle><DialogDescription>Mật khẩu chỉ hiện một lần. Hãy gửi cho người dùng và nhắc họ đổi lại trong Hồ sơ.</DialogDescription></DialogHeader>
          <p className="select-all rounded-xl border-2 border-dashed border-primary bg-card p-4 text-center text-2xl font-bold tracking-[.1em] tabular-nums">{pw?.password}</p>
          <Button onClick={async () => { await copyText(pw!.password); toast.success("Đã sao chép"); }}><Copy />Sao chép mật khẩu</Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
