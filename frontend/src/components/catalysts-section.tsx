"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Zap, AlertTriangle } from "lucide-react";
import { CatalystCard } from "@/components/catalyst-card";
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
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="rounded-lg border border-orange-500/20 bg-orange-500/10 p-2 text-orange-600 dark:text-orange-400">
          <Zap className="size-4" aria-hidden />
        </div>
        <div>
          <h2 className="font-heading text-base font-semibold leading-none">
            Catalizadores del Día
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Earnings · Insider Buys · cruzados con Weinstein + CAN SLIM
          </p>
        </div>
        {catalysts !== null && (
          <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
            {catalysts.length}
          </span>
        )}
      </div>

      {/* Contenido */}
      {error ? (
        <div className="flex items-start gap-3 rounded-lg border border-(--color-risk-high)/30 bg-(--color-risk-high)/10 p-4 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-(--color-risk-high)" aria-hidden />
          <p>{error}</p>
        </div>
      ) : catalysts === null ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[...Array(3)].map((_, i) => <CatalystCardSkeleton key={i} />)}
        </div>
      ) : catalysts.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-muted/30 py-10 text-center text-sm text-muted-foreground">
          Sin catalizadores detectados esta semana.
          <br />
          <span className="text-xs opacity-70">El job corre tras el screener diario.</span>
        </div>
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
