import Link from "next/link";
import { ArrowLeft, Award, DollarSign, Rocket, Search, TrendingUp, Trophy } from "lucide-react";
import { EmptyState, ErrorState } from "@/components/empty-state";
import { getPortfolio } from "@/lib/api";
import type { PortfolioMethod, PortfolioPosition } from "@/lib/api";
import { cn } from "@/lib/utils";

const METHOD_META: Record<PortfolioMethod, { label: string; icon: React.ElementType; color: string }> = {
  early_stage2: { label: "Entrada Temprana", icon: Rocket, color: "text-(--color-strategy-early)" },
  minervini: { label: "Minervini SEPA", icon: TrendingUp, color: "text-(--color-strategy-minervini)" },
  lynch: { label: "Lynch GARP", icon: Search, color: "text-(--color-strategy-lynch)" },
  berkshire: { label: "Berkshire Quality", icon: Award, color: "text-(--color-strategy-berkshire)" },
  dividendos: { label: "Dividendos", icon: DollarSign, color: "text-(--color-strategy-dividendos)" },
};

function ReturnValue({ pct }: { pct: number }) {
  const positive = pct > 0;
  const flat = pct === 0;
  return (
    <span
      className={cn(
        "font-heading font-semibold tabular-nums",
        flat ? "text-muted-foreground" : positive ? "text-(--color-stage-advance)" : "text-(--color-risk-high)",
      )}
    >
      {positive ? "+" : ""}
      {pct.toFixed(1)}%
    </span>
  );
}

/** Cerradas: en vez de listar las ~20+ operaciones cerradas (muchas del
 * mismo ticker reabriéndose tras el stop-loss), se muestra solo lo
 * representativo -- los mejores trades, la mejor operación de cada ticker
 * que cerró en positivo, ordenados de mayor a menor rentabilidad. */
const MAX_TOP_TRADES = 10;

function curateClosedPositions(closed: PortfolioPosition[]): PortfolioPosition[] {
  const bestPerTicker = new Map<string, PortfolioPosition>();
  for (const p of closed) {
    const current = bestPerTicker.get(p.ticker);
    if (!current || p.return_pct > current.return_pct) bestPerTicker.set(p.ticker, p);
  }
  return [...bestPerTicker.values()]
    .filter((p) => p.return_pct > 0)
    .sort((a, b) => b.return_pct - a.return_pct)
    .slice(0, MAX_TOP_TRADES);
}

function PositionRow({ position }: { position: PortfolioPosition }) {
  const meta = METHOD_META[position.method];
  const Icon = meta.icon;

  return (
    <Link
      href={`/opportunities/${position.ticker}`}
      className="grid grid-cols-[1fr_auto] items-center gap-4 rounded-lg border border-border/60 bg-card p-4 transition-colors hover:border-(--color-stage-advance)/40 sm:grid-cols-[auto_1fr_auto_auto_auto]"
    >
      <div className="flex items-center gap-2 sm:w-40">
        <Icon className={cn("size-3.5 shrink-0", meta.color)} aria-hidden />
        <span className={cn("text-xs font-medium", meta.color)}>{meta.label}</span>
      </div>

      <div className="min-w-0 sm:col-start-2">
        <div className="flex items-baseline gap-2">
          <span className="font-heading text-base font-semibold">{position.ticker}</span>
          {position.sector && <span className="truncate text-xs text-muted-foreground">{position.sector}</span>}
        </div>
        <p className="truncate text-xs text-muted-foreground">{position.name ?? "Nombre no disponible"}</p>
      </div>

      <div className="hidden text-right text-xs text-muted-foreground sm:col-start-3 sm:block">
        <p>Entrada {position.entry_date}</p>
        <p className="tabular-nums">${position.entry_price.toFixed(2)} → ${position.current_price.toFixed(2)}</p>
      </div>

      <div className="text-right sm:col-start-4">
        <ReturnValue pct={position.return_pct} />
      </div>

      <span
        className={cn(
          "hidden rounded-full px-2 py-0.5 text-[10px] font-medium sm:col-start-5 sm:block",
          position.status === "open"
            ? "bg-(--color-stage-advance)/10 text-(--color-stage-advance)"
            : "bg-muted text-muted-foreground",
        )}
      >
        {position.status === "open" ? "Abierta" : "Cerrada"}
      </span>

      {position.explanation && (
        <p className="col-span-2 line-clamp-2 text-xs leading-relaxed text-muted-foreground/90 sm:col-span-5">
          {position.explanation}
        </p>
      )}
    </Link>
  );
}

export default async function PortfolioPage() {
  let portfolio;
  try {
    portfolio = await getPortfolio();
  } catch {
    return (
      <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-8">
        <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground">
          <ArrowLeft className="size-4" aria-hidden /> Volver al feed
        </Link>
        <div className="mt-6">
          <ErrorState message="No se pudo conectar con el backend." />
        </div>
      </main>
    );
  }

  const { positions } = portfolio;
  const open = positions.filter((p) => p.status === "open");
  const closed = curateClosedPositions(positions.filter((p) => p.status === "closed"));

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-8">
      <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft className="size-4" aria-hidden /> Volver al feed
      </Link>

      {positions.length === 0 ? (
        <div className="mt-8">
          <EmptyState
            message="Aún no hay picks en la cartera."
            detail="Se abre la primera posición en cuanto algún método detecte una señal excepcional."
            icon={Trophy}
          />
        </div>
      ) : (
        <>
          <div className="mt-6 flex flex-col gap-3">
            <h2 className="text-sm font-semibold text-foreground">Abiertas ({open.length})</h2>
            {open.length === 0 ? (
              <p className="text-sm text-muted-foreground">Sin posiciones abiertas ahora mismo.</p>
            ) : (
              <div className="flex flex-col gap-2">
                {open.map((p) => (
                  <PositionRow key={`${p.ticker}-${p.entry_date}`} position={p} />
                ))}
              </div>
            )}
          </div>

          {closed.length > 0 && (
            <div className="mt-8 flex flex-col gap-3">
              <div>
                <h2 className="text-sm font-semibold text-foreground">Top trades ({closed.length})</h2>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  La mejor operación de cada ticker que cerró en positivo, ordenadas de mayor a menor rentabilidad.
                </p>
              </div>
              <div className="flex flex-col gap-2">
                {closed.map((p) => (
                  <PositionRow key={`${p.ticker}-${p.entry_date}`} position={p} />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </main>
  );
}
