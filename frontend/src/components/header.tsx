import Link from "next/link";
import Image from "next/image";

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

export function Header() {
  return (
    <header className="border-b border-border/60">
      {DEMO_MODE && (
        <div className="bg-(--color-accent)/15 px-6 py-1.5 text-center text-xs font-medium text-(--color-accent)">
          Preview de diseño con datos de ejemplo — no conectado al screener en vivo
        </div>
      )}
      <div className="mx-auto flex max-w-6xl flex-col gap-5 px-6 py-8 sm:flex-row sm:items-center sm:justify-between sm:gap-8">
        <div className="max-w-3xl">
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
          <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-muted-foreground">
            TradeFinder combina Weinstein y CAN SLIM para detectar oportunidades, explicar sus
            señales y seguir su evolución a medida que cambia el mercado.
          </p>
        </div>
        <Image
          src="/tradefinder-logo.svg"
          alt="TradeFinder"
          width={420}
          height={72}
          priority
          className="hidden h-auto w-[210px] shrink-0 md:block lg:w-[250px]"
        />
      </div>
    </header>
  );
}
