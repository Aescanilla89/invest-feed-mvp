import { TrendingUp, Search, Award, DollarSign } from "lucide-react";
import type { StrategyName, StrategyResult } from "@/lib/api";
import { cn } from "@/lib/utils";

const STRATEGY_META: Record<StrategyName, { label: string; icon: React.ElementType; classes: string }> = {
  minervini: {
    label: "Minervini",
    icon: TrendingUp,
    classes: "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/30",
  },
  lynch: {
    label: "Lynch",
    icon: Search,
    classes: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30",
  },
  berkshire: {
    label: "Berkshire",
    icon: Award,
    classes: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30",
  },
  dividendos: {
    label: "Dividendo",
    icon: DollarSign,
    classes: "bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/30",
  },
};

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
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {active.map(([name, result]) => {
        const meta = STRATEGY_META[name];
        const Icon = meta.icon;
        return (
          <span
            key={name}
            title={result.details}
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium",
              meta.classes,
            )}
          >
            <Icon className="size-2.5 shrink-0" aria-hidden />
            {meta.label}
            {result.score !== null && <span className="opacity-70">{result.score}</span>}
          </span>
        );
      })}
    </div>
  );
}
