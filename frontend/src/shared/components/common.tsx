import * as React from "react";
import { Moon, Sun, Monitor, Star } from "lucide-react";
import { useTheme, type Theme } from "@/shared/hooks/use-theme";
import { Button } from "@/shared/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/shared/ui/dropdown-menu";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/shared/ui/alert-dialog";
import { cn } from "@/shared/lib/utils";

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();
  const items: [Theme, string, React.ComponentType<{ className?: string }>][] = [["light", "Sáng", Sun], ["dark", "Tối", Moon], ["system", "Theo hệ thống", Monitor]];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className={className} aria-label="Giao diện sáng/tối">
          <Sun className="h-5 w-5 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {items.map(([t, label, Icon]) => (
          <DropdownMenuItem key={t} onClick={() => setTheme(t)} className={cn(theme === t && "bg-accent")}><Icon />{label}</DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Hộp thoại xác nhận dùng thay window.confirm. */
export function ConfirmDialog({ open, onOpenChange, title, description, confirmText = "Xác nhận", danger, onConfirm, children }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: string; description?: React.ReactNode; confirmText?: string; danger?: boolean; onConfirm: () => void | Promise<void>; children?: React.ReactNode;
}) {
  const [busy, setBusy] = React.useState(false);
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          {description && <AlertDialogDescription>{description}</AlertDialogDescription>}
        </AlertDialogHeader>
        {children}
        <AlertDialogFooter>
          <AlertDialogCancel>Hủy</AlertDialogCancel>
          <AlertDialogAction
            className={cn(danger && "bg-destructive text-destructive-foreground hover:bg-destructive/90")}
            disabled={busy}
            onClick={async (e) => { e.preventDefault(); setBusy(true); try { await onConfirm(); onOpenChange(false); } finally { setBusy(false); } }}
          >
            {confirmText}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

/** Dãy sao chỉ đọc hoặc chọn được. */
export function Stars({ value, onChange, size = "md", className }: { value: number; onChange?: (n: number) => void; size?: "sm" | "md" | "lg"; className?: string }) {
  const [hover, setHover] = React.useState(0);
  const s = { sm: "h-4 w-4", md: "h-6 w-6", lg: "h-9 w-9" }[size];
  const shown = hover || value;
  return (
    <span className={cn("inline-flex", onChange ? "gap-1" : "gap-0.5", className)} role={onChange ? "radiogroup" : undefined} aria-label={`${value} sao`}>
      {[1, 2, 3, 4, 5].map((i) => {
        const on = i <= shown;
        const star = <Star className={cn(s, "transition-colors", on ? "fill-paddy text-paddy" : "text-muted-foreground/40")} strokeWidth={1.5} />;
        return onChange ? (
          <button key={i} type="button" role="radio" aria-checked={i === value} aria-label={`${i} sao`} className="rounded-lg p-1 hover:bg-accent active:scale-95" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(0)} onClick={() => onChange(i)}>
            {star}
          </button>
        ) : <span key={i}>{star}</span>;
      })}
    </span>
  );
}

/** Vòng tròn độ tin cậy. */
export function ConfidenceRing({ value, size = 88, className }: { value: number; size?: number; className?: string }) {
  const r = (size - 10) / 2, c = 2 * Math.PI * r, v = Math.max(0, Math.min(1, value));
  const tone = v >= 0.8 ? "text-primary" : v >= 0.6 ? "text-paddy" : "text-destructive";
  return (
    <div className={cn("relative grid place-items-center", className)} style={{ width: size, height: size }} role="img" aria-label={`Độ tin cậy ${Math.round(v * 100)}%`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} className="fill-none stroke-muted" strokeWidth={8} />
        <circle cx={size / 2} cy={size / 2} r={r} className={cn("fill-none transition-all duration-700", tone)} stroke="currentColor" strokeWidth={8} strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - v)} />
      </svg>
      <span className="absolute text-lg font-extrabold tabular-nums">{Math.round(v * 100)}%</span>
    </div>
  );
}

export function PageHeader({ title, text, action, back, className }: { title: string; text?: string; action?: React.ReactNode; back?: React.ReactNode; className?: string }) {
  return (
    <header className={cn("mb-5", className)}>
      {back}
      <div className="flex items-start justify-between gap-3">
        <div><h1 className="text-2xl font-extrabold md:text-3xl">{title}</h1>{text && <p className="mt-1 text-muted-foreground">{text}</p>}</div>
        {action}
      </div>
    </header>
  );
}
