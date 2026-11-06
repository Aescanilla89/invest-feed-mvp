"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getDetectedOpportunities, type Opportunity } from "@/lib/api";
import { cn } from "@/lib/utils";

function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(`${value.slice(0, 10)}T12:00:00Z`);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("es-ES", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" }).format(date);
}

function formatReturn(value: number | null | undefined) {
  if (value == null) return "—";
  return `${value > 0 ? "+" : ""}${value.toLocaleString("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
}

export function DetectedOpportunities() {
  const [rows, setRows] = useState<Opportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getDetectedOpportunities()
      .then((data) => { if (!cancelled) setRows(data); })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const sorted = [...rows].sort((a, b) => (b.first_detected_date ?? "").localeCompare(a.first_detected_date ?? ""));

  if (loading) return <p className="mt-6 text-sm text-muted-foreground">Cargando oportunidades…</p>;
  if (error) return <p role="alert" className="mt-6 text-sm text-muted-foreground">No se pudieron cargar las oportunidades. Inténtalo de nuevo más tarde.</p>;
  if (sorted.length === 0) return <p className="mt-6 text-sm text-muted-foreground">No hay oportunidades detectadas disponibles.</p>;

  return (
    <div className="mt-6 overflow-x-auto rounded-xl border border-border/60">
      <table className="w-full min-w-[520px] border-collapse text-left text-sm">
        <thead className="bg-muted/40 text-xs font-medium text-muted-foreground">
          <tr>
            <th scope="col" className="px-4 py-3">Ticker</th>
            <th scope="col" className="px-4 py-3">Empresa</th>
            <th scope="col" className="px-4 py-3">Detectada</th>
            <th scope="col" className="px-4 py-3 text-right">Variación</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/60">
          {sorted.map((row) => (
            <tr key={row.ticker} className="hover:bg-muted/20">
              <td className="px-4 py-3 font-semibold"><Link className="hover:text-(--color-accent)" href={`/opportunities/${row.ticker}`}>{row.ticker}</Link></td>
              <td className="px-4 py-3 text-muted-foreground">{row.name ?? "—"}</td>
              <td className="px-4 py-3 tabular-nums text-muted-foreground">{formatDate(row.first_detected_date)}</td>
              <td className={cn("px-4 py-3 text-right font-semibold tabular-nums", row.return_since_first_detected_pct == null && "text-muted-foreground", (row.return_since_first_detected_pct ?? 0) > 0 && "text-(--color-risk-low)", (row.return_since_first_detected_pct ?? 0) < 0 && "text-(--color-risk-high)")} title="Variación histórica del precio desde la primera detección; no representa una operación ejecutada.">
                {formatReturn(row.return_since_first_detected_pct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-border/60 px-4 py-2.5 text-xs text-muted-foreground">La variación refleja el cambio de precio desde la detección registrada; no es una rentabilidad de cartera.</p>
    </div>
  );
}
