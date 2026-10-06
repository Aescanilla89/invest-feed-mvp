import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";

const EMAIL = "escanillaalberto@gmail.com";

const plans = [
  {
    name: "Fundador",
    price: "149 €",
    cadence: "por año",
    description: "Acceso anticipado para quienes quieran seguir el producto desde el principio.",
    cta: "Solicitar plaza fundadora",
    featured: true,
    features: [
      "Feed completo de oportunidades",
      "Scoring Weinstein + CAN SLIM",
      "Explicación de cada criterio",
      "Catalizadores recientes",
      "Histórico de cartera modelo",
      "Precio bloqueado durante el primer año",
    ],
  },
  {
    name: "Pro",
    price: "19 €",
    cadence: "por mes",
    description: "La experiencia completa para investigar el mercado cada semana.",
    cta: "Apuntarme a la lista",
    featured: false,
    features: [
      "Todo lo incluido en Fundador",
      "Filtros por estrategia",
      "Alertas de oportunidades",
      "Histórico de puntuaciones",
      "Favoritos y listas propias",
    ],
  },
];

function contactHref(subject: string) {
  return `mailto:${EMAIL}?subject=${encodeURIComponent(subject)}`;
}

export default function PricingPage() {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-10 sm:py-16">
      <div className="mb-10 flex items-center justify-between gap-4">
        <Link href="/" className="text-sm font-medium text-muted-foreground hover:text-foreground">
          ← Volver al feed
        </Link>
        <span className="rounded-full border border-(--color-accent)/30 bg-(--color-accent)/10 px-3 py-1 text-xs font-medium text-(--color-accent)">
          Acceso anticipado
        </span>
      </div>

      <section className="max-w-3xl">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-(--color-accent)">
          TradeFinder Pro
        </p>
        <h1 className="mt-4 max-w-2xl font-heading text-4xl font-bold tracking-tight sm:text-6xl">
          Investiga menos ruido. Entiende mejor cada oportunidad.
        </h1>
        <p className="mt-5 max-w-2xl text-lg leading-relaxed text-muted-foreground">
          Un feed de investigación educativa que combina Stage Analysis de Weinstein,
          CAN SLIM y catalizadores trazables para ayudarte a construir tu propio criterio.
        </p>
      </section>

      <section className="mt-12 grid gap-5 lg:grid-cols-2" aria-label="Planes">
        {plans.map((plan) => (
          <article
            key={plan.name}
            className={`relative flex flex-col rounded-2xl border p-7 sm:p-8 ${
              plan.featured
                ? "border-(--color-accent)/60 bg-(--color-accent)/8"
                : "border-border bg-card"
            }`}
          >
            {plan.featured && (
              <span className="absolute -top-3 left-6 rounded-full bg-(--color-accent) px-3 py-1 text-xs font-semibold text-(--color-accent-foreground)">
                Mejor punto de entrada
              </span>
            )}
            <div>
              <h2 className="font-heading text-2xl font-semibold">{plan.name}</h2>
              <p className="mt-3 min-h-12 text-sm leading-relaxed text-muted-foreground">{plan.description}</p>
              <div className="mt-7 flex items-baseline gap-2">
                <span className="font-heading text-4xl font-bold tabular">{plan.price}</span>
                <span className="text-sm text-muted-foreground">{plan.cadence}</span>
              </div>
            </div>
            <ul className="mt-7 space-y-3 border-t border-border/70 pt-6">
              {plan.features.map((feature) => (
                <li key={feature} className="flex gap-3 text-sm text-muted-foreground">
                  <Check className="mt-0.5 size-4 shrink-0 text-(--color-stage-advance)" aria-hidden />
                  <span>{feature}</span>
                </li>
              ))}
            </ul>
            <a
              href={contactHref(`TradeFinder — ${plan.name}`)}
              className={`mt-8 inline-flex h-11 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold transition-colors ${
                plan.featured
                  ? "bg-(--color-accent) text-(--color-accent-foreground) hover:opacity-90"
                  : "border border-border bg-secondary text-secondary-foreground hover:bg-muted"
              }`}
            >
              {plan.cta}
              <ArrowRight className="size-4" aria-hidden />
            </a>
          </article>
        ))}
      </section>

      <section className="mt-12 grid gap-6 border-t border-border/70 pt-8 text-sm text-muted-foreground md:grid-cols-3">
        <div>
          <h2 className="font-semibold text-foreground">Datos con contexto</h2>
          <p className="mt-2 leading-relaxed">Cada puntuación muestra qué se ha comprobado y qué todavía no está disponible.</p>
        </div>
        <div>
          <h2 className="font-semibold text-foreground">Proceso claro</h2>
          <p className="mt-2 leading-relaxed">La herramienta ayuda a investigar; no sustituye tu análisis ni ejecuta órdenes.</p>
        </div>
        <div>
          <h2 className="font-semibold text-foreground">Acceso educativo</h2>
          <p className="mt-2 leading-relaxed">No ofrecemos recomendaciones personalizadas ni prometemos resultados financieros.</p>
        </div>
      </section>
    </main>
  );
}
