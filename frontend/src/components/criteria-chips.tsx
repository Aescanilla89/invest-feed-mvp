import { Check, Minus, X } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { CanslimCriterion } from "@/lib/api";
import { CANSLIM_LABELS, CANSLIM_ORDER } from "@/lib/canslim-labels";
import { cn } from "@/lib/utils";

export function CriteriaChips({ criteria }: { criteria: Record<string, CanslimCriterion> }) {
  return (
    <div className="flex flex-wrap gap-1.5" role="list" aria-label="Criterios CAN SLIM">
      {CANSLIM_ORDER.map((letter) => {
        const criterion = criteria[letter];
        const value = criterion?.value ?? null;
        return (
          <Tooltip key={letter}>
            <TooltipTrigger
              render={
                <span
                  role="listitem"
                  tabIndex={0}
                  className={cn(
                    "relative z-10 pointer-events-auto inline-flex h-6 w-6 items-center justify-center rounded-md text-xs font-semibold transition-colors cursor-default",
                    value === true && "bg-(--color-risk-low)/15 text-(--color-risk-low)",
                    value === false && "bg-muted text-muted-foreground/50 line-through",
                    value === null && "border border-dashed border-muted-foreground/40 text-muted-foreground/60",
                  )}
                >
                  {letter}
                </span>
              }
            />
            <TooltipContent>
              <p className="max-w-64 text-xs">
                <span className="font-semibold">{CANSLIM_LABELS[letter]}: </span>
                {criterion?.detail ?? "Sin datos."}
              </p>
            </TooltipContent>
          </Tooltip>
        );
      })}
    </div>
  );
}

export function CriteriaLegend() {
  return (
    <div className="flex items-center gap-3 text-xs text-muted-foreground">
      <span className="inline-flex items-center gap-1">
        <Check className="size-3 text-(--color-risk-low)" /> cumple
      </span>
      <span className="inline-flex items-center gap-1">
        <X className="size-3" /> no cumple
      </span>
      <span className="inline-flex items-center gap-1">
        <Minus className="size-3" /> no verificable
      </span>
    </div>
  );
}
