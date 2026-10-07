import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { RiskBadge } from "@/components/risk-badge";
import { TimeHorizonBadge } from "@/components/time-horizon-badge";
import { TradingViewMiniChart } from "@/components/tradingview-mini-chart";
import type { Opportunity } from "@/lib/api";

function formatDetectedDate(value: string) {
  return new Intl.DateTimeFormat("es-ES", { day: "2-digit", month: "2-digit", timeZone: "UTC" })
    .format(new Date(`${value}T12:00:00Z`));
}

function formatReturn(value: number) {
  return `${value > 0 ? "+" : ""}${value.toLocaleString("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
}

export function OpportunityCard({ opportunity }: { opportunity: Opportunity }) {
  const { ticker, name, sector, risk_bucket, last_updated, first_detected_date, return_since_first_detected_pct } = opportunity;

  return (
    <Card className="group relative flex h-full flex-col gap-4 border-border/60 bg-card p-5 transition-all duration-200 ease-out hover:-translate-y-0.5 hover:border-(--color-stage-advance)/40 hover:shadow-md">
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

      {/* Fila 2: horizonte temporal de la inversión -- sin metodologías
       * (Weinstein/CAN SLIM/estrategias) a la vista, eso vive solo en el
       * detalle del ticker. */}
      <div className="relative z-10 pointer-events-none">
        <TimeHorizonBadge opportunity={opportunity} />
      </div>

      {/* Fila 3: volatilidad y evolución desde la primera detección */}
      <div className="relative z-10 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 pointer-events-none">
        <RiskBadge risk={risk_bucket} />
        {first_detected_date && (
          <div className="flex items-center gap-2 text-xs tabular-nums">
            <span className="text-muted-foreground">Detectada {formatDetectedDate(first_detected_date)}</span>
            <span
              className={cn(
                "font-semibold",
                return_since_first_detected_pct == null && "text-muted-foreground",
                return_since_first_detected_pct != null && return_since_first_detected_pct > 0 && "text-(--color-risk-low)",
                return_since_first_detected_pct != null && return_since_first_detected_pct < 0 && "text-(--color-risk-high)",
                return_since_first_detected_pct === 0 && "text-muted-foreground",
              )}
              title="Variación del precio desde la primera detección registrada. Rentabilidad histórica; no representa una operación ejecutada."
            >
              {return_since_first_detected_pct == null ? "—" : formatReturn(return_since_first_detected_pct)}
            </span>
          </div>
        )}
      </div>

      {/* Fila 4: gráfica TradingView — overlay transparente encima para que el Link capture los clicks */}
      <div className="relative z-10 mt-auto overflow-hidden rounded-lg">
        <TradingViewMiniChart symbol={ticker} />
        <div className="absolute inset-0" aria-hidden />
      </div>

      {/* Fila 5: fecha + flecha */}
      <div className="relative z-10 flex items-center justify-between pointer-events-none">
        <p className="text-[11px] text-muted-foreground/70">Actualizado {last_updated}</p>
        <span className="inline-flex items-center gap-1 text-xs font-medium text-(--color-accent) opacity-0 transition-all duration-200 group-hover:translate-x-0.5 group-hover:opacity-100">
          Ver análisis completo <ArrowRight className="size-3.5" aria-hidden />
        </span>
      </div>
    </Card>
  );
}
