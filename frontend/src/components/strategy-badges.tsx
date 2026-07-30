import { TrendingUp, Search, Award, DollarSign } from "lucide-react";
import type { StrategyName } from "@/lib/api";

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
