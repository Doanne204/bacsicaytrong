import { useEffect } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlarmClock, AlertTriangle, Bell, CloudSun } from "lucide-react";
import { api, send, type Notification } from "@/shared/lib/api";
import { ago, cn } from "@/shared/lib/utils";
import { EmptyState, Skeleton } from "@/shared/ui/misc";
import { PageHeader } from "@/shared/components/common";

const toPath = (link: string | null) => (link || "/home").replace(/^#/, "");

export default function Notifications() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["notifications"], queryFn: () => api<Notification[]>("/api/notifications") });
  useEffect(() => {
    if (q.data?.some((n) => !n.read)) send("/api/notifications/read", {}).then(() => qc.invalidateQueries({ queryKey: ["me"] }));
  }, [q.data, qc]);
  return (
    <div className="mx-auto max-w-2xl animate-fade-up">
      <PageHeader title="Thông báo" />
      {q.isLoading ? <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-16" />)}</div>
        : !q.data?.length ? <EmptyState icon={Bell} title="Chưa có thông báo nào" />
        : <div className="space-y-1">{q.data.map((n) => {
          const warn = n.content.includes("không được") || n.content.includes("từ chối");
          const path = toPath(n.link);
          const Icon = warn ? AlertTriangle : path.startsWith("/journal") ? AlarmClock : path === "/weather" ? CloudSun : Bell;
          const inner = <><Icon className={cn("mt-0.5 h-5 w-5 shrink-0", warn ? "text-destructive" : path.startsWith("/journal") || path === "/weather" ? "text-warning" : "text-primary")} /><span className="min-w-0 flex-1"><span className="block">{n.content}</span><small className="text-muted-foreground">{ago(n.created)}</small></span></>;
          const cls = cn("flex gap-3 rounded-2xl px-4 py-3.5 text-sm transition hover:bg-accent", !n.read && "bg-secondary");
          return path.startsWith("/admin") ? <a key={n.id} href={path} className={cls}>{inner}</a> : <Link key={n.id} to={path} className={cls}>{inner}</Link>;
        })}</div>}
    </div>
  );
}
