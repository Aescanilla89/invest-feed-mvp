"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle } from "lucide-react";
import { FilterBar, type FeedFilters } from "@/components/filter-bar";
import { OpportunityCard } from "@/components/opportunity-card";
import { OpportunityCardSkeleton } from "@/components/opportunity-card-skeleton";
import { EmptyState } from "@/components/empty-state";
import { StrategyTabs, type ActiveStrategy } from "@/components/strategy-tabs";
import { getOpportunities, type Opportunity } from "@/lib/api";

const DEFAULT_FILTERS: FeedFilters = { minScore: 80, risk: "todos", sector: "todos", sort: "score" };

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.05, delayChildren: 0.05 } },
};

const item = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.25, 1, 0.5, 1] as const } },
};

export function FeedSection() {
  const [opportunities, setOpportunities] = useState<Opportunity[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<FeedFilters>(DEFAULT_FILTERS);
  const [activeStrategy, setActiveStrategy] = useState<ActiveStrategy>("todas");

  useEffect(() => {
    let cancelled = false;
    setOpportunities(null);
    const strategy = activeStrategy !== "todas" ? activeStrategy : undefined;
    getOpportunities({ strategy, limit: 100 } as Parameters<typeof getOpportunities>[0])
      .then((data) => {
        if (!cancelled) setOpportunities(data);
      })
      .catch(() => {
        if (!cancelled) setError("No se pudo conectar con el backend. ¿Está corriendo la API en el puerto esperado?");
      });
    return () => {
      cancelled = true;
    };
  }, [activeStrategy]);

  const sectors = useMemo(() => {
    if (!opportunities) return [];
    return Array.from(new Set(opportunities.map((o) => o.sector).filter((s): s is string => Boolean(s)))).sort();
  }, [opportunities]);

  const filtered = useMemo(() => {
    if (!opportunities) return [];
    let result = opportunities.filter((o) => o.combined_score >= filters.minScore);
    if (filters.risk !== "todos") result = result.filter((o) => o.risk_bucket === filters.risk);
    if (filters.sector !== "todos") result = result.filter((o) => o.sector === filters.sector);
    result = [...result].sort((a, b) =>
      filters.sort === "score" ? b.combined_score - a.combined_score : a.weinstein.stage - b.weinstein.stage,
    );
    return result;
  }, [opportunities, filters]);

  if (error) {
    return (
      <div className="flex items-start gap-3 rounded-lg border border-(--color-risk-high)/30 bg-(--color-risk-high)/10 p-4 text-sm">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-(--color-risk-high)" aria-hidden />
        <p>{error}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <StrategyTabs active={activeStrategy} onChange={setActiveStrategy} />

      <div className="flex flex-wrap items-center justify-between gap-4">
        <FilterBar filters={filters} sectors={sectors} onChange={setFilters} />
        {opportunities && (
          <p className="text-sm tabular text-muted-foreground">
            <span className="font-semibold text-foreground">{filtered.length}</span> de {opportunities.length}{" "}
            oportunidades
          </p>
        )}
      </div>

      {!opportunities ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <OpportunityCardSkeleton key={i} />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState message="No hay oportunidades que cumplan estos filtros ahora mismo. Prueba bajando el score mínimo o ampliando el riesgo." />
      ) : (
        <motion.div
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
          variants={container}
          initial="hidden"
          animate="show"
        >
          {filtered.map((opportunity) => (
            <motion.div key={opportunity.ticker} variants={item}>
              <OpportunityCard opportunity={opportunity} />
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  );
}
