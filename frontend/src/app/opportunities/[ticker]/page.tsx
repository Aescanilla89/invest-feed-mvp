import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Clock, Lightbulb, LineChart, ListChecks } from "lucide-react";
import { CanslimPatternDiagram } from "@/components/canslim-pattern-diagram";
import { CriteriaChips } from "@/components/criteria-chips";
import { WeinsteinChart } from "@/components/weinstein-chart";
import { RiskBadge } from "@/components/risk-badge";
import { StagePill } from "@/components/stage-pill";
import { WeinsteinCycleDiagram } from "@/components/weinstein-cycle-diagram";
import { ExplanationBullets } from "@/components/explanation-bullets";
import { STRATEGY_META } from "@/components/strategy-badges";
import { TimeHorizonBadge } from "@/components/time-horizon-badge";
import { getOpportunityDetail, getPortfolio, type PortfolioPosition } from "@/lib/api";
import { cn } from "@/lib/utils";

// Gancho en una frase por método, en lenguaje llano -- lo que vio el sistema,
// no el desglose técnico de criterios (ese ya está en "Metodologías" más
// abajo, no hace falta repetirlo aquí en la narrativa).
const METHOD_HOOKS: Record<string, string> = {
  early_stage2: "acababa de salir de suelo con volumen fuerte detrás",
  minervini: "rompía en tendencia con una estructura de libro",
  lynch: "cotizaba barata para lo que estaba creciendo",
  berkshire: "tenía la pinta de negocio de calidad que aguanta ciclos",
  dividendos: "pagaba un dividendo sólido y sostenible",
};

const EXIT_REASON_LABELS: Record<string, string> = {
  ma40_break: "se le rompió la tendencia de fondo",
  weinstein_stage_1: "se le rompió la tendencia",
  weinstein_stage_4: "se le rompió la tendencia",
};

function describeExitReason(reason: string | null): string {
  if (!reason) return "cerramos sin motivo registrado";
  if (reason in EXIT_REASON_LABELS) return EXIT_REASON_LABELS[reason];
  const stopMatch = reason.match(/^trailing_stop_(\d+)pct$/);
  if (stopMatch) return `saltó el stop`;
  return reason;
}

/** Storytelling de una operación ya cerrada: sustituye a "por qué es una
 * oportunidad ahora" (que no tiene sentido para algo que ya no está
 * abierto) por el relato de cómo fue, en tono directo y sin la jerga de
 * criterios técnicos (esa ya vive en "Metodologías" más abajo). */
function buildTradeStory(p: PortfolioPosition): string {
  const hook = METHOD_HOOKS[p.method] ?? "encajaba con la señal del sistema";
  const weeksOpen = p.exit_date
    ? Math.max(1, Math.round((new Date(p.exit_date).getTime() - new Date(p.entry_date).getTime()) / (7 * 86400000)))
    : null;
  const isWin = p.return_pct >= 0;
  const pct = Math.abs(p.return_pct).toFixed(1);

  let story = `El ${p.entry_date}, ${p.ticker} entró en el radar: ${hook}. Compramos a $${p.entry_price.toFixed(2)}.`;

  if (p.exit_date && weeksOpen !== null) {
    if (isWin) {
      story += ` ${weeksOpen} semana${weeksOpen === 1 ? "" : "s"} después tocaba recoger: vendimos a `
        + `$${p.current_price.toFixed(2)}, un +${pct}% de subida.`;
    } else {
      story += ` No salió como esperábamos: ${weeksOpen} semana${weeksOpen === 1 ? "" : "s"} después `
        + `${describeExitReason(p.exit_reason)}, así que cerramos a $${p.current_price.toFixed(2)}, -${pct}%. `
        + `El método corta rápido lo que deja de funcionar.`;
    }
  }
  return story;
}

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

  // Posiciones reales de la cartera pública para este ticker (puede haber
  // varias si el mismo ticker entró y salió más de una vez) -- se pintan
  // como marcadores de entrada/salida sobre el mismo gráfico de precio, y
  // no hace falta manejar el error de conexión aquí porque ya se resolvió
  // (con notFound) al pedir el detalle de la oportunidad arriba.
  const portfolio = await getPortfolio().catch(() => null);
  const tickerPositions = (portfolio?.positions ?? []).filter((p) => p.ticker === detail.ticker);

  // Si el ticker tiene una posición abierta ahora mismo, sigue siendo una
  // oportunidad activa -- se muestra el "por qué ahora" de siempre. Si solo
  // tiene historial cerrado (sin ninguna abierta), no tiene sentido esa
  // pregunta: se cuenta cómo fue la operación en su lugar.
  const openPosition = tickerPositions.find((p) => p.status === "open");
  const closedPositions = [...tickerPositions]
    .filter((p) => p.status === "closed")
    .sort((a, b) => b.entry_date.localeCompare(a.entry_date));
  const showTradeStory = !openPosition && closedPositions.length > 0;

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
            <TimeHorizonBadge opportunity={detail} />
          </div>
        </div>
      </div>

      {/* Explicación IA / storytelling -- la sección con más peso de la
       * página: regla de acento a la izquierda + icono en círculo relleno +
       * tinte de fondo, sin chrome de card, para que destaque sobre las
       * secciones de referencia que le siguen. Si el ticker ya no tiene
       * posición abierta, "por qué es una oportunidad ahora" no aplica --
       * se cuenta cómo fue la operación (o las operaciones, si entró y
       * salió más de una vez) en su lugar. */}
      {showTradeStory ? (
        <section className="mt-8 rounded-r-lg border-l-2 border-(--color-accent) bg-(--color-accent)/5 py-4 pl-5 pr-4">
          <div className="flex items-center gap-2.5">
            <div className="rounded-full bg-(--color-accent) p-1.5 text-accent-foreground">
              <Clock className="size-3.5" aria-hidden />
            </div>
            <h2 className="font-heading text-lg font-semibold leading-none">
              {closedPositions.length > 1 ? "Cómo fueron estas inversiones" : "Cómo fue esta inversión"}
            </h2>
          </div>
          <div className="mt-4 flex flex-col gap-3">
            {closedPositions.map((p) => (
              <p key={`${p.entry_date}-${p.method}`} className="text-sm leading-relaxed text-foreground/90">
                {buildTradeStory(p)}
              </p>
            ))}
          </div>
        </section>
      ) : (
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
      )}

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
            positions={tickerPositions}
          />
        </div>
        {tickerPositions.length > 0 && (
          <ul className="mt-3 flex flex-col gap-1.5">
            {tickerPositions.map((p) => (
              <li key={`${p.entry_date}-${p.method}`} className="flex flex-wrap items-baseline gap-x-1.5 text-xs text-muted-foreground">
                <span className="font-medium text-(--color-stage-advance)">Entrada {p.entry_date}</span>
                <span>(${p.entry_price.toFixed(2)})</span>
                {p.exit_date ? (
                  <>
                    <span>→</span>
                    <span className="font-medium text-(--color-risk-high)">Salida {p.exit_date}</span>
                    {p.exit_reason && <span>({describeExitReason(p.exit_reason)})</span>}
                  </>
                ) : (
                  <span className="italic">— posición abierta</span>
                )}
              </li>
            ))}
          </ul>
        )}
        <div className="mt-6 border-t border-border/60 pt-5">
          <h3 className="text-sm font-semibold text-muted-foreground">Ciclo de Weinstein</h3>
          <div className="mt-4">
            <WeinsteinCycleDiagram weinstein={weinstein} />
          </div>
        </div>
      </section>

      {/* Metodologías -- muestra las 4 estrategias completas (cumple o no),
       * no solo las que pasan, para que el detalle sea la única vista donde
       * se ve el desglose de metodología. */}
      {strategies && (
        <section className="mt-8 border-t border-border/60 pt-5">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Metodologías</h2>
          <ul className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            {(Object.entries(STRATEGY_META) as [keyof typeof STRATEGY_META, (typeof STRATEGY_META)[keyof typeof STRATEGY_META]][])
              .map(([name, meta]) => {
                const result = strategies[name];
                const Icon = meta.icon;
                const passed = result?.passed ?? null;
                return (
                  <li
                    key={name}
                    className={cn(
                      "flex items-start gap-2.5 rounded-lg border px-3 py-2.5",
                      passed === true && meta.classes,
                      passed === false && "border-border/40 text-muted-foreground/60",
                      passed === null && "border-dashed border-border/40 text-muted-foreground/60",
                    )}
                  >
                    <Icon className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                    <div className="min-w-0">
                      <p className="text-sm font-medium leading-none">
                        {meta.label}
                        {result?.score !== null && result?.score !== undefined && (
                          <span className="ml-1.5 font-normal opacity-70">{result.score}/100</span>
                        )}
                        {passed === false && <span className="ml-1.5 font-normal">· no cumple</span>}
                        {passed === null && <span className="ml-1.5 font-normal">· sin datos</span>}
                      </p>
                      <p className="mt-1 text-xs leading-snug opacity-80">{result?.details ?? meta.sublabel}</p>
                    </div>
                  </li>
                );
              })}
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
