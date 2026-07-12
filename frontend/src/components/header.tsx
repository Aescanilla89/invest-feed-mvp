import Link from "next/link";

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

export function Header() {
  return (
    <header className="border-b border-border/60">
      {DEMO_MODE && (
        <div className="bg-(--color-accent)/15 px-6 py-1.5 text-center text-xs font-medium text-(--color-accent)">
          Preview de diseño con datos de ejemplo — no conectado al screener en vivo
        </div>
      )}
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-8 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold tracking-tight sm:text-3xl">
            <Link href="/">
              Trade
              <span className="relative text-(--color-accent)">
                Finder
                <span className="absolute -right-2.5 top-1 size-1.5 rounded-full bg-(--color-stage-advance) motion-safe:animate-pulse" aria-hidden />
              </span>
            </Link>
          </h1>
          <p className="mt-1 text-xs font-medium uppercase tracking-wide text-(--color-accent)">
            From Market Noise to Clear Decisions
          </p>
          <p className="mt-1.5 max-w-md text-sm text-muted-foreground">
            Oportunidades rankeadas combinando Stage Analysis de Weinstein y CAN&nbsp;SLIM —
            con el porqué explicado, no solo el qué.
          </p>
        </div>
        <nav className="flex items-center gap-4">
          <Link href="/" className="text-sm font-medium text-muted-foreground transition-colors hover:text-foreground">
            Feed
          </Link>
          <Link href="/portfolio" className="text-sm font-medium text-muted-foreground transition-colors hover:text-foreground">
            Cartera pública
          </Link>
          <p className="hidden max-w-xs text-xs leading-relaxed text-muted-foreground/80 lg:block">
            Información educativa con retraso, no asesoramiento financiero ni ejecución de
            órdenes.
          </p>
        </nav>
      </div>
    </header>
  );
}
