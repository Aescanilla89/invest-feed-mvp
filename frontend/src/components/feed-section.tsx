"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, TrendingUp, Search, Award, DollarSign, Zap } from "lucide-react";
import { OpportunityCard } from "@/components/opportunity-card";
import { OpportunityCardSkeleton } from "@/components/opportunity-card-skeleton";
import { EmptyState } from "@/components/empty-state";
import { getOpportunities, type Opportunity, type StrategyName } from "@/lib/api";

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.05, delayChildren: 0.05 } },
};
const item = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.25, 1, 0.5, 1] as const } },
};

const STRATEGY_SECTIONS: {
  key: StrategyName;
  label: string;
  sublabel: string;
  icon: React.ElementType;
  classes: string;
}[] = [
  {
    key: "minervini",
    label: "Minervini SEPA",
    sublabel: "Trend Template · precio sobre MAs · fuerza relativa",
    icon: TrendingUp,
    classes: "text-purple-600 dark:text-purple-400",
  },
  {
    key: "lynch",
    label: "Lynch GARP",
    sublabel: "Growth at a Reasonable Price · PEG ratio",
    icon: Search,
    classes: "text-emerald-600 dark:text-emerald-400",
  },
  {
    key: "berkshire",
    label: "Berkshire Quality",
    sublabel: "Márgenes · OCF/NI · ROE · sin dilución",
    icon: Award,
    classes: "text-amber-600 dark:text-amber-400",
  },
  {
    key: "dividendos",
    label: "Dividendos",
    sublabel: "Yield ≥2.5% · payout sostenible · EPS creciente",
    icon: DollarSign,
    classes: "text-sky-600 dark:text-sky-400",
  },
];

interface FeedData {
  top: Opportunity[];
  byStrategy: Record<StrategyName, Opportunity[]>;
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

function SectionHeader({
  icon: Icon,
  label,
  sublabel,
  iconClass,
  count,
}: {
  icon: React.ElementType;
  label: string;
  sublabel: string;
  iconClass: string;
  count: number;
}) {
  return (
    <div className="flex items-center gap-3">
      <div className={`rounded-lg border border-current/20 bg-current/10 p-2 ${iconClass}`}>
        <Icon className="size-4" aria-hidden />
      </div>
      <div>
        <h2 className="font-heading text-base font-semibold leading-none">{label}</h2>
        <p className="mt-0.5 text-xs text-muted-foreground">{sublabel}</p>
      </div>
      <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
        {count}
      </span>
    </div>
  );
}

export function FeedSection() {
  const [data, setData] = useState<FeedData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [top, minervini, lynch, berkshire, dividendos] = await Promise.all([
          getOpportunities({ limit: 4, minScore: 40, sort: "score" }),
          getOpportunities({ limit: 6, strategy: "minervini" }),
          getOpportunities({ limit: 6, strategy: "lynch" }),
          getOpportunities({ limit: 6, strategy: "berkshire" }),
          getOpportunities({ limit: 6, strategy: "dividendos" }),
        ]);
        if (!cancelled) {
          setData({
            top,
            byStrategy: { minervini, lynch, berkshire, dividendos },
          });
        }
      } catch {
        if (!cancelled) setError("No se pudo conectar con el backend.");
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  if (error) {
    return (
      <div className="flex items-start gap-3 rounded-lg border border-(--color-risk-high)/30 bg-(--color-risk-high)/10 p-4 text-sm">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-(--color-risk-high)" aria-hidden />
        <p>{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex flex-col gap-10">
        {[...Array(3)].map((_, s) => (
          <div key={s} className="flex flex-col gap-4">
            <div className="h-10 w-48 animate-pulse rounded-lg bg-muted" />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[...Array(s === 0 ? 4 : 6)].map((_, i) => <OpportunityCardSkeleton key={i} />)}
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-10">
      {/* Sección 1: Destacadas (Weinstein + CAN SLIM) */}
      <section>
        <SectionHeader
          icon={Zap}
          label="Destacadas"
          sublabel="Mejor combined score · Weinstein + CAN SLIM"
          iconClass="text-(--color-accent)"
          count={data.top.length}
        />
        <div className="mt-4">
          {data.top.length === 0 ? (
            <EmptyState message="Sin señales Weinstein/CAN SLIM activas hoy." />
          ) : (
            <CardGrid opportunities={data.top} />
          )}
        </div>
      </section>

      {/* Secciones por estrategia */}
      {STRATEGY_SECTIONS.map(({ key, label, sublabel, icon, classes }) => {
        const opps = data.byStrategy[key];
        return (
          <section key={key}>
            <SectionHeader
              icon={icon}
              label={label}
              sublabel={sublabel}
              iconClass={classes}
              count={opps.length}
            />
            <div className="mt-4">
              {opps.length === 0 ? (
                <EmptyState message={`Sin oportunidades ${label} detectadas hoy.`} />
              ) : (
                <CardGrid opportunities={opps} />
              )}
            </div>
          </section>
        );
      })}
    </div>
  );
}
