"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Radar, CalendarClock } from "lucide-react";
import { CatalystCard } from "@/components/catalyst-card";
import { EmptyState, ErrorState } from "@/components/empty-state";
import { getCatalysts, type Catalyst } from "@/lib/api";

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.05 } },
};
const item = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 1, 0.5, 1] as const } },
};

function CatalystCardSkeleton() {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <div className="h-5 w-24 animate-pulse rounded-full bg-muted" />
        <div className="h-5 w-14 animate-pulse rounded-full bg-muted" />
      </div>
      <div className="space-y-1.5">
        <div className="h-5 w-32 animate-pulse rounded bg-muted" />
        <div className="h-3.5 w-20 animate-pulse rounded bg-muted" />
      </div>
      <div className="h-4 w-3/4 animate-pulse rounded bg-muted" />
      <div className="h-3.5 w-full animate-pulse rounded bg-muted" />
      <div className="h-7 w-36 animate-pulse rounded-lg bg-muted" />
    </div>
  );
}

export function CatalystsSection() {
  const [catalysts, setCatalysts] = useState<Catalyst[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCatalysts(7)
      .then((data) => { if (!cancelled) setCatalysts(data); })
      .catch(() => { if (!cancelled) setError("No se pudieron cargar los catalizadores."); });
    return () => { cancelled = true; };
  }, []);

  return (
    <section className="flex flex-col gap-4">
      {/* Header -- deliberadamente distinto de SectionHeader: icono inline sin
       * círculo tintado, con línea de radar bajo el título en vez de un badge,
       * para diferenciar esta sección orientada a eventos del resto de grids. */}
      <div className="flex items-center gap-2.5">
        <Radar className="size-5 shrink-0 text-(--color-catalyst-earnings)" aria-hidden />
        <h2 className="font-heading text-base font-semibold leading-none">
          Catalizadores del Día
        </h2>
        {catalysts !== null && (
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
            {catalysts.length}
          </span>
        )}
      </div>
      <p className="-mt-3 border-l-2 border-(--color-catalyst-earnings)/40 pl-4 text-xs text-muted-foreground">
        Earnings · Insider Buys · cruzados con Weinstein + CAN SLIM
      </p>

      {/* Contenido */}
      {error ? (
        <ErrorState message={error} />
      ) : catalysts === null ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {/* getCatalysts(7) can return up to 7 items -- size the skeleton
           * closer to that so the grid doesn't gain/lose rows on load. */}
          {[...Array(6)].map((_, i) => <CatalystCardSkeleton key={i} />)}
        </div>
      ) : catalysts.length === 0 ? (
        <EmptyState
          icon={CalendarClock}
          message="Sin catalizadores detectados esta semana."
          detail="El job corre tras el screener diario."
        />
      ) : (
        <motion.div
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
          variants={container}
          initial="hidden"
          animate="show"
        >
          {catalysts.map((c) => (
            <motion.div key={c.id} variants={item}>
              <CatalystCard catalyst={c} />
            </motion.div>
          ))}
        </motion.div>
      )}
    </section>
  );
}
