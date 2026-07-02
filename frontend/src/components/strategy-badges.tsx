import { TrendingUp, Search, Award, DollarSign } from "lucide-react";
import type { StrategyName, StrategyResult } from "@/lib/api";
import { cn } from "@/lib/utils";

export const STRATEGY_META: Record<
  StrategyName,
  { label: string; sublabel: string; icon: React.ElementType; classes: string; pillClasses: string }
> = {
  minervini: {
    label: "Minervini SEPA",
    sublabel: "Trend Template · 6/7 criterios",
    icon: TrendingUp,
    classes: "bg-(--color-strategy-minervini)/10 text-(--color-strategy-minervini) border-(--color-strategy-minervini)/30",
    pillClasses: "bg-(--color-strategy-minervini)/10 text-(--color-strategy-minervini) border-(--color-strategy-minervini)/30",
  },
  lynch: {
    label: "Lynch GARP",
    sublabel: "PEG ratio · crecimiento razonable",
    icon: Search,
    classes: "bg-(--color-strategy-lynch)/10 text-(--color-strategy-lynch) border-(--color-strategy-lynch)/30",
    pillClasses: "bg-(--color-strategy-lynch)/10 text-(--color-strategy-lynch) border-(--color-strategy-lynch)/30",
  },
  berkshire: {
    label: "Berkshire Quality",
    sublabel: "Márgenes · OCF/NI · ROE",
    icon: Award,
    classes: "bg-(--color-strategy-berkshire)/10 text-(--color-strategy-berkshire) border-(--color-strategy-berkshire)/30",
    pillClasses: "bg-(--color-strategy-berkshire)/10 text-(--color-strategy-berkshire) border-(--color-strategy-berkshire)/30",
  },
  dividendos: {
    label: "Dividendo",
    sublabel: "Yield ≥2.5% · payout sostenible",
    icon: DollarSign,
    classes: "bg-(--color-strategy-dividendos)/10 text-(--color-strategy-dividendos) border-(--color-strategy-dividendos)/30",
    pillClasses: "bg-(--color-strategy-dividendos)/10 text-(--color-strategy-dividendos) border-(--color-strategy-dividendos)/30",
  },
};

/** Badges grandes (mismo tamaño que SignalBadge de Weinstein/CAN SLIM) */
interface StrategyBadgesProps {
  strategies: Partial<Record<StrategyName, StrategyResult>>;
  className?: string;
}

export function StrategyBadges({ strategies, className }: StrategyBadgesProps) {
  const active = (Object.entries(strategies) as [StrategyName, StrategyResult][]).filter(
    ([, r]) => r.passed === true,
  );
  if (active.length === 0) return null;

  return (
    <div className={cn("flex flex-wrap gap-2", className)}>
      {active.map(([name, result]) => {
        const meta = STRATEGY_META[name];
        const Icon = meta.icon;
        return (
          <div
            key={name}
            title={result.details}
            className={cn(
              "flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5",
              meta.classes,
            )}
          >
            <Icon className="size-3.5 shrink-0" aria-hidden />
            <div className="min-w-0">
              <p className="text-xs font-semibold leading-none">
                {meta.label}
                {result.score !== null && (
                  <span className="ml-1 font-normal opacity-70">{result.score}</span>
                )}
              </p>
              <p className="mt-0.5 text-[10px] leading-none opacity-80">{meta.sublabel}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
