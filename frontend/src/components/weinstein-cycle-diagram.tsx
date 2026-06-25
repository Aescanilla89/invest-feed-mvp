"use client";

import { useMemo } from "react";
import type { Weinstein } from "@/lib/api";

const WIDTH = 600;
const HEIGHT = 180;
const SAMPLES_PER_STAGE = 20;

const TYPICAL_DURATION_WEEKS: Record<number, number> = { 1: 16, 2: 20, 3: 10, 4: 16 };

const STAGE_META: Record<number, { label: string; x0: number; x1: number }> = {
  1: { label: "1 · Base", x0: 0, x1: 150 },
  2: { label: "2 · Avance", x0: 150, x1: 330 },
  3: { label: "3 · Techo", x0: 330, x1: 450 },
  4: { label: "4 · Declive", x0: 450, x1: 600 },
};

const BASE_Y = 132;
const TOP_Y = 30;
const PAD_TOP = 20;
const PAD_BOTTOM = 28;

function ease(t: number) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function buildStagePoints(stage: number): { x: number; y: number }[] {
  const meta = STAGE_META[stage];
  const points: { x: number; y: number }[] = [];
  for (let i = 0; i <= SAMPLES_PER_STAGE; i++) {
    const t = i / SAMPLES_PER_STAGE;
    const x = meta.x0 + t * (meta.x1 - meta.x0);
    let y: number;
    if (stage === 1) y = BASE_Y + Math.sin(t * Math.PI * 2.4) * 5;
    else if (stage === 2) y = BASE_Y + (TOP_Y - BASE_Y) * ease(t);
    else if (stage === 3) y = TOP_Y + Math.sin(t * Math.PI * 2.2) * 4;
    else y = TOP_Y + (BASE_Y - TOP_Y) * ease(t);
    points.push({ x, y: PAD_TOP + y });
  }
  return points;
}

function toPath(points: { x: number; y: number }[]) {
  return points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}

export function WeinsteinCycleDiagram({ weinstein }: { weinstein: Weinstein }) {
  const { stage, weeks_in_stage, is_transition } = weinstein;

  const stagePointsByStage = useMemo(
    () => ({ 1: buildStagePoints(1), 2: buildStagePoints(2), 3: buildStagePoints(3), 4: buildStagePoints(4) }),
    [],
  );

  const marker = useMemo(() => {
    const points = stagePointsByStage[stage as 1 | 2 | 3 | 4];
    let fraction = Math.min(weeks_in_stage / TYPICAL_DURATION_WEEKS[stage], 0.95);
    fraction = Math.max(fraction, 0.05);
    if (is_transition) fraction = 0.05;
    const index = Math.round(fraction * SAMPLES_PER_STAGE);
    return points[Math.min(index, points.length - 1)];
  }, [stage, weeks_in_stage, is_transition, stagePointsByStage]);

  const isAdvanceLike = stage === 1 || stage === 2;

  return (
    <div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" role="img" aria-label={`Diagrama del ciclo de Weinstein, posición actual: Stage ${stage}`}>
        {[1, 2, 3, 4].map((s) => (
          <path
            key={s}
            d={toPath(stagePointsByStage[s as 1 | 2 | 3 | 4])}
            fill="none"
            stroke={s === stage ? "var(--accent)" : "var(--stage-neutral)"}
            strokeOpacity={s === stage ? 1 : 0.35}
            strokeWidth={s === stage ? 3 : 2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}

        <circle cx={marker.x} cy={marker.y} r={6} fill="var(--background)" stroke="var(--accent)" strokeWidth={2.5} />

        {[1, 2, 3, 4].map((s) => {
          const meta = STAGE_META[s];
          const midX = (meta.x0 + meta.x1) / 2;
          return (
            <text
              key={s}
              x={midX}
              y={HEIGHT - 6}
              textAnchor="middle"
              className="select-none"
              fill={s === stage ? "var(--accent)" : "var(--muted-foreground)"}
              fontSize={12}
              fontWeight={s === stage ? 600 : 400}
            >
              {meta.label}
            </text>
          );
        })}
      </svg>

      <p className="mt-2 text-xs text-muted-foreground">
        Estás aquí: <span className="font-medium text-foreground">Stage {stage}</span>, {weeks_in_stage} semanas
        {is_transition && " — justo en la transición de base a avance"}. {isAdvanceLike ? "Fase constructiva del ciclo." : "Fase de distribución/declive del ciclo."}{" "}
        Esto es un esquema idealizado del método, no una proyección de precio.
      </p>
    </div>
  );
}
