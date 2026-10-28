import { Skeleton } from "@/shared/ui/misc";
import { cn } from "@/shared/lib/utils";

export function PageSkeleton({ full, className }: { full?: boolean; className?: string }) {
  return (
    <div className={cn("mx-auto w-full max-w-3xl space-y-4 p-4", full && "min-h-dvh pt-10", className)} aria-busy="true" aria-label="Đang tải">
      <Skeleton className="h-8 w-1/2" />
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-44 w-full rounded-2xl" />
      <div className="grid grid-cols-2 gap-3"><Skeleton className="h-24" /><Skeleton className="h-24" /></div>
      <Skeleton className="h-32 w-full" />
    </div>
  );
}
