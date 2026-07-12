import Link from "next/link";
import { ArrowLeft, Award, DollarSign, Rocket, Search, TrendingDown, TrendingUp, Trophy } from "lucide-react";
import { Card } from "@/components/ui/card";
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

function StatCard({ label, value, sublabel }: { label: string; value: React.ReactNode; sublabel?: string }) {
  return (
    <Card className="px-4 py-3.5">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 font-heading text-2xl font-semibold leading-none">{value}</p>
      {sublabel && <p className="mt-1 text-[11px] text-muted-foreground/80">{sublabel}</p>}
    </Card>
  );
}

function PositionRow({ position }: { position: PortfolioPosition }) {
  const meta = METHOD_META[position.method];
  const Icon = meta.icon;
  const beatSpy = position.return_pct - position.spy_return_pct;

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
        <p className="text-[11px] text-muted-foreground">
          {beatSpy >= 0 ? "+" : ""}
          {beatSpy.toFixed(1)}pp vs S&amp;P
        </p>
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

  const { stats, positions } = portfolio;
  const open = positions.filter((p) => p.status === "open");
  const closed = positions.filter((p) => p.status === "closed");

  return (
    <main className="mx-auto w-full max-w-4xl flex-1 px-6 py-8">
      <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft className="size-4" aria-hidden /> Volver al feed
      </Link>

      <div className="mt-6 flex items-center gap-3 border-l-2 border-(--color-accent) pl-4">
        <div className="rounded-full bg-(--color-accent) p-2.5 text-accent-foreground">
          <Trophy className="size-4" aria-hidden />
        </div>
        <div>
          <h1 className="font-heading text-xl font-semibold leading-none">Cartera Pública</h1>
          <p className="mt-1 max-w-lg text-xs text-muted-foreground">
            El track record real, en abierto: la oportunidad excepcional de cada método entra sola
            cuando lo dispara el screener, y sale sola cuando Weinstein confirma que la tendencia
            se rompió. Sin retoques a posteriori.
          </p>
        </div>
      </div>

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
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label="Posiciones" value={stats.total_positions} sublabel={`${stats.open_positions} abiertas · ${stats.closed_positions} cerradas`} />
            <StatCard
              label="Win rate"
              value={stats.win_rate !== null ? `${stats.win_rate}%` : "—"}
            />
            <StatCard
              label="Retorno medio"
              value={stats.avg_return_pct !== null ? <ReturnValue pct={stats.avg_return_pct} /> : "—"}
              sublabel={stats.avg_spy_return_pct !== null ? `S&P 500: ${stats.avg_spy_return_pct >= 0 ? "+" : ""}${stats.avg_spy_return_pct}%` : undefined}
            />
            <StatCard
              label="Mejor / peor pick"
              value={
                <span className="flex items-center gap-2 text-base">
                  {stats.best && (
                    <span className="inline-flex items-center gap-1 text-(--color-stage-advance)">
                      <TrendingUp className="size-3.5" aria-hidden /> {stats.best.ticker}
                    </span>
                  )}
                  {stats.worst && (
                    <span className="inline-flex items-center gap-1 text-(--color-risk-high)">
                      <TrendingDown className="size-3.5" aria-hidden /> {stats.worst.ticker}
                    </span>
                  )}
                </span>
              }
            />
          </div>

          <div className="mt-8 flex flex-col gap-3">
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
              <h2 className="text-sm font-semibold text-foreground">Cerradas ({closed.length})</h2>
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
