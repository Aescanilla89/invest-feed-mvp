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
    classes: "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/30",
    pillClasses: "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/30",
  },
  lynch: {
    label: "Lynch GARP",
    sublabel: "PEG ratio · crecimiento razonable",
    icon: Search,
    classes: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30",
    pillClasses: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30",
  },
  berkshire: {
    label: "Berkshire Quality",
    sublabel: "Márgenes · OCF/NI · ROE",
    icon: Award,
    classes: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30",
    pillClasses: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30",
  },
  dividendos: {
    label: "Dividendo",
    sublabel: "Yield ≥2.5% · payout sostenible",
    icon: DollarSign,
    classes: "bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/30",
    pillClasses: "bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/30",
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
