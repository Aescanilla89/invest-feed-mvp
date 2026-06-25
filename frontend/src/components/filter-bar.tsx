"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export interface FeedFilters {
  minScore: number;
  risk: "todos" | "bajo" | "medio" | "alto";
  sector: string;
  sort: "score" | "stage";
}

const MIN_SCORE_OPTIONS = [
  { value: "0", label: "Cualquier score" },
  { value: "40", label: "40+" },
  { value: "60", label: "60+" },
  { value: "80", label: "80+" },
];

const RISK_OPTIONS = [
  { value: "todos", label: "Cualquier riesgo" },
  { value: "bajo", label: "Riesgo bajo" },
  { value: "medio", label: "Riesgo medio" },
  { value: "alto", label: "Riesgo alto" },
];

const SORT_OPTIONS = [
  { value: "score", label: "Ordenar por score" },
  { value: "stage", label: "Ordenar por stage" },
];

export function FilterBar({
  filters,
  sectors,
  onChange,
}: {
  filters: FeedFilters;
  sectors: string[];
  onChange: (filters: FeedFilters) => void;
}) {
  const minScoreLabels = Object.fromEntries(MIN_SCORE_OPTIONS.map((o) => [o.value, o.label]));
  const riskLabels = Object.fromEntries(RISK_OPTIONS.map((o) => [o.value, o.label]));
  const sortLabels = Object.fromEntries(SORT_OPTIONS.map((o) => [o.value, o.label]));
  const sectorLabels: Record<string, string> = { todos: "Todos los sectores", ...Object.fromEntries(sectors.map((s) => [s, s])) };

  return (
    <div className="flex flex-wrap items-center gap-2.5" role="group" aria-label="Filtros del feed">
      <Select
        value={String(filters.minScore)}
        onValueChange={(v) => onChange({ ...filters, minScore: Number(v) })}
      >
        <SelectTrigger className="h-11 w-[150px]" aria-label="Score mínimo">
          <SelectValue>{(v: string) => minScoreLabels[v]}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {MIN_SCORE_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={filters.risk} onValueChange={(v) => onChange({ ...filters, risk: v as FeedFilters["risk"] })}>
        <SelectTrigger className="h-11 w-[150px]" aria-label="Riesgo">
          <SelectValue>{(v: string) => riskLabels[v]}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {RISK_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={filters.sector} onValueChange={(v) => onChange({ ...filters, sector: v ?? "todos" })}>
        <SelectTrigger className="h-11 w-[180px]" aria-label="Sector">
          <SelectValue>{(v: string) => sectorLabels[v] ?? v}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="todos">Todos los sectores</SelectItem>
          {sectors.map((s) => (
            <SelectItem key={s} value={s}>
              {s}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={filters.sort} onValueChange={(v) => onChange({ ...filters, sort: v as FeedFilters["sort"] })}>
        <SelectTrigger className="h-11 w-[170px]" aria-label="Ordenar por">
          <SelectValue>{(v: string) => sortLabels[v]}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {SORT_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
