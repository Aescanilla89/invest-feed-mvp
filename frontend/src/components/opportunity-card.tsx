import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { CriteriaChips } from "@/components/criteria-chips";
import { RiskBadge } from "@/components/risk-badge";
import { ScoreBadge } from "@/components/score-badge";
import { StagePill } from "@/components/stage-pill";
import type { Opportunity } from "@/lib/api";

export function OpportunityCard({ opportunity }: { opportunity: Opportunity }) {
  const { ticker, name, sector, combined_score, risk_bucket, weinstein, canslim, explanation, last_updated } =
    opportunity;

  return (
    <Card className="group relative flex flex-col gap-4 border-border/60 bg-card p-5 transition-colors hover:border-(--color-stage-advance)/40">
      <Link
        href={`/opportunities/${ticker}`}
        className="absolute inset-0 z-0 rounded-xl focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        aria-label={`Ver análisis completo de ${ticker}${name ? `, ${name}` : ""}`}
      />

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

      <div className="relative z-10 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        <StagePill weinstein={weinstein} />
        <RiskBadge risk={risk_bucket} />
      </div>

      <div className="relative z-10 flex items-center justify-between gap-3 pointer-events-none">
        <CriteriaChips criteria={canslim.criteria} />
        <span className="shrink-0 text-xs text-muted-foreground">{canslim.score}</span>
      </div>

      <div className="relative z-10 border-l-2 border-(--color-accent) pl-3 pointer-events-none">
        {explanation ? (
          <p className="text-sm leading-relaxed text-foreground/90">{explanation}</p>
        ) : (
          <p className="text-sm italic text-muted-foreground">
            Sin explicación generada todavía para esta corrida.
          </p>
        )}
      </div>

      <div className="relative z-10 flex items-center justify-between pointer-events-none">
        <p className="text-[11px] text-muted-foreground/70">Actualizado {last_updated}</p>
        <span className="inline-flex items-center gap-1 text-xs font-medium text-(--color-accent) opacity-0 transition-opacity group-hover:opacity-100">
          Ver análisis completo <ArrowRight className="size-3.5" aria-hidden />
        </span>
      </div>
    </Card>
  );
}
