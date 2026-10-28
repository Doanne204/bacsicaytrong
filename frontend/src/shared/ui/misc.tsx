import * as React from "react";
import * as AvatarPrimitive from "@radix-ui/react-avatar";
import * as ProgressPrimitive from "@radix-ui/react-progress";
import * as SeparatorPrimitive from "@radix-ui/react-separator";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cn, initial } from "@/shared/lib/utils";

// ---------- Avatar chữ cái đầu ----------
export function Avatar({ name, className, size = "md" }: { name?: string; className?: string; size?: "sm" | "md" | "lg" }) {
  const s = { sm: "h-8 w-8 text-sm", md: "h-10 w-10", lg: "h-16 w-16 text-2xl" }[size];
  return (
    <AvatarPrimitive.Root className={cn("flex shrink-0 select-none items-center justify-center rounded-full bg-secondary font-bold text-secondary-foreground", s, className)}>
      <AvatarPrimitive.Fallback>{initial(name)}</AvatarPrimitive.Fallback>
    </AvatarPrimitive.Root>
  );
}

// ---------- Thanh tiến trình ----------
export const Progress = React.forwardRef<React.ElementRef<typeof ProgressPrimitive.Root>, React.ComponentPropsWithoutRef<typeof ProgressPrimitive.Root> & { tone?: "primary" | "paddy" | "destructive" }>(
  ({ className, value, tone = "primary", ...props }, ref) => (
    <ProgressPrimitive.Root ref={ref} className={cn("relative h-2.5 w-full overflow-hidden rounded-full bg-muted", className)} {...props}>
      <ProgressPrimitive.Indicator className={cn("h-full rounded-full transition-all duration-700", { primary: "bg-primary", paddy: "bg-paddy", destructive: "bg-destructive" }[tone])} style={{ width: `${value || 0}%` }} />
    </ProgressPrimitive.Root>
  ),
);
Progress.displayName = "Progress";

export const Separator = React.forwardRef<React.ElementRef<typeof SeparatorPrimitive.Root>, React.ComponentPropsWithoutRef<typeof SeparatorPrimitive.Root>>(
  ({ className, orientation = "horizontal", decorative = true, ...props }, ref) => (
    <SeparatorPrimitive.Root ref={ref} decorative={decorative} orientation={orientation} className={cn("shrink-0 bg-border", orientation === "horizontal" ? "h-px w-full" : "h-full w-px", className)} {...props} />
  ),
);
Separator.displayName = "Separator";

export const Switch = React.forwardRef<React.ElementRef<typeof SwitchPrimitive.Root>, React.ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>>(({ className, ...props }, ref) => (
  <SwitchPrimitive.Root
    className={cn("peer inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary data-[state=unchecked]:bg-input", className)}
    {...props}
    ref={ref}
  >
    <SwitchPrimitive.Thumb className="pointer-events-none block h-5 w-5 rounded-full bg-white shadow-lg ring-0 transition-transform data-[state=checked]:translate-x-5 data-[state=unchecked]:translate-x-0" />
  </SwitchPrimitive.Root>
));
Switch.displayName = "Switch";

export const TooltipProvider = TooltipPrimitive.Provider;
export const Tooltip = TooltipPrimitive.Root;
export const TooltipTrigger = TooltipPrimitive.Trigger;
export const TooltipContent = React.forwardRef<React.ElementRef<typeof TooltipPrimitive.Content>, React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>>(({ className, sideOffset = 4, ...props }, ref) => (
  <TooltipPrimitive.Content ref={ref} sideOffset={sideOffset} className={cn("z-50 overflow-hidden rounded-lg bg-foreground px-3 py-1.5 text-xs text-background animate-in fade-in-0 zoom-in-95", className)} {...props} />
));
TooltipContent.displayName = "TooltipContent";

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-xl bg-muted", className)} {...props} />;
}

/** Trạng thái trống / lỗi thống nhất cho mọi danh sách. */
export function EmptyState({ icon: Icon, title, text, action, className }: { icon: React.ComponentType<{ className?: string }>; title: string; text?: string; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center px-4 py-12 text-center", className)}>
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-secondary text-primary"><Icon className="h-8 w-8" /></div>
      <h3 className="text-base font-bold">{title}</h3>
      {text && <p className="mt-1 max-w-sm text-sm text-muted-foreground">{text}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/** Hộp thông báo trong trang (ghi chú, cảnh báo, lỗi). */
export function Notice({ tone = "info", icon: Icon, children, className }: { tone?: "info" | "warn" | "danger" | "ok"; icon?: React.ComponentType<{ className?: string }>; children: React.ReactNode; className?: string }) {
  const tones = { info: "bg-secondary/60 text-foreground [&>svg]:text-primary", warn: "bg-warning/10 [&>svg]:text-warning", danger: "bg-destructive/10 [&>svg]:text-destructive", ok: "bg-secondary [&>svg]:text-primary" };
  return (
    <div className={cn("flex gap-3 rounded-2xl p-4 text-sm leading-relaxed", tones[tone], className)}>
      {Icon && <Icon className="mt-0.5 h-5 w-5 shrink-0" />}
      <div className="min-w-0 flex-1 [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-4">{children}</div>
    </div>
  );
}

/** Trường nhập có nhãn và lỗi inline. */
export function Field({ label, htmlFor, error, hint, children, className }: { label: React.ReactNode; htmlFor?: string; error?: string; hint?: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <label htmlFor={htmlFor} className="block text-sm font-semibold">{label}</label>
      {children}
      {error ? <p className="text-xs font-medium text-destructive" role="alert">{error}</p> : hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
