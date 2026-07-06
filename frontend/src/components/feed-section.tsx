"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Flame, TrendingUp, Search, Award, DollarSign, Rocket } from "lucide-react";
import { OpportunityCard } from "@/components/opportunity-card";
import { OpportunityCardSkeleton } from "@/components/opportunity-card-skeleton";
import { EmptyState, ErrorState } from "@/components/empty-state";
import { FilterBar, type FeedFilters } from "@/components/filter-bar";
import { getOpportunities, type Opportunity, type StrategyName } from "@/lib/api";
import { cn } from "@/lib/utils";

const DEFAULT_FILTERS: FeedFilters = { risk: "todos", sector: "todos" };

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.05, delayChildren: 0.05 } },
};
const item = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 1, 0.5, 1] as const } },
};

// "early_stage2" es un filtro propio (Weinstein stage+semanas), no una de las
// 4 estrategias evaluadas en el JSON `strategies` del backend -- de ahí el tipo
// separado para las pestañas de esta sección.
type FeedTabKey = StrategyName | "early_stage2";

const STRATEGY_SECTIONS: {
  key: FeedTabKey;
  label: string;
  sublabel: string;
  icon: React.ElementType;
  tabActive: string;
  iconColor: string;
}[] = [
  {
    key: "early_stage2",
    label: "Entrada Temprana",
    sublabel: "Stage 2 recién confirmado · máx. 6 semanas",
    icon: Rocket,
    tabActive: "border-(--color-strategy-early)/50 bg-(--color-strategy-early)/10 text-(--color-strategy-early)",
    iconColor: "text-(--color-strategy-early)",
  },
  {
    key: "minervini",
    label: "Minervini SEPA",
    sublabel: "Trend Template · precio sobre MAs · fuerza relativa",
    icon: TrendingUp,
    tabActive: "border-(--color-strategy-minervini)/50 bg-(--color-strategy-minervini)/10 text-(--color-strategy-minervini)",
    iconColor: "text-(--color-strategy-minervini)",
  },
  {
    key: "lynch",
    label: "Lynch GARP",
    sublabel: "Growth at a Reasonable Price · PEG ratio",
    icon: Search,
    tabActive: "border-(--color-strategy-lynch)/50 bg-(--color-strategy-lynch)/10 text-(--color-strategy-lynch)",
    iconColor: "text-(--color-strategy-lynch)",
  },
  {
    key: "berkshire",
    label: "Berkshire Quality",
    sublabel: "Márgenes · OCF/NI · ROE · sin dilución",
    icon: Award,
    tabActive: "border-(--color-strategy-berkshire)/50 bg-(--color-strategy-berkshire)/10 text-(--color-strategy-berkshire)",
    iconColor: "text-(--color-strategy-berkshire)",
  },
  {
    key: "dividendos",
    label: "Dividendos",
    sublabel: "Yield ≥2.5% · payout sostenible · EPS creciente",
    icon: DollarSign,
    tabActive: "border-(--color-strategy-dividendos)/50 bg-(--color-strategy-dividendos)/10 text-(--color-strategy-dividendos)",
    iconColor: "text-(--color-strategy-dividendos)",
  },
];

interface StrategyData {
  byStrategy: Record<FeedTabKey, Opportunity[]>;
}

function CardGrid({ opportunities }: { opportunities: Opportunity[] }) {
  if (opportunities.length === 0) return null;
  return (
    <motion.div
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
      variants={container}
      initial="hidden"
      animate="show"
    >
      {opportunities.map((o) => (
        <motion.div key={o.ticker} variants={item}>
          <OpportunityCard opportunity={o} />
        </motion.div>
      ))}
    </motion.div>
  );
}

/** Header "hero" para Destacadas -- deliberadamente distinto del resto: barra
 * de acento a la izquierda, icono en círculo relleno (no solo tintado), y
 * jerarquía tipográfica mayor, para marcarla como la sección principal. */
function FeaturedHeader({ count }: { count: number }) {
  return (
    <div className="flex items-center gap-3 border-l-2 border-(--color-accent) pl-4">
      <div className="rounded-full bg-(--color-accent) p-2.5 text-accent-foreground">
        <Flame className="size-4" aria-hidden />
      </div>
      <div>
        <h2 className="font-heading text-lg font-semibold leading-none">Destacadas</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Señales activas · Weinstein + CAN SLIM
        </p>
      </div>
      <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
        {count}
      </span>
    </div>
  );
}

/** Barra de pestañas para las 4 estrategias -- reemplaza los 4 bloques
 * full-width apilados por una única sección filtrable. */
function StrategyTabBar({
  active,
  counts,
  onChange,
}: {
  active: FeedTabKey;
  counts: Record<FeedTabKey, number>;
  onChange: (key: FeedTabKey) => void;
}) {
  return (
    <div role="tablist" aria-label="Filtrar por estrategia" className="flex flex-wrap gap-1.5 border-b border-border pb-3">
      {STRATEGY_SECTIONS.map(({ key, label, icon: Icon, tabActive }) => (
        <button
          key={key}
          role="tab"
          aria-selected={active === key}
          onClick={() => onChange(key)}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
            active === key ? tabActive : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          <Icon className="size-3.5 shrink-0" aria-hidden />
          {label}
          <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-muted-foreground">
            {counts[key]}
          </span>
        </button>
      ))}
    </div>
  );
}

export function FeedSection() {
  const [strategyData, setStrategyData] = useState<StrategyData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeStrategy, setActiveStrategy] = useState<FeedTabKey>("early_stage2");

  const [filters, setFilters] = useState<FeedFilters>(DEFAULT_FILTERS);
  const [top, setTop] = useState<Opportunity[] | null>(null);
  const [topError, setTopError] = useState<string | null>(null);

  // Estrategias: se cargan una única vez, no dependen de los filtros de Destacadas.
  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [earlyStage2, minervini, lynch, berkshire, dividendos] = await Promise.all([
          getOpportunities({ limit: 6, strategy: "early_stage2" }),
          getOpportunities({ limit: 6, strategy: "minervini" }),
          getOpportunities({ limit: 6, strategy: "lynch" }),
          getOpportunities({ limit: 6, strategy: "berkshire" }),
          getOpportunities({ limit: 6, strategy: "dividendos" }),
        ]);
        if (!cancelled) {
          setStrategyData({ byStrategy: { early_stage2: earlyStage2, minervini, lynch, berkshire, dividendos } });
        }
      } catch {
        if (!cancelled) setError("No se pudo conectar con el backend.");
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  // Destacadas: se refresca cada vez que cambian los filtros del FilterBar.
  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const result = await getOpportunities({
          limit: 4,
          risk: filters.risk === "todos" ? undefined : filters.risk,
          sector: filters.sector === "todos" ? undefined : filters.sector,
        });
        if (!cancelled) setTop(result);
      } catch {
        if (!cancelled) setTopError("No se pudo conectar con el backend.");
      }
    }

    load();
    return () => { cancelled = true; };
  }, [filters]);

  const sectors = useMemo(() => {
    const all = [...(top ?? []), ...Object.values(strategyData?.byStrategy ?? {}).flat()];
    return Array.from(new Set(all.map((o) => o.sector).filter((s): s is string => Boolean(s)))).sort();
  }, [top, strategyData]);

  if (error || topError) {
    return <ErrorState message={error ?? topError!} />;
  }

  if (!strategyData || !top) {
    // Mirrors the real DOM shape below (FeaturedHeader + StrategyTabBar) at
    // matching heights so the section's total height doesn't jump once data
    // arrives -- avoids a CLS-driven mis-click on the tab bar.
    return (
      <div className="flex flex-col gap-10">
        <section>
          <div className="flex flex-wrap items-center gap-2.5">
            {[150, 150, 180, 170].map((w, i) => (
              <div key={i} className="h-11 animate-pulse rounded-lg bg-muted" style={{ width: `${w}px` }} />
            ))}
          </div>
          <div className="mt-4 flex items-center gap-3 border-l-2 border-transparent pl-4">
            <div className="size-9 animate-pulse rounded-full bg-muted" />
            <div className="space-y-1.5">
              <div className="h-[18px] w-24 animate-pulse rounded bg-muted" />
              <div className="h-3 w-56 animate-pulse rounded bg-muted" />
            </div>
            <div className="ml-auto h-5 w-6 animate-pulse rounded-full bg-muted" />
          </div>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[...Array(4)].map((_, i) => <OpportunityCardSkeleton key={i} />)}
          </div>
        </section>
        <section>
          <div className="flex flex-wrap gap-1.5 border-b border-border pb-3">
            {STRATEGY_SECTIONS.map(({ key, label }) => (
              <div
                key={key}
                className="h-[30px] animate-pulse rounded-lg bg-muted"
                style={{ width: `${label.length * 7 + 56}px` }}
              />
            ))}
          </div>
          <div className="mt-4 flex flex-col gap-3">
            <div className="h-3.5 w-64 animate-pulse rounded bg-muted" />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[...Array(6)].map((_, i) => <OpportunityCardSkeleton key={i} />)}
            </div>
          </div>
        </section>
      </div>
    );
  }

  const activeConf = STRATEGY_SECTIONS.find((s) => s.key === activeStrategy)!;
  const activeOpps = strategyData.byStrategy[activeStrategy];
  const counts = {
    early_stage2: strategyData.byStrategy.early_stage2.length,
    minervini: strategyData.byStrategy.minervini.length,
    lynch: strategyData.byStrategy.lynch.length,
    berkshire: strategyData.byStrategy.berkshire.length,
    dividendos: strategyData.byStrategy.dividendos.length,
  };

  return (
    <div className="flex flex-col gap-10">
      {/* Sección 1: Destacadas (Weinstein + CAN SLIM) */}
      <section>
        <FilterBar filters={filters} sectors={sectors} onChange={setFilters} />
        <div className="mt-4">
          <FeaturedHeader count={top.length} />
        </div>
        <div className="mt-4">
          {top.length === 0 ? (
            <EmptyState
              icon={Flame}
              message="Sin señales Weinstein/CAN SLIM activas hoy."
              detail="Vuelve tras el próximo cierre de sesión."
            />
          ) : (
            <CardGrid opportunities={top} />
          )}
        </div>
      </section>

      {/* Sección 2: Estrategias -- vista filtrable en vez de 4 bloques apilados */}
      <section>
        <StrategyTabBar active={activeStrategy} counts={counts} onChange={setActiveStrategy} />
        <div className="mt-4 flex flex-col gap-3">
          <p className={cn("text-xs", activeConf.iconColor)}>{activeConf.sublabel}</p>
          {activeOpps.length === 0 ? (
            <EmptyState
              icon={activeConf.icon}
              message={`Sin oportunidades ${activeConf.label} detectadas hoy.`}
            />
          ) : (
            <CardGrid opportunities={activeOpps} />
          )}
        </div>
      </section>
    </div>
  );
}
