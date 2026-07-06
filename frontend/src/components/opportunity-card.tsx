import Link from "next/link";
import { ArrowRight, TrendingUp, BarChart2, Zap } from "lucide-react";
import { Card } from "@/components/ui/card";
import { CriteriaChips } from "@/components/criteria-chips";
import { RiskBadge } from "@/components/risk-badge";
import { StagePill } from "@/components/stage-pill";
import { StrategyBadges } from "@/components/strategy-badges";
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
    classes: "bg-(--color-signal-canslim)/10 text-(--color-signal-canslim) border-(--color-signal-canslim)/30",
  },
  both: {
    label: "Señal Doble",
    sublabel: "Weinstein + CAN SLIM completo",
    icon: Zap,
    classes: "bg-(--color-signal-both)/10 text-(--color-signal-both) border-(--color-signal-both)/30",
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
  const { ticker, name, sector, risk_bucket, weinstein, canslim, last_updated, signal_type, strategies } =
    opportunity;

  return (
    <Card className="group relative flex flex-col gap-4 border-border/60 bg-card p-5 transition-all duration-200 ease-out hover:-translate-y-0.5 hover:border-(--color-stage-advance)/40 hover:shadow-md">
      <Link
        href={`/opportunities/${ticker}`}
        className="absolute inset-0 z-0 rounded-xl focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        aria-label={`Ver análisis completo de ${ticker}${name ? `, ${name}` : ""}`}
      />

      {/* Fila 1: ticker */}
      <div className="relative z-10 flex items-start justify-between gap-3 pointer-events-none">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <h3 className="font-heading text-lg font-semibold tracking-tight">{ticker}</h3>
            {sector && <span className="truncate text-xs text-muted-foreground">{sector}</span>}
          </div>
          <p className="truncate text-sm text-muted-foreground">{name ?? "Nombre no disponible"}</p>
        </div>
      </div>

      {/* Fila 2: badge de señal (el POR QUÉ está aquí) */}
      <div className="relative z-10 pointer-events-none">
        <SignalBadge signal_type={signal_type ?? null} />
      </div>

      {/* Fila 2b: badges de estrategias + snippet de por qué pasa */}
      {strategies && (() => {
        const passing = (Object.entries(strategies) as [import("@/lib/api").StrategyName, import("@/lib/api").StrategyResult][]).filter(([, r]) => r.passed === true);
        if (passing.length === 0) return null;
        // Primer detalle: extraer solo la primera cláusula (antes del primer ";")
        const snippet = passing[0][1].details.split(";")[0].trim();
        return (
          <div className="relative z-10 pointer-events-none flex flex-col gap-2">
            <StrategyBadges strategies={strategies} />
            {snippet && (
              <p className="text-[11px] leading-snug text-muted-foreground line-clamp-2">{snippet}</p>
            )}
          </div>
        );
      })()}

      {/* Fila 3: stage + riesgo */}
      <div className="relative z-10 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        <StagePill weinstein={weinstein} />
        <RiskBadge risk={risk_bucket} />
      </div>

      {/* Fila 4: chips CAN SLIM */}
      <div className="relative z-10 flex items-center gap-3 pointer-events-none">
        <CriteriaChips criteria={canslim.criteria} />
      </div>

      {/* Fila 5: gráfica TradingView — overlay transparente encima para que el Link capture los clicks */}
      <div className="relative z-10 overflow-hidden rounded-lg">
        <TradingViewMiniChart symbol={ticker} />
        <div className="absolute inset-0" aria-hidden />
      </div>

      {/* Fila 6: fecha + flecha */}
      <div className="relative z-10 flex items-center justify-between pointer-events-none">
        <p className="text-[11px] text-muted-foreground/70">Actualizado {last_updated}</p>
        <span className="inline-flex items-center gap-1 text-xs font-medium text-(--color-accent) opacity-0 transition-all duration-200 group-hover:translate-x-0.5 group-hover:opacity-100">
          Ver análisis completo <ArrowRight className="size-3.5" aria-hidden />
        </span>
      </div>
    </Card>
  );
}
