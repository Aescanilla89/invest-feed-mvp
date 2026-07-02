"use client";

import { TrendingUp, Users, Award, AlertCircle } from "lucide-react";
import type { Catalyst, CatalystClassification } from "@/lib/api";

const TYPE_CONFIG = {
  earnings: {
    label: "Resultados",
    Icon: TrendingUp,
    classes: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20",
  },
  insider_buy: {
    label: "Insider Buy",
    Icon: Users,
    classes: "bg-violet-500/10 text-violet-600 dark:text-violet-400 border-violet-500/20",
  },
} as const;

const CLASSIFICATION_CONFIG: Record<CatalystClassification, { label: string; medal: string; classes: string }> = {
  oro: {
    label: "Oportunidad Oro",
    medal: "🥇",
    classes: "bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/20",
  },
  plata: {
    label: "Oportunidad Plata",
    medal: "🥈",
    classes: "bg-slate-500/10 text-slate-600 dark:text-slate-300 border-slate-500/20",
  },
  bronce: {
    label: "Oportunidad Bronce",
    medal: "🥉",
    classes: "bg-orange-500/10 text-orange-700 dark:text-orange-400 border-orange-500/20",
  },
};

export function CatalystCard({ catalyst }: { catalyst: Catalyst }) {
  const typeConf = TYPE_CONFIG[catalyst.catalyst_type] ?? TYPE_CONFIG.earnings;
  const { Icon } = typeConf;
  const classConf = catalyst.classification ? CLASSIFICATION_CONFIG[catalyst.classification] : null;

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm transition-shadow hover:shadow-md">
      {/* Header: tipo + score */}
      <div className="flex items-center justify-between gap-2">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${typeConf.classes}`}
        >
          <Icon className="size-3" aria-hidden />
          {typeConf.label}
        </span>
        {catalyst.combined_score !== null && (
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-semibold tabular-nums text-muted-foreground">
            Score {catalyst.combined_score}
          </span>
        )}
      </div>

      {/* Empresa */}
      <div>
        <div className="flex items-baseline gap-2">
          {catalyst.ticker && (
            <span className="font-heading text-base font-bold tracking-wide">
              {catalyst.ticker}
            </span>
          )}
          {catalyst.company_name && (
            <span className="truncate text-sm text-muted-foreground">{catalyst.company_name}</span>
          )}
        </div>
        {catalyst.sector && (
          <span className="text-xs text-muted-foreground/70">{catalyst.sector}</span>
        )}
      </div>

      {/* Título del catalizador */}
      <p className="text-sm font-medium leading-snug">{catalyst.title}</p>

      {/* Descripción técnica */}
      {catalyst.description && (
        <p className="text-xs text-muted-foreground leading-relaxed">{catalyst.description}</p>
      )}

      {/* Clasificación / Evento relevante */}
      <div className="mt-auto pt-1">
        {classConf ? (
          <span
            className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1 text-xs font-semibold ${classConf.classes}`}
          >
            <span aria-hidden>{classConf.medal}</span>
            {classConf.label}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted/50 px-3 py-1 text-xs text-muted-foreground">
            <AlertCircle className="size-3" aria-hidden />
            Evento relevante
          </span>
        )}
      </div>

      {/* Extracto de explicación si hay oportunidad */}
      {catalyst.explanation && (
        <p className="border-t border-border pt-2 text-xs text-muted-foreground/80 leading-relaxed line-clamp-2">
          {catalyst.explanation}
        </p>
      )}
    </div>
  );
}
