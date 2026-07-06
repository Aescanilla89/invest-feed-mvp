"use client";

import { TrendingUp, Users, BarChart3 } from "lucide-react";
import type { Catalyst, CatalystClassification } from "@/lib/api";

const TYPE_CONFIG = {
  earnings: {
    label: "Resultados",
    Icon: TrendingUp,
    classes: "bg-(--color-catalyst-earnings)/10 text-(--color-catalyst-earnings) border-(--color-catalyst-earnings)/20",
  },
  insider_buy: {
    label: "Insider Buy",
    Icon: Users,
    classes: "bg-(--color-catalyst-insider)/10 text-(--color-catalyst-insider) border-(--color-catalyst-insider)/20",
  },
  macro_data: {
    label: "Dato Macro",
    Icon: BarChart3,
    classes: "bg-(--color-catalyst-macro)/10 text-(--color-catalyst-macro) border-(--color-catalyst-macro)/20",
  },
} as const;

const CLASSIFICATION_CONFIG: Record<CatalystClassification, { label: string; rank: string; classes: string }> = {
  oro: {
    label: "Oportunidad Oro",
    rank: "1º",
    classes: "bg-(--color-medal-gold)/10 text-(--color-medal-gold) border-(--color-medal-gold)/30",
  },
  plata: {
    label: "Oportunidad Plata",
    rank: "2º",
    classes: "bg-(--color-medal-silver)/10 text-(--color-medal-silver) border-(--color-medal-silver)/30",
  },
  bronce: {
    label: "Oportunidad Bronce",
    rank: "3º",
    classes: "bg-(--color-medal-bronze)/10 text-(--color-medal-bronze) border-(--color-medal-bronze)/30",
  },
};

// macro_data no está ligado a un ticker y no lleva score/clasificación --
// lleva su propia fuente de datos en vez de un badge de medalla.
const MACRO_TYPES = new Set(["macro_data"]);
const SOURCE_LABEL: Record<string, string> = {
  macro_data: "Fuente: FRED (St. Louis Fed)",
};

interface MacroDataExtra {
  release_id?: string;
  release_name?: string;
  date?: string;
}

function formatDate(iso: string | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("es-ES", { day: "numeric", month: "short", year: "numeric" });
}

export function CatalystCard({ catalyst }: { catalyst: Catalyst }) {
  const typeConf = TYPE_CONFIG[catalyst.catalyst_type] ?? TYPE_CONFIG.earnings;
  const { Icon } = typeConf;
  const classConf = catalyst.classification ? CLASSIFICATION_CONFIG[catalyst.classification] : null;
  const isMacro = MACRO_TYPES.has(catalyst.catalyst_type);
  const hasCompanyInfo = Boolean(catalyst.ticker || catalyst.company_name);

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

      {/* Empresa -- solo se renderiza si hay ticker/nombre, los 3 tipos macro
       * no llevan empresa asociada. */}
      {hasCompanyInfo && (
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
      )}

      {/* Título del catalizador */}
      <p className="text-sm font-medium leading-snug">{catalyst.title}</p>

      {/* Contenido específico por tipo */}
      {catalyst.catalyst_type === "macro_data" ? (
        <p className="text-xs text-muted-foreground leading-relaxed">
          Publicación programada: {formatDate((catalyst.extra as MacroDataExtra).date)}
        </p>
      ) : (
        catalyst.description && (
          <p className="text-xs text-muted-foreground leading-relaxed">{catalyst.description}</p>
        )
      )}

      {/* Clasificación / fuente */}
      <div className="mt-auto pt-1">
        {isMacro ? (
          <span className="text-xs text-muted-foreground/70">{SOURCE_LABEL[catalyst.catalyst_type]}</span>
        ) : classConf ? (
          <span
            className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1 text-xs font-semibold ${classConf.classes}`}
          >
            <span
              className="inline-flex size-4 shrink-0 items-center justify-center rounded-full bg-current/20 text-[10px] font-bold tabular-nums"
              aria-hidden
            >
              {classConf.rank}
            </span>
            {classConf.label}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-muted/50 px-3 py-1 text-xs text-muted-foreground">
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
