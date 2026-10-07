import { cn } from "@/lib/utils";
import type { RiskBucket } from "@/lib/api";

const RISK_LABEL: Record<RiskBucket, string> = {
  bajo: "Volatilidad baja",
  medio: "Volatilidad media",
  alto: "Volatilidad alta",
  desconocido: "Volatilidad no disponible",
};

const RISK_COLOR: Record<RiskBucket, string> = {
  bajo: "bg-(--color-risk-low)",
  medio: "bg-(--color-risk-medium)",
  alto: "bg-(--color-risk-high)",
  desconocido: "bg-muted-foreground/40",
};

export function RiskBadge({ risk }: { risk: RiskBucket }) {
  const explanation = risk === "desconocido"
    ? "No hay suficientes datos semanales para calcular la volatilidad."
    : "Clasificación basada en la desviación estándar de los rendimientos semanales de las últimas 12 semanas: baja (<3 %), media (3–6 %) o alta (≥6 %). No representa el riesgo total de la inversión.";
  return (
    <span title={explanation} aria-label={`${RISK_LABEL[risk]}. ${explanation}`} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className={cn("size-1.5 rounded-full", RISK_COLOR[risk])} aria-hidden />
      {RISK_LABEL[risk]}
    </span>
  );
}
