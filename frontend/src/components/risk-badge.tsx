import { cn } from "@/lib/utils";
import type { RiskBucket } from "@/lib/api";

const RISK_LABEL: Record<RiskBucket, string> = {
  bajo: "Riesgo bajo",
  medio: "Riesgo medio",
  alto: "Riesgo alto",
  desconocido: "Riesgo desconocido",
};

const RISK_COLOR: Record<RiskBucket, string> = {
  bajo: "bg-(--color-risk-low)",
  medio: "bg-(--color-risk-medium)",
  alto: "bg-(--color-risk-high)",
  desconocido: "bg-muted-foreground/40",
};

export function RiskBadge({ risk }: { risk: RiskBucket }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className={cn("size-1.5 rounded-full", RISK_COLOR[risk])} aria-hidden />
      {RISK_LABEL[risk]}
    </span>
  );
}
