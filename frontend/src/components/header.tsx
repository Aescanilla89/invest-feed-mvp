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
          <h1>
            <Link href="/" aria-label="TradeFinder, inicio" className="inline-flex">
              <Image
                src="/tradefinder-logo.svg"
                alt="TradeFinder"
                width={420}
                height={72}
                priority
                className="h-auto w-[210px] sm:w-[250px]"
              />
            </Link>
          </h1>
          <p className="mt-2 text-sm font-medium uppercase tracking-wide text-white sm:text-base">
            From Market Noise to Clear Decisions
          </p>
          <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-muted-foreground">
            TradeFinder combina Weinstein y CAN SLIM para detectar oportunidades, explicar sus
            señales y seguir su evolución a medida que cambia el mercado.
          </p>
        </div>
      </div>
    </header>
  );
}
