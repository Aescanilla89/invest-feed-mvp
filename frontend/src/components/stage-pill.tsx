import { ArrowUpRight, Minus, TrendingDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Weinstein } from "@/lib/api";

const STAGE_LABEL: Record<number, string> = {
  1: "Base",
  2: "Avance",
  3: "Techo",
  4: "Declive",
};

export function StagePill({ weinstein }: { weinstein: Weinstein }) {
  const { stage, is_transition, weeks_in_stage } = weinstein;
  const isAdvance = stage === 2;
  const isDecline = stage === 4;

  return (
    <div className="flex items-center gap-2">
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium tabular",
          isAdvance && "bg-(--color-stage-advance)/15 text-(--color-stage-advance)",
          isDecline && "bg-(--color-stage-decline)/15 text-(--color-stage-decline)",
          !isAdvance && !isDecline && "bg-(--color-stage-neutral)/15 text-(--color-stage-neutral)",
        )}
      >
        {isAdvance && <ArrowUpRight className="size-3.5" aria-hidden />}
        {isDecline && <TrendingDown className="size-3.5" aria-hidden />}
        {!isAdvance && !isDecline && <Minus className="size-3.5" aria-hidden />}
        Stage {stage} · {STAGE_LABEL[stage]}
      </span>
      <span className="text-xs text-muted-foreground">{weeks_in_stage} sem</span>
      {is_transition && (
        <span className="relative rounded-full bg-(--color-stage-advance)/20 px-2 py-0.5 text-[11px] font-semibold text-(--color-stage-advance)">
          <span className="absolute inset-0 rounded-full bg-(--color-stage-advance)/25 motion-safe:animate-pulse" aria-hidden />
          <span className="relative">Transición 1→2</span>
        </span>
      )}
    </div>
  );
}
