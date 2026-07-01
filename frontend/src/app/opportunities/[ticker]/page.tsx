import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { CanslimPatternDiagram } from "@/components/canslim-pattern-diagram";
import { CriteriaChips } from "@/components/criteria-chips";
import { WeinsteinChart } from "@/components/weinstein-chart";
import { RiskBadge } from "@/components/risk-badge";
import { ScoreBadge } from "@/components/score-badge";
import { StagePill } from "@/components/stage-pill";
import { WeinsteinCycleDiagram } from "@/components/weinstein-cycle-diagram";
import { ExplanationBullets } from "@/components/explanation-bullets";
import { getOpportunityDetail } from "@/lib/api";

export default async function OpportunityDetailPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params;

  let detail;
  try {
    detail = await getOpportunityDetail(ticker.toUpperCase());
  } catch {
    notFound();
  }

  const { name, sector, combined_score, risk_bucket, weinstein, canslim, explanation, last_updated, price_history } =
    detail;

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-8">
      <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft className="size-4" aria-hidden /> Volver al feed
      </Link>

      <div className="mt-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-baseline gap-2">
            <h1 className="font-heading text-3xl font-bold tracking-tight">{detail.ticker}</h1>
            {sector && <span className="text-sm text-muted-foreground">{sector}</span>}
          </div>
          <p className="mt-1 text-muted-foreground">{name ?? "Nombre no disponible"}</p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <StagePill weinstein={weinstein} />
            <RiskBadge risk={risk_bucket} />
          </div>
        </div>
        <ScoreBadge score={combined_score} />
      </div>

      <section className="mt-8 rounded-xl border border-border/60 bg-card p-5">
        <h2 className="font-heading text-base font-semibold">Por qué es una oportunidad ahora</h2>
        {explanation ? (
          <ExplanationBullets
            explanation={explanation}
            className="mt-3 flex flex-col gap-2 border-l-2 border-(--color-accent) pl-3"
          />
        ) : (
          <p className="mt-3 text-sm italic text-muted-foreground">
            Sin explicación generada todavía para esta corrida.
          </p>
        )}
        <p className="mt-4 text-[11px] text-muted-foreground/70">Actualizado {last_updated}</p>
      </section>

      <section className="mt-6 rounded-xl border border-border/60 bg-card p-5">
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="font-heading text-base font-semibold">Precio semanal · MA30 Weinstein</h2>
          <span className="text-xs text-muted-foreground">Velas semanales · volumen · MA30 (ámbar)</span>
        </div>
        <div className="mt-4 -mx-5">
          <WeinsteinChart
            bars={price_history}
            weeksInStage={weinstein.weeks_in_stage}
            isTransition={weinstein.is_transition}
          />
        </div>
      </section>

      <section className="mt-6 rounded-xl border border-border/60 bg-card p-5">
        <h2 className="font-heading text-base font-semibold">Stage Analysis de Weinstein</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Media móvil de 30 semanas con pendiente {weinstein.ma_slope_pct >= 0 ? "+" : ""}
          {(weinstein.ma_slope_pct * 100).toFixed(1)}% y volumen relativo {weinstein.relative_volume.toFixed(2)}x sobre
          su media de 10 semanas.
        </p>
        <div className="mt-5">
          <WeinsteinCycleDiagram weinstein={weinstein} />
        </div>
      </section>

      <section className="mt-6 rounded-xl border border-border/60 bg-card p-5">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-heading text-base font-semibold">Criterios CAN&nbsp;SLIM</h2>
          <span className="text-sm text-muted-foreground">{canslim.score}</span>
        </div>
        <div className="mt-4">
          <CriteriaChips criteria={canslim.criteria} />
        </div>
        <ul className="mt-4 space-y-2 text-sm">
          {Object.entries(canslim.criteria).map(([letter, criterion]) => (
            <li key={letter} className="flex gap-2 leading-relaxed">
              <span className="font-semibold text-foreground">{letter}</span>
              <span className="text-muted-foreground">{criterion.detail}</span>
            </li>
          ))}
        </ul>
        <div className="mt-6 border-t border-border/60 pt-5">
          <h3 className="text-sm font-semibold">Patrón esperado: base + ruptura</h3>
          <div className="mt-4">
            <CanslimPatternDiagram newHighCriterion={canslim.criteria["N"]} relativeVolume={weinstein.relative_volume} />
          </div>
        </div>
      </section>
    </main>
  );
}
