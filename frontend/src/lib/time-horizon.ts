import type { Opportunity } from "@/lib/api";

export type TimeHorizonKey = "corto" | "medio" | "largo";

export const TIME_HORIZON_META: Record<TimeHorizonKey, { label: string; sublabel: string }> = {
  corto: { label: "Corto-medio plazo", sublabel: "Semanas a meses · señal de entrada táctica" },
  medio: { label: "Medio plazo", sublabel: "Meses a 1 año · crecimiento a precio razonable" },
  largo: { label: "Largo plazo", sublabel: "1+ años · calidad / renta" },
};

/**
 * Deriva un horizonte temporal único a partir de qué estrategias pasan.
 * Prioridad: Berkshire/Dividendos (largo) > Lynch (medio) > Minervini o señal
 * Weinstein/CAN SLIM (corto-medio). Con varias estrategias activas se elige
 * el horizonte más largo, porque implica una tesis de inversión más duradera.
 */
export function deriveTimeHorizon(opportunity: Pick<Opportunity, "strategies" | "signal_type">): TimeHorizonKey {
  const { strategies, signal_type } = opportunity;

  if (strategies?.berkshire?.passed || strategies?.dividendos?.passed) return "largo";
  if (strategies?.lynch?.passed) return "medio";
  if (strategies?.minervini?.passed || signal_type) return "corto";
  return "medio";
}
