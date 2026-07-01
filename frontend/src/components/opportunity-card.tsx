import Link from "next/link";
import { ArrowRight, TrendingUp, BarChart2, Zap } from "lucide-react";
import { Card } from "@/components/ui/card";
import { CriteriaChips } from "@/components/criteria-chips";
import { RiskBadge } from "@/components/risk-badge";
import { ScoreBadge } from "@/components/score-badge";
import { StagePill } from "@/components/stage-pill";
import { TradingViewMiniChart } from "@/components/tradingview-mini-chart";
import type { Opportunity, SignalType } from "@/lib/api";
import { cn } from "@/lib/utils";

const SIGNAL_META: Record<
  NonNullable<SignalType>,
  { label: string; sublabel: string; icon: React.ElementType; classes: string }
> = {
  weinstein: {
    label: "Entrada Weinstein",
    sublabel: "Stage 1→2 con volumen",
    icon: TrendingUp,
    classes: "bg-(--color-stage-advance)/15 text-(--color-stage-advance) border-(--color-stage-advance)/30",
  },
  canslim: {
    label: "Rotura CAN SLIM",
    sublabel: "ATH con volumen · todos los criterios",
    icon: BarChart2,
    classes: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/30",
  },
  both: {
    label: "Señal Doble",
    sublabel: "Weinstein + CAN SLIM completo",
    icon: Zap,
    classes: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30",
  },
};

function SignalBadge({ signal_type }: { signal_type: SignalType }) {
  if (!signal_type) return null;
  const meta = SIGNAL_META[signal_type];
  const Icon = meta.icon;
  return (
    <div className={cn("flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5", meta.classes)}>
      <Icon className="size-3.5 shrink-0" aria-hidden />
      <div className="min-w-0">
        <p className="text-xs font-semibold leading-none">{meta.label}</p>
        <p className="mt-0.5 text-[10px] leading-none opacity-80">{meta.sublabel}</p>
      </div>
    </div>
  );
}

export function OpportunityCard({ opportunity }: { opportunity: Opportunity }) {
  const { ticker, name, sector, combined_score, risk_bucket, weinstein, canslim, last_updated, signal_type } =
    opportunity;

  return (
    <Card className="group relative flex flex-col gap-4 border-border/60 bg-card p-5 transition-colors hover:border-(--color-stage-advance)/40">
      <Link
        href={`/opportunities/${ticker}`}
        className="absolute inset-0 z-0 rounded-xl focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        aria-label={`Ver análisis completo de ${ticker}${name ? `, ${name}` : ""}`}
      />

      {/* Fila 1: ticker + score */}
      <div className="relative z-10 flex items-start justify-between gap-3 pointer-events-none">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <h3 className="font-heading text-lg font-semibold tracking-tight">{ticker}</h3>
            {sector && <span className="truncate text-xs text-muted-foreground">{sector}</span>}
          </div>
          <p className="truncate text-sm text-muted-foreground">{name ?? "Nombre no disponible"}</p>
        </div>
        <ScoreBadge score={combined_score} />
      </div>

      {/* Fila 2: badge de señal (el POR QUÉ está aquí) */}
      <div className="relative z-10 pointer-events-none">
        <SignalBadge signal_type={signal_type ?? null} />
      </div>

      {/* Fila 3: stage + riesgo */}
      <div className="relative z-10 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        <StagePill weinstein={weinstein} />
        <RiskBadge risk={risk_bucket} />
      </div>

      {/* Fila 4: chips CAN SLIM */}
      <div className="relative z-10 flex items-center justify-between gap-3 pointer-events-none">
        <CriteriaChips criteria={canslim.criteria} />
        <span className="shrink-0 text-xs text-muted-foreground">{canslim.score}</span>
      </div>

      {/* Fila 5: gráfica TradingView — overlay transparente encima para que el Link capture los clicks */}
      <div className="relative z-10 overflow-hidden rounded-lg">
        <TradingViewMiniChart symbol={ticker} />
        <div className="absolute inset-0" aria-hidden />
      </div>

      {/* Fila 6: fecha + flecha */}
      <div className="relative z-10 flex items-center justify-between pointer-events-none">
        <p className="text-[11px] text-muted-foreground/70">Actualizado {last_updated}</p>
        <span className="inline-flex items-center gap-1 text-xs font-medium text-(--color-accent) opacity-0 transition-opacity group-hover:opacity-100">
          Ver análisis completo <ArrowRight className="size-3.5" aria-hidden />
        </span>
      </div>
    </Card>
  );
}
