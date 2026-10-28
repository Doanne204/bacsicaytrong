import { cn } from "@/shared/lib/utils";

/** Logo vòng lá + tên ứng dụng; phần ảnh do Flask phục vụ ở /static/img. */
export function Logo({ size = 40, className }: { size?: number; className?: string }) {
  return <img src="/static/img/logo-96.png" srcSet="/static/img/logo-96.png 1x, /static/img/logo.png 3x" alt="" width={size} height={size} className={cn("shrink-0 object-contain", className)} />;
}

export function Brand({ sub, className, light }: { sub?: string; className?: string; light?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <Logo className={cn("rounded-full", light && "bg-white p-0.5")} />
      <span className="leading-tight">
        <b className={cn("block whitespace-nowrap text-base font-extrabold", light ? "text-white" : "text-primary")}>Bác sĩ cây trồng</b>
        {sub && <small className={cn("block text-[11px] font-bold uppercase tracking-wider", light ? "text-paddy" : "text-muted-foreground")}>{sub}</small>}
      </span>
    </span>
  );
}
