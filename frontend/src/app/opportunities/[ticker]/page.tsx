import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Lightbulb, LineChart, ListChecks } from "lucide-react";
import { CanslimPatternDiagram } from "@/components/canslim-pattern-diagram";
import { CriteriaChips } from "@/components/criteria-chips";
import { WeinsteinChart } from "@/components/weinstein-chart";
import { RiskBadge } from "@/components/risk-badge";
import { StagePill } from "@/components/stage-pill";
import { WeinsteinCycleDiagram } from "@/components/weinstein-cycle-diagram";
import { ExplanationBullets } from "@/components/explanation-bullets";
import { StrategyBadges } from "@/components/strategy-badges";
import { getOpportunityDetail } from "@/lib/api";

export default async function OpportunityDetailPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params;

  let detail;
  try {
    detail = await getOpportunityDetail(ticker.toUpperCase());
  } catch {
    notFound();
  }

  const { name, sector, risk_bucket, weinstein, canslim, explanation, last_updated, price_history, strategies } =
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
          {strategies && <StrategyBadges strategies={strategies} className="mt-2" />}
        </div>
      </div>

      {/* Explicación IA -- la sección con más peso de la página: regla de
       * acento a la izquierda + icono en círculo relleno + tinte de fondo,
       * sin chrome de card, para que destaque sobre las secciones de
       * referencia que le siguen. */}
      <section className="mt-8 rounded-r-lg border-l-2 border-(--color-accent) bg-(--color-accent)/5 py-4 pl-5 pr-4">
        <div className="flex items-center gap-2.5">
          <div className="rounded-full bg-(--color-accent) p-1.5 text-accent-foreground">
            <Lightbulb className="size-3.5" aria-hidden />
          </div>
          <h2 className="font-heading text-lg font-semibold leading-none">Por qué es una oportunidad ahora</h2>
        </div>
        {explanation ? (
          <ExplanationBullets explanation={explanation} className="mt-4 flex flex-col gap-2" />
        ) : (
          <p className="mt-4 text-sm italic text-muted-foreground">
            Sin explicación generada todavía para esta corrida.
          </p>
        )}
        <p className="mt-4 text-[11px] text-muted-foreground/70">Actualizado {last_updated}</p>
      </section>

      {/* Precio + Stage Analysis -- combinados en una sola card (ambos son
       * lectura del mismo Weinstein) en vez de dos bloques idénticos
       * apilados; sigue siendo la card con más contenido visual tras la
       * explicación. */}
      <section className="mt-6 rounded-xl border border-border/60 bg-card p-5">
        <div className="flex items-center gap-2 text-(--color-stage-neutral)">
          <LineChart className="size-4 shrink-0" aria-hidden />
          <h2 className="font-heading text-base font-semibold text-foreground">Precio semanal · Stage Analysis de Weinstein</h2>
        </div>
        <div className="mt-1 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <p className="text-xs text-muted-foreground">
            Media móvil de 30 semanas con pendiente {weinstein.ma_slope_pct >= 0 ? "+" : ""}
            {(weinstein.ma_slope_pct * 100).toFixed(1)}% y volumen relativo {weinstein.relative_volume.toFixed(2)}x sobre
            su media de 10 semanas.
          </p>
          <span className="text-xs text-muted-foreground">Velas semanales · volumen · MA30 (ámbar)</span>
        </div>
        <div className="mt-4 -mx-5">
          <WeinsteinChart
            bars={price_history}
            weeksInStage={weinstein.weeks_in_stage}
            isTransition={weinstein.is_transition}
          />
        </div>
        <div className="mt-6 border-t border-border/60 pt-5">
          <h3 className="text-sm font-semibold text-muted-foreground">Ciclo de Weinstein</h3>
          <div className="mt-4">
            <WeinsteinCycleDiagram weinstein={weinstein} />
          </div>
        </div>
      </section>

      {/* Estrategias adicionales -- sección de referencia, sin chrome de
       * card: divisor superior simple y encabezado discreto en vez de otra
       * caja idéntica. */}
      {strategies && Object.values(strategies).some((r) => r.passed) && (
        <section className="mt-8 border-t border-border/60 pt-5">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Estrategias adicionales</h2>
          <ul className="mt-3 space-y-3">
            {(Object.entries(strategies) as [string, { passed: boolean | null; score: number | null; details: string }][])
              .filter(([, r]) => r.passed)
              .map(([name, r]) => (
                <li key={name} className="flex flex-col gap-0.5">
                  <span className="text-sm font-medium capitalize">{name} {r.score !== null && `· ${r.score}/100`}</span>
                  <span className="text-xs text-muted-foreground">{r.details}</span>
                </li>
              ))}
          </ul>
        </section>
      )}

      {/* Criterios CAN SLIM -- también de referencia; card más discreta
       * (borde tenue, sin bg-card) y encabezado más pequeño que las
       * secciones de arriba para reforzar la jerarquía. */}
      <section className="mt-8 rounded-lg border border-border/40 p-5">
        <div className="flex items-center gap-2 text-muted-foreground">
          <ListChecks className="size-4 shrink-0" aria-hidden />
          <h2 className="text-sm font-semibold text-foreground">Criterios CAN&nbsp;SLIM</h2>
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
