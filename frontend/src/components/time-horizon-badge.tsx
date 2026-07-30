import { Clock } from "lucide-react";
import type { Opportunity } from "@/lib/api";
import { TIME_HORIZON_META, deriveTimeHorizon } from "@/lib/time-horizon";
import { cn } from "@/lib/utils";

export function TimeHorizonBadge({
  opportunity,
  className,
}: {
  opportunity: Pick<Opportunity, "strategies" | "signal_type">;
  className?: string;
}) {
  const horizon = deriveTimeHorizon(opportunity);
  const meta = TIME_HORIZON_META[horizon];
  return (
    <div
      className={cn(
        "flex items-center gap-1.5 rounded-lg border border-border/60 bg-muted/40 px-2.5 py-1.5 text-muted-foreground",
        className,
      )}
    >
      <Clock className="size-3.5 shrink-0" aria-hidden />
      <div className="min-w-0">
        <p className="text-xs font-semibold leading-none text-foreground">{meta.label}</p>
        <p className="mt-0.5 text-[10px] leading-none opacity-80">{meta.sublabel}</p>
      </div>
    </div>
  );
}
